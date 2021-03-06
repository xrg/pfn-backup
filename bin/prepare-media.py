#!/usr/bin/python
# -*- coding: utf-8 -*-
from openerp_libclient import rpc, agent_commands, tools
from openerp_libclient.extra import options
import logging
import sys
import optparse
import os
import os.path
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
              'dvd':      4489.25,
              'dvd-dl':   8140.8,
              'bd-sl':   23098.0, # unformatted: 23866.0
              'bd-dl':   46196.0, # unformatted: 47732.0
              #'bd-tl':   95466.0,
              #'bd-ql':  122072.0,
              }
    fill_factor = 99.7
    
    class DiskTypeAllowed(object):
        def __init__(self, dtype, remaining=1000):
            self.dtype = dtype
            self.size_mb = PMWorker.disk_sizes[dtype]
            self.size_bytes = long(self.size_mb) * MB
            self.count = 0
            self.remaining = int(remaining)
            self.fill_factor = PMWorker.fill_factor
        
        def increment(self):
            self.count += 1
            self.remaining -= 1

        def make_new(self):
            if not self.remaining:
                return None
            self.count += 1
            self.remaining -= 1

            return { 'name': False,
                        'path': False,
                        'size': self.size_mb,
                        'type': self.dtype,
                        'remaining': long(self.size_bytes * self.fill_factor / 100.0),
                        'old_files': [],
                        'new_files': [],
                        'num': self.count
                    }

    def __init__(self, allowed_media=None, wontfit_dir=None,
                 path_pattern='disk%02d', sector_size=2048, start_from=1, use_dtype=True):
        self.allowed_media = []
        for a in allowed_media:
            if ':' in a:
                a, rem = a.split(':',1)
                self.allowed_media.append(PMWorker.DiskTypeAllowed(a, rem))
            else:
                self.allowed_media.append(PMWorker.DiskTypeAllowed(a))

        self.volume_dir = False
        self.start_from = int(start_from)
        self.wontfit_dir = wontfit_dir
        self.sector_size = sector_size
        self.max_size = max([s.size_mb * MB for s in self.allowed_media])
        self.log.info("Max volume size: %s", self.sizeof_fmt(self.max_size))
        self.n_errors = 0
        self.file_pos = 0
        
        self.path_pattern = path_pattern
        self.use_dtype = use_dtype
        
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
            dpath = os.path.join(vdir, vd)
            if not os.path.isdir(dpath):
                # files are legal here, will silently be ignored
                continue

            if self.use_dtype and vd in self.disk_sizes:
                # standard hierarchy like "dvd/disk02/"
                for vd2 in os.listdir(dpath):
                    dpath2 = os.path.join(dpath, vd2)
                    if not os.path.isdir(dpath2):
                        continue

                    new_dest = { 'name': dpath2,
                            'path': dpath2,
                            'old_files': [],
                            'new_files': [],
                            'type': vd,
                            'size': self.disk_sizes[vd]
                            }

                    if vd2.startswith('disk'):
                        new_dest['num'] = int(vd2[4:])
                    self._scan_dest_dir(dpath2, new_dest)
            else:
                # some other dir, treat it as a disk
                new_dest = { 'name': dpath,
                            'path': dpath,
                            'old_files': [],
                            'new_files': [],
                            }
                self._scan_dest_dir(dpath, new_dest)

        # Renumber destination manifests
        for dm in self.dest_manifests:
            if dm.get('num', 0) >= self.start_from:
                self.start_from = dm['num'] + 1
        for dm in self.dest_manifests:
            if 'num' not in dm:
                dm['num'] = self.start_from
                self.start_from += 1

    def _scan_dest_dir(self, dpath, new_dest):
        """scan existing volumes
            (+manifests TODO)

        """
        self.log.debug("Found volume dir (%s), scanning: %s", new_dest.get('type', '?'), dpath)
        tsize = 0L
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error):
            for f in filenames:
                tsize += self.size_pad(os.path.getsize(os.path.join(dirpath, f)))

        # compute possible size:
        if 'type' not in new_dest:
            for amedia in self.allowed_media:
                if amedia.size_bytes >= tsize:
                    amedia.increment()
                    new_dest['type'] = amedia.dtype
                    new_dest['size'] = self.disk_sizes[amedia.dtype]
                    break
            else:
                new_dest['type'] = '?'
                new_dest['size'] = tsize / MB
                new_dest['remaining'] = 0L

        if 'remaining' not in new_dest:
            new_dest['remaining'] = (new_dest['size'] * MB) - tsize

        self.dest_manifests.append(new_dest)
        return True

    def scan_source_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        
        in_manifest = []
        msize = 0L
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error,
                                                    followlinks=True):
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
        in_manifest = self.src_manifest
        warn_end_disks = True
        while in_manifest:
            if in_manifest[0][1] > self.max_size:
                self.wontfit_files.append(in_manifest.pop(0))
                continue
    
            # sort by /least/ remaining size
            self.dest_manifests.sort(key=itemgetter('remaining'))
            avail_size = 0L # max avail size both in existing and allowed media
            for am in self.allowed_media:
                if am.remaining and am.size_bytes > avail_size:
                    avail_size = am.size_bytes
            if self.dest_manifests:
                mf = self.dest_manifests[-1]
                if (mf['remaining'] > 0) and (mf['remaining'] > avail_size):
                    avail_size = mf['remaining']

            # cleanup fast all these files that wouldn't fit
            pos = 0
            while (pos < len(in_manifest)) and in_manifest[pos][1] > avail_size:
                pos += 1
            if pos:
                in_manifest[:] = in_manifest[pos:]
                self.log.debug("Skipping %d files > %s", pos, self.sizeof_fmt(avail_size))

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
                        self.log.debug("Just filled disk: %s", mf['num'])
                        break
                mf['remaining'] = remaining
            
            if in_manifest:
                # not all archives could fit existing destinations
                for amedia in self.allowed_media:
                    if amedia.size_bytes < in_manifest[0][1]:
                        continue
                    new_dest = amedia.make_new()
                    if not new_dest:
                        continue
                    self.dest_manifests.append(new_dest)
                    self.log.debug("Will need new %s volume (# %d)", amedia.dtype, amedia.count)
                    break
                else:
                    if warn_end_disks:
                        log.warning("No disks left for file of size %s", self.sizeof_fmt(in_manifest[0][1]))
                        warn_end_disks = False
                    in_manifest.pop(0)
                
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
                    if self.use_dtype:
                        new_path = os.path.join(self.volume_dir, mf['type'], self.path_pattern % disk_num)
                    else:
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
                os.makedirs(mf['path'])

            for nf in mf['new_files']:
                bd = os.path.join(mf['path'], os.path.dirname(nf[0]))
                if not os.path.exists(bd):
                    os.makedirs(bd)
                self.log.debug("Moving %s to %s", nf[3], bd)
                if os.path.exists(os.path.join(bd, os.path.basename(nf[0]))):
                    # a `move` would silently replace the existing one,
                    # better not to clobber.
                    continue
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
