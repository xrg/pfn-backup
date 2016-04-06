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

    pgroup.add_option('-u', '--upload-to', help="URL of service to upload manifests onto")
    pgroup.add_option('-b', '--cookies-file', help='Cookie jar file')
    pgroup.add_option('-k', '--insecure', help="Skip SSL certificate verification")
    parser.add_option_group(pgroup)

options.allow_include = 3
options._path_options += ['output', 'cookies_file' ]
options.init(options_prepare=custom_options,
        have_args=None,
        config='~/.openerp/backup.conf', config_section=(),
        defaults={ 'cookies_file': '~/.f3_upload_cookies.txt', })


log = logging.getLogger('main')

def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


class BaseManifestor(object):
    log = logging.getLogger('manifestor')
    BS = 1024 * 1024

    def __init__(self):
        self.n_files = 0
        self.n_errors = 0
        self.use_hidden = True

    def walk_error(self, ose):
        self.log.error("error: %s", ose)
        self.n_errors += 1

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

    def _scan_dir(self, dpath):
        """Scan directory `dpath` for archive files, return their manifest

            @return manifest, aka. list of {name, size, [md5sum], base_path }
                `base_path` is `dpath`, ie. part not participating in `name`
        """
        msize = 0L
        n_files = 0
        n_allfiles = 0
        ret_manifest = []
        for dirpath, dirnames, filenames in os.walk(dpath, onerror=self.walk_error):
            self.log.debug("Walking: %s", dirpath)
            if not filenames:
                continue
            assert dirpath.startswith(dpath), "Unexpected dirpath: %s" % dirpath
            dirpath1 = dirpath[len(dpath):].lstrip(os.sep) + os.sep
            if not self._check_dirname(dirpath1):
                self.log.debug("Skipping dir: %s", dirpath1)
                continue
            for f in filenames:
                n_allfiles += 1
                if not self._check_filename(f):
                    self.log.debug("Skipping file: %s", f)
                    continue
                full_f = os.path.join(dirpath, f)
                this_size = os.path.getsize(full_f)
                ret_manifest.append({'name': dirpath1 + f, 'size': this_size, 'md5sum': None, 'base_path': dpath})
                n_files += 1
                msize += this_size

        self.log.info("Located %d/%d files totalling %s in %s", n_files, n_allfiles, sizeof_fmt(msize), dpath)
        self.n_files += n_files
        return True

    def _check_dirname(self, d):
        return self.use_hidden or (not d.startswith('.'))

    def _check_filename(self, f):
        return self.use_hidden or (not f.startswith('.'))


    def _compute_sums(self, in_manifest, out_manifest, prefix=False,
                      time_limit=False, size_limit=False):
        """Read files from `in_manifest`, compute their MD5 sums, put in `out_manifest`

            If a file is already in `out_manifest`, skip
            @param prefix   prepend this to filename before storing on `out_manifest`
        """
        tp = sstime = time.time()

        todo_size = sum([ x[1]['size'] for x in in_manifest])
        todo_num = len(in_manifest)

        dnum = 0
        done_size = 0L
        out_names = set([m['name'] for m in out_manifest])
        while in_manifest:
            t2 = time.time()
            if time_limit and (t2 > (sstime + time_limit)):
                self.log.debug("Stopping on deadline")
                break
            if size_limit and done_size > size_limit:
                break

            dpath, mf = in_manifest.pop(0)
            mf_name = mf['name']
            if prefix:
                mf_name = os.path.join(prefix, mf['name'])
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
            out_manifest.append(mf)
            done_size += mf['size']
            dnum += 1

            # This process is expected to be long, progress indication is essential
            if (time.time() - tp) > 2.0:
                self.log.info("Computed %d/%d files, %s of %s", dnum, todo_num,
                              sizeof_fmt(done_size), sizeof_fmt(todo_size))
                tp = time.time()

        if in_manifest:
            return False
        else:
            self.log.info("Finished, computed %d/%d files, %s of %s", dnum, todo_num,
                              sizeof_fmt(done_size), sizeof_fmt(todo_size))
            return True


class SourceManifestor(BaseManifestor):
    log = logging.getLogger('manifestor.source')

    def __init__(self, prefix=None):
        super(SourceManifestor, self).__init__()
        self.in_manifest = []
        self.out_manifest = []
        self.prefix = prefix


    def scan_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        self.in_manifest += self._scan_dir(dpath)
        return True


    def sort_by_size(self):
        """Put smaller files first

            This helps the algorithm get done with "easy" files, first, so that
            possible errors (on larger files, greatest probability) occur last
        """
        self.in_manifest.sort(key=lambda x: x[1]['size'])

    def compute_sums(self, time_limit=False, size_limit=False):
        """Compute MD5 sums of `in_manifest` files into `out_manifest`

            @param time_limit time (seconds) to stop after. Useful for test runs
        """

        self._compute_sums(self.in_manifest, self.out_manifest,
                           time_limit=time_limit, size_limit=size_limit)

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

worker = SourceManifestor(options.opts.prefix)

ssl_verify = True
if options.opts.insecure:
    ssl_verify = False

cj = cookielib.MozillaCookieJar()
if options.opts.cookies_file and os.path.exists(options.opts.cookies_file):
    cj.load(options.opts.cookies_file)

rsession = False
if options.opts.upload_to:
    rsession = requests.Session()
    rsession.cookies = cj

if False:
    pres = rsession.get(options.opts.upload_to, verify=ssl_verify)
    pres.raise_for_status()
    data = pres.json
    assert isinstance(data, list)
    worker.out_manifest = data
    log.info("Loaded ")

if (not worker.out_manifest) and options.opts.output:
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
elif rsession:
    headers = {'Content-type': 'application/json', }
    pres = rsession.post(options.opts.upload_to, headers=headers, verify=ssl_verify,
                         data=json.dumps({'mode': 'upload',
                                          'entries': worker.out_manifest })
                         )
    pres.raise_for_status()
else:
    if options.opts.output:
        worker.write_out(options.opts.output)

#eof
