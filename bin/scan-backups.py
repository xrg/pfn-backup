#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
#
#    F3, Open Source Management Solution
#    Copyright (C) 2016 P. Christeas <xrg@hellug.gr>
#
##############################################################################

import logging
import os
import os.path
import time
import json
import cookielib
import hashlib
import requests
import socket
import sys
import optparse
from openerp_libclient.extra import options

def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Generation options")
    pgroup.add_option('--force', default=False, action='store_true', help="Continue on errors")
    pgroup.add_option('--dry-run', default=False, action='store_true', help="Just print the results")
    pgroup.add_option('--small-first', default=False, action='store_true',
                      help="Sort by size, compute smaller files first")
    
    pgroup.add_option('--prefix', help="Add this (directory) prefix to scanned paths")
    pgroup.add_option('-o', '--output', help="Write output JSON file (re-use existing data)")

    parser.add_option_group(pgroup)

options.allow_include = 3
options._path_options += ['output', ]
options.init(options_prepare=custom_options,
        have_args=None,
        config='~/.openerp/backup.conf', config_section=(),
        defaults={ })


log = logging.getLogger('main')


class Manifestor(object):
    log = logging.getLogger('manifestor')
    BS = 1024 * 1024

    def __init__(self, prefix=None):
        self.n_files = 0
        self.n_errors = 0
        self.in_manifest = []
        self.out_manifest = []
        self.prefix = prefix
    
    def walk_error(self, ose):
        self.log.error("error: %s", ose)
        self.n_errors += 1
  
    @staticmethod
    def sizeof_fmt(num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def scan_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        
        msize = 0L
        n_files = 0
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error):
            self.log.debug("Walking: %s", dirpath)
            if not filenames:
                continue
            assert dirpath.startswith(dpath), "Unexpected dirpath: %s" % dirpath
            dirpath1 = dirpath[len(dpath):].lstrip(os.sep) + os.sep
            for f in filenames:
                full_f = os.path.join(dirpath, f)
                this_size = os.path.getsize(full_f)
                self.in_manifest.append((dpath, {'name': dirpath1 + f, 'size': this_size, 'md5sum': None}))
                n_files += 1
                msize += this_size
            
        self.log.info("Located %d files totalling %s in %s", n_files, self.sizeof_fmt(msize), dpath)
        self.n_files += n_files
        return True

    def sort_by_size(self):
        """Put smaller files first
        
            This helps the algorithm get done with "easy" files, first, so that
            possible errors (on larger files, greatest probability) occur last
        """
        self.in_manifest.sort(key=lambda x: x[1]['size'])

    def compute_sums(self, limit=False, size_limit=False):
        """Compute MD5 sums of `in_manifest` files into `out_manifest`
        
            @param limit time (seconds) to stop after. Useful for test runs
        """
        
        tp = sstime = time.time()
        
        todo_size = sum([ x[1]['size'] for x in self.in_manifest])
        todo_num = len(self.in_manifest)
        
        dnum = 0
        done_size = 0L
        out_names = set([m['name'] for m in self.out_manifest])
        while self.in_manifest:
            t2 = time.time()
            if limit and (t2 > (sstime + limit)):
                self.log.debug("Stopping on deadline")
                break
            if size_limit and done_size > size_limit:
                break
            
            dpath, mf = self.in_manifest.pop(0)
            mf_name = mf['name']
            if self.prefix:
                mf_name = os.path.join(self.prefix, mf['name'])
            if mf_name in out_names:
                continue

            if not mf['md5sum']:
                try:
                    mf['md5sum'] = self.md5sum(os.path.join(dpath, mf['name']))
                except Exception:
                    self.n_errors += 1
                    self.log.warning("Cannot compute %s", mf['name'], exc_info=True)
                    mf['md5sum'] = 'unreadable'
            
            mf['name'] = mf_name # use the one with prefix
            self.out_manifest.append(mf)
            done_size += mf['size']
            dnum += 1
            
            # This process is expected to be long, progress indication is essential
            if (time.time() - tp) > 2.0:
                self.log.info("Computed %d/%d files, %s of %s", dnum, todo_num,
                              self.sizeof_fmt(done_size), self.sizeof_fmt(todo_size))
                tp = time.time()
        
        if self.in_manifest:
            return False
        else:
            self.log.info("Finished, computed %d/%d files, %s of %s", dnum, todo_num,
                              self.sizeof_fmt(done_size), self.sizeof_fmt(todo_size))
            return True

    def md5sum(self, full_path):
        """Compute MD5 sum of some file
        
            Fear not, the core of this algorithm is an OpenSSL C function,
            which can be efficient enough for large buffers of input data.
            Using 1MB of buffer, this loop has been timed to perform as
            fast as the `md5sum` UNIX utility.
        """
        fp = open(full_path, 'rb')

        md5 = hashlib.md5()
        try:
            while True:
                data = fp.read(self.BS)
                if not len(data):
                    break
                md5.update(data)
        finally:
            fp.close()
        
        return md5.digest().encode('hex')

    def read_out(self, out_pname):
        """Read existing JSON file, re-using previous results
        """
        if os.path.exists(out_pname):
            fp = file(out_pname, 'rb')
            data = json.load(fp)
            assert isinstance(data, list), "Bad data: %s" % type(data)
            self.out_manifest = data
            return True
        else:
            return False
       
    def write_out(self, out_pname):
        """Write results to output JSON file
        """
        fp = open(out_pname, 'wb')
        json.dump(self.out_manifest, fp)
        fp.close()
        self.log.info("Results saved to %s", out_pname)

worker = Manifestor(options.opts.prefix)

if options.opts.output:
    worker.read_out(options.opts.output)

for fpath in options.args:
    worker.scan_dir(fpath)

if options.opts.small_first:
    log.debug("Sorting by size")
    worker.sort_by_size()

if True:
    kwargs = {}
    if options.opts.dry_run:
        kwargs['limit'] = 10.0 # sec
        kwargs['size_limit'] = pow(1024.0, 3)
    
    try:
        worker.compute_sums(**kwargs)
    except KeyboardInterrupt:
        log.info('Canceling by user request, will still save output in 2 sec')
        time.sleep(2.0) # User can hit Ctrl+C, again, here

if options.opts.dry_run:
    print "Results:"
    from pprint import pprint
    pprint(worker.out_manifest)
else:
    if options.opts.output:
        worker.write_out(options.opts.output)

#eof
