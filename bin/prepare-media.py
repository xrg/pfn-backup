#!/usr/bin/python
# -*- coding: utf-8 -*-
from openerp_libclient import rpc, agent_commands, tools
from openerp_libclient.extra import options
import logging
import sys
import optparse
import os
import os.path
import subprocess
import time
import re
import shutil
from operator import itemgetter
import collections


""" Split archives into removable volumes, of fixed size

    Improved version of "prepare-media.sh"
    
    Goal is:
      - split collections of backup archives into multiple 'volumes'
        (aka. disks), trying to fit as many files as possible on each
        one.
      - keep archives intact, ie. not split a single archive to more
        than one volume
      - preserve full path of archives, ie. directory structure
      - Try to preserve order of files
      - keep folder of "wontfit" archives, those larger than available
        volume media
      - discover existing files on media
      
      - generate "manifest" files with contents of each volume
"""


def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Generation options")
    pgroup.add_option('--force', default=False, action='store_true', help="Continue on errors")
    pgroup.add_option('--dry-run', default=False, action='store_true', help="Just print the results")
    pgroup.add_option('--output-dir', help="Directory where output media will be set")
    pgroup.add_option('--wontfit-dir', help="Directory of files not fit in allowed sizes")
    pgroup.add_option('--allowed-media', help="Comma-separated list of allowed disk types")
    pgroup.add_option('--start-from', type=int, help="Number of volume to start from")

    parser.add_option_group(pgroup)

options.allow_include = 3
options._path_options += ['output_dir', 'wontfit_dir']
options.init(options_prepare=custom_options,
        have_args=None,
        config='~/.openerp/backup.conf', config_section=(),
        defaults={ 'allowed_media':'dvd', 'output_dir': 'outgoing', 'wontfit_dir': 'wontfit',
                  'start_from': 1})


log = logging.getLogger('main')

if False:
    rpc.openSession(**options.connect_dsn)

    if not rpc.login():
        raise Exception("Could not login!")

if not options.args:
    log.error("Must supply input paths")
    sys.exit(1)
    

MB = 1048576L

class PMWorker(object):
    log = logging.getLogger('pmworker')
    disk_sizes = { # In MBytes
              'cd':       700.0,
              'dvd':      4589.84,
              'dvd-dl':   8140.8,
              'bd-sl':   23098.0, # unformatted: 23866.0
              #'bd-dl':   47732.0,
              #'bd-tl':   95466.0,
              #'bd-ql':  122072.0,
              }
    fill_factor = 99.0
    
    def __init__(self, allowed_media=None, wontfit_dir=None,
                 path_pattern='disk%02d', sector_size=2048, start_from=1):
        self.allowed_media = allowed_media or []
        self.volume_dir = False
        self.start_from = int(start_from)
        self.wontfit_dir = wontfit_dir
        self.sector_size = sector_size
        self.max_size = max([self.disk_sizes[s] * MB for s in self.allowed_media])
        self.log.info("Max volume size: %s", self.sizeof_fmt(self.max_size))
        self.n_errors = 0
        self.file_pos = 0
        
        self.path_pattern = path_pattern
        
        # manifests (aka. lists of files on volumes)
        self.src_manifest = []
        self.dest_manifests = []
        self.wontfit_files = []

    def walk_error(self, ose):
        self.log.error("error: %s", ose)
        self.n_errors += 1
  
    def size_pad(self, size):
        mod = size % self.sector_size
        if mod:
            size += self.sector_size - mod
        return size

    @staticmethod
    def sizeof_fmt(num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def use_volume_dir(self, vdir):
        self.volume_dir = vdir
        for vd in os.listdir(vdir):
            self._scan_dest_dir(os.path.join(vdir, vd))

    def _scan_dest_dir(self, dpath):
        """scan existing volumes
            (+manifests TODO)
        """
        if not os.path.isdir(dpath):
            # files are legal here, will silently be ignored
            return False

        self.log.debug("Found volume dir, scanning: %s", dpath)
        tsize = 0L
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error):
            for f in filenames:
                tsize += self.size_pad(os.path.getsize(os.path.join(dirpath, f)))
        
        new_dest = { 'name': dpath,
                    'path': dpath,
                    'old_files': [],
                    'new_files': [],
                    }
        # compute possible size:
        for dtype in self.allowed_media:
            if self.disk_sizes[dtype] * MB >= tsize:
                new_dest['type'] = dtype
                new_dest['size'] = self.disk_sizes[dtype]
                new_dest['remaining'] = (new_dest['size'] * MB) - tsize
                break
        else:
            new_dest['type'] = '?'
            new_dest['size'] = tsize / MB
            new_dest['remaining'] = 0L
        
        self.dest_manifests.append(new_dest)
        return True
        
    def scan_source_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        
        in_manifest = []
        msize = 0L
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error):
            self.log.debug("Walking: %s", dirpath)
            if not filenames:
                continue
            ssize = 0L
            assert dirpath.startswith(dpath), "Unexpected dirpath: %s" % dirpath
            dirpath1 = dirpath[len(dpath):].lstrip(os.sep) + os.sep
            for f in filenames:
                full_f = os.path.join(dirpath, f)
                this_size = os.path.getsize(full_f)
                in_manifest.append((dirpath1 + f, this_size, self.file_pos, full_f, {}))
                self.file_pos += 1
                if this_size < self.max_size:
                    # Only consider archives that fit in media
                    ssize += self.size_pad(this_size)
                
            self.log.debug("Located %s at %s", self.sizeof_fmt(ssize), dirpath)
            msize += ssize
            
        self.log.info("Located %s in %s", self.sizeof_fmt(msize), dpath)
        self.src_manifest += in_manifest
        return True

    def compute(self):
        """ Process, distribute source archives into dest manifests
        """
        self.src_manifest.sort(key=itemgetter(1), reverse=True)
        self.dest_manifests.sort(key=itemgetter('remaining'))
        in_manifest = self.src_manifest
        while in_manifest:
            if in_manifest[0][1] > self.max_size:
                self.wontfit_files.append(in_manifest.pop(0))
                continue
    
            # sort by /least/ remaining size
            for mf in self.dest_manifests:
                remaining = mf['remaining']
                if remaining <= 0:
                    continue
                pos = 0
                while pos < len(in_manifest):
                    # source manifest is sorted by descending size
                    # try to find largest file that fits this dest.
                    if in_manifest[pos][1] > remaining:
                        pos += 1
                        continue
                    entry = in_manifest.pop(pos)
                    remaining -= self.size_pad(entry[1])
                    mf['new_files'].append(entry)
                    if remaining <= 0:
                        break
                mf['remaining'] = remaining
            
            if in_manifest:
                # not all archives could fit existing destinations
                for dtype in self.allowed_media:
                    if self.disk_sizes[dtype] * MB > in_manifest[0][1]:
                        new_dest = { 'name': False,
                                        'path': False,
                                        'size': self.disk_sizes[dtype],
                                        'type': dtype,
                                        'remaining': long(self.disk_sizes[dtype] * MB * self.fill_factor / 100.0),
                                        'old_files': [],
                                        'new_files': [],
                                    }
                        self.dest_manifests.append(new_dest)
                        self.log.debug("Will need new %s volume", dtype)
                        break
                else:
                    # cannot reach here, because of "max_size" check at start of loop
                    raise RuntimeError("No disk size can accomodate file of %s" % self.sizeof_fmt(in_manifest[0][1]))
                
        # Second pass: sort "new_files" on each destination
        for mf in self.dest_manifests:
            mf['new_files'].sort(key=itemgetter(2))
        
        # Third pass: sort destinations by earliest file on each
        def mf_key(mf):
            # manifest key
            if mf['new_files']:
                new_pos = mf['new_files'][0][2]
            else:
                new_pos = 0
            return (bool(mf['path'] != False), mf['name'], new_pos)
        self.dest_manifests.sort(key=mf_key)
        
        # Fourth pass: assign a name (label) and tmp path on each new volume
        old_names = set()
        old_paths = set()
        disk_num = self.start_from
        for mf in self.dest_manifests:
            if mf['path']:
                old_paths.add(mf['path'])
            if mf['name']:
                old_names.add(mf['name'])
        

        for mf in self.dest_manifests:
            if not mf['path']:
                while True:
                    new_path = os.path.join(self.volume_dir, self.path_pattern % disk_num)
                    if new_path not in old_paths:
                        break
                    disk_num += 1
                mf['path'] = new_path
                if not mf['name']:
                    mf['name'] = "Backup %s" % disk_num
                disk_num += 1
            
        return True

    def move_files(self):
        n_moved = 0
        for mf in self.dest_manifests:
            if not mf['new_files']:
                continue
            if not mf['path']:
                raise RuntimeError("No path for dest volume")
            if not os.path.exists(mf['path']):
                os.mkdir(mf['path']) # only last element, otherwise error
            
            for nf in mf['new_files']:
                bd = os.path.join(mf['path'], os.path.dirname(nf[0]))
                if not os.path.exists(bd):
                    os.makedirs(bd)
                self.log.debug("Moving %s to %s", nf[3], bd)
                shutil.move(nf[3], bd)
                n_moved += 1
        self.log.info("Moved %d files to output directories", n_moved)

    def print_results(self):
        """List resulting manifests
        """
        print "Results:"
        for mf in self.dest_manifests:
            print
            print "Manifest: %s  (%s) %s of %s" % (mf['name'], mf['type'],
                                                   self.sizeof_fmt(mf['remaining']),
                                                   self.sizeof_fmt(mf['size'] * MB))
            print "Path %s\n" % (mf['path'])
            
            for nf in mf['new_files'][:10]:
                print "     %-60s %10s" %( nf[0], self.sizeof_fmt(nf[1]))
            if len(mf['new_files']) > 10:
                print "     ..."
            
        if self.wontfit_files:
            tsum = 0L
            for wf in self.wontfit_files:
                tsum += wf[1]
            print "Won't fit: %s" % self.sizeof_fmt(tsum)
            print
            for nf in self.wontfit_files[:10]:
                print "     %-60s %10s" %( nf[0], self.sizeof_fmt(nf[1]))
            if len(self.wontfit_files) > 10:
                print "     ..."
        
    def print_summary(self):
        """Print a summary of new volumes to be needed
        """
        vols = collections.Counter()
        num_vols = 0
        for mf in self.dest_manifests:
            if not mf['new_files']:
                continue
            num_vols += 1
            vols[mf['type']] += 1
        
        print "Will need %d new volumes:" % num_vols
        for m, c in vols.items():
            print "    %d x %s" % (c, m)
        print
        

# Main flow:
worker = PMWorker(allowed_media=options.opts.allowed_media.split(','),
                  wontfit_dir=options.opts.wontfit_dir,
                  start_from=options.opts.start_from)

worker.use_volume_dir(options.opts.output_dir)

# stage 2: scan "source" folders
for fpath in options.args:
    worker.scan_source_dir(fpath)

if worker.n_errors:
    log.error("Errors encountered while scanning files. Cannot continue")
    if not options.opts.force:
        sys.exit(1)


# stage x: write "manifest" file on each volume.

worker.compute()
worker.print_summary()

if options.opts.dry_run:
    worker.print_results()
else:
    worker.move_files()

#eof