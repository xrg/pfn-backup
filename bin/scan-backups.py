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
import sys
import optparse
from openerp_libclient.extra import options
import threading
import shutil

def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Generation options")
    pgroup.add_option('--mode', help="Operation mode: sources, volume or udisks2")
    pgroup.add_option('--force', default=False, action='store_true', help="Continue on errors")
    pgroup.add_option('--fast-run', default=False, action='store_true', help="Limit scanning to 10sec or 1 GB, for test runs")

    pgroup.add_option('--dry-run', default=False, action='store_true', help="Just print the results")
    pgroup.add_option('--small-first', default=False, action='store_true',
                      help="Sort by size, compute smaller files first")

    pgroup.add_option('--prefix', help="Add this (directory) prefix to scanned paths")
    pgroup.add_option('-o', '--output', help="Write output JSON file (re-use existing data)")
    pgroup.add_option('--outdir', help="Directory to move checked files into")

    pgroup.add_option('-u', '--upload-to', help="URL of service to upload manifests onto")
    pgroup.add_option('-b', '--cookies-file', help='Cookie jar file')
    pgroup.add_option('-k', '--insecure', default=False, action='store_true', help="Skip SSL certificate verification")
    parser.add_option_group(pgroup)

options.allow_include = 3
options._path_options += ['output', 'cookies_file', 'outdir']
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
        self.context = {}

    def walk_error(self, ose):
        self.log.error("error: %s", ose)
        self.n_errors += 1

    def get_out_manifest(self):
        raise NotImplementedError

    def md5sum(self, full_path, size_hint=0):
        """Compute MD5 sum of some file

            Fear not, the core of this algorithm is an OpenSSL C function,
            which can be efficient enough for large buffers of input data.
            Using 1MB of buffer, this loop has been timed to perform as
            fast as the `md5sum` UNIX utility.
        """
        ts = time.time()
        r_size = 0L
        fp = open(full_path, 'rb')

        md5 = hashlib.md5()
        try:
            while True:
                data = fp.read(self.BS)
                if not len(data):
                    break
                r_size += len(data)
                md5.update(data)
                if time.time() - ts > 10.0:
                    self.log.info("MD5sum compute: %s of %s", sizeof_fmt(r_size), sizeof_fmt(size_hint))
                    ts = time.time()
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
            dirpath1 = dirpath[len(dpath):].lstrip(os.sep)
            if dirpath1:
                dirpath1 += os.sep
            if not self._check_dirname(dirpath1):
                self.log.debug("Skipping dir: %s", dirpath1)
                continue
            for f in filenames:
                n_allfiles += 1
                if not self._check_filename(f):
                    self.log.debug("Skipping file: %s", f)
                    continue
                full_f = os.path.join(dirpath, f)
                try:
                    this_size = os.path.getsize(full_f)
                    ret_manifest.append({'name': dirpath1 + f, 'size': this_size, 'md5sum': None, 'base_path': dpath})
                    n_files += 1
                    msize += this_size
                except EnvironmentError, e:
                    self.log.warning("File %s cannot be stat'ed, defect on volume: %s", full_f, e)
                    self.n_errors += 1
                except Exception, e:
                    self.log.warning("File %s cannot be stat'ed, defect on volume: %s", full_f, e)
                    self.n_errors += 1

        self.log.info("Located %d/%d files totalling %s in %s", n_files, n_allfiles, sizeof_fmt(msize), dpath)
        self.n_files += n_files
        return ret_manifest

    def _check_dirname(self, d):
        return self.use_hidden or (not d.startswith('.'))

    def _check_filename(self, f):
        return self.use_hidden or (not f.startswith('.'))


    def _compute_sums(self, in_manifest, out_manifest, prefix=False,
                      time_limit=False, size_limit=False, file_limit=False):
        """Read files from `in_manifest`, compute their MD5 sums, put in `out_manifest`

            If a file is already in `out_manifest`, skip
            @param prefix   prepend this to filename before storing on `out_manifest`
        """
        tp = sstime = time.time()

        todo_size = sum([ x['size'] for x in in_manifest])
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
            if file_limit and dnum > file_limit:
                break

            mf = in_manifest.pop(0)
            dpath = mf.pop('base_path')
            mf_name = mf['name']
            if prefix:
                mf_name = os.path.join(prefix, mf['name'])
            if mf_name in out_names:
                continue

            if not mf['md5sum']:
                try:
                    mf['md5sum'] = self.md5sum(os.path.join(dpath, mf['name']), mf.get('size', 0L))
                except IOError, e:
                    self.n_errors += 1
                    self.log.warning("IOError on %s: %s", mf['name'], e)
                    mf['md5sum'] = 'unreadable'
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

    def _filter_in(self, manifest, prefix, storage):
        if prefix:
            lname = lambda m: os.path.join(prefix, m['name'])
        else:
            lname = lambda m: m['name']

        tmp_manifest = manifest
        tmp_out_manifest = []
        while tmp_manifest:
            tmp = tmp_manifest[:1000]
            tmp_manifest = tmp_manifest[1000:]
            outnames = storage.filter_needed(map(lname, tmp), self)
            if outnames:
                outnames = set(outnames)
                for t in tmp:
                    if lname(t) in outnames:
                        tmp_out_manifest.append(t)

        # Then, apply filtered list inplace
        manifest[:] = tmp_out_manifest


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

    def get_out_manifest(self):
        return self.out_manifest

    def sort_by_size(self):
        """Put smaller files first

            This helps the algorithm get done with "easy" files, first, so that
            possible errors (on larger files, greatest probability) occur last
        """
        self.in_manifest.sort(key=lambda x: x['size'])

    def compute_sums(self, time_limit=False, size_limit=False):
        """Compute MD5 sums of `in_manifest` files into `out_manifest`

            @param time_limit time (seconds) to stop after. Useful for test runs
        """

        self._compute_sums(self.in_manifest, self.out_manifest, prefix=self.prefix,
                           time_limit=time_limit, size_limit=size_limit)

    def produce_sums(self):
        """Compute MD5 sums, in batches
        
            When number of files gets large, or size/time is large, it makes sense
            to upload every now and then
            
            Hard-coded loop limits are:
                time: 5min
                size: 10GB
                files: 2000
        """
        tmp_out_manifest = []
        while self.in_manifest:
            self._compute_sums(self.in_manifest, tmp_out_manifest, prefix=self.prefix,
                               time_limit=300.0, size_limit=1.0e10, file_limit=2000)
            if not tmp_out_manifest:
                continue
            
            yield tmp_out_manifest
            self.out_manifest += tmp_out_manifest
            tmp_out_manifest = []

    def filter_in(self, storage):
        """Check filenames of `in_manifest` against storage

            storage can tell us if files need to be checked (MD5) at all,
            it would be a waste of CPU+time to compute those already in.

        """
        self._filter_in(self.in_manifest, self.prefix, storage)

class MoveManifestor(BaseManifestor):
    """This one will only read filenames, check with storage and move files away
    """
    log = logging.getLogger('manifestor.move')

    def __init__(self,prefix=None):
        super(MoveManifestor, self).__init__()
        self.in_manifest = []
        self.move_manifest = []
        self.prefix = prefix


    def scan_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        self.in_manifest += self._scan_dir(dpath)
        return True

    def get_out_manifest(self):
        raise RuntimeError("MoveManifestor shall not write its output")

    def compute_sums(self, time_limit=False, size_limit=False):
        raise RuntimeError("No computation allowed")

    def filter_in(self, storage):
        if self.prefix:
            lname = lambda m: os.path.join(self.prefix, m['name'])
        else:
            lname = lambda m: m['name']

        tmp_manifest = self.in_manifest
        tmp_out_manifest = []
        while tmp_manifest:
            tmp = tmp_manifest[:1000]
            tmp_manifest = tmp_manifest[1000:]
            outnames = storage.filter_checked(map(lname, tmp), self)
            if outnames:
                outnames = set(outnames)
                for t in tmp:
                    if lname(t) in outnames:
                        tmp_out_manifest.append(t)
                        
        self.move_manifest = tmp_out_manifest

    def move_to(self, out_dir, dry=True):
        """Move files of manifest into `out_dir`
        """
        new_dirs = set()
        n_moved = 0

        for mf in self.move_manifest:
            src_fname = os.path.join(mf['base_path'], mf['name'])
            out_fname = os.path.join(out_dir, mf['name'])
            odir = os.path.dirname(out_fname)
            if odir in new_dirs or os.path.isdir(odir):
                pass
            else:
                log.info("Must create directory: %s", odir)
                if not dry:
                    os.makedirs(odir)
                new_dirs.add(odir)

            log.info("Move %s to %s", src_fname, out_fname)
            if not dry:
                shutil.move(src_fname, out_fname)
            n_moved += 1

        log.info("Moved %d files", n_moved)


class VolumeManifestor(BaseManifestor):
    log = logging.getLogger('manifestor.source')

    def __init__(self, label='', uuid=False):
        super(VolumeManifestor, self).__init__()
        self.manifest = []
        self.context['vol_label'] = label
        if uuid:
            self.context['uuid'] = uuid

    def get_out_manifest(self):
        return self.manifest

    def scan_dir(self, dpath):
        if not os.path.isdir(dpath):
            self.log.error("Input arguments must be directories. \"%s\" is not", dpath)
            self.n_errors += 1
            return False
        self.manifest += self._scan_dir(dpath)
        return True


    def sort_by_size(self):
        """Put smaller files first

            This helps the algorithm get done with "easy" files, first, so that
            possible errors (on larger files, greatest probability) occur last
        """
        self.manifest.sort(key=lambda x: x['size'])

    def compute_sums(self, time_limit=False, size_limit=False):
        """Compute MD5 sums of `in_manifest` files into `out_manifest`

            @param time_limit time (seconds) to stop after. Useful for test runs
        """
        in_manifest = self.manifest
        out_manifest = []
        try:
            self._compute_sums(in_manifest, out_manifest,
                            time_limit=time_limit, size_limit=size_limit)
        finally:
            # replace with ones that got computed, even on KeyboardInterrupt
            self.manifest = out_manifest

    def produce_sums(self):
        """Compute MD5 sums, in batches
        
            When number of files gets large, or size/time is large, it makes sense
            to upload every now and then
            
            Hard-coded loop limits are:
                time: 5min
                size: 10GB
                files: 2000
        """
        tmp_out_manifest = []
        in_manifest = self.manifest[:]
        out_manifest = []
        while in_manifest:
            self._compute_sums(in_manifest, tmp_out_manifest,
                               time_limit=300.0, size_limit=1.0e10, file_limit=2000)
            if not tmp_out_manifest:
                continue
            
            yield tmp_out_manifest
            out_manifest += tmp_out_manifest
            tmp_out_manifest = []
        
        self.manifest = out_manifest

    def filter_in(self, storage):
        """Check filenames of `in_manifest` against storage

            storage can tell us if files need to be checked (MD5) at all,
            it would be a waste of CPU+time to compute those already in.

        """
        self._filter_in(self.manifest, False, storage)


class BaseStorageInterface(object):
    def __init__(self, options):
        pass

    def filter_needed(self, in_fnames, worker):
        """Take `in_fnames` list of (prefixed) input filenames, check with storage

            @return filtered list of names to compute MD5 sums for
        """
        raise NotImplementedError

    def filter_checked(self, in_fnames, worker):
        """Find those of `in_fnames` which have been backed up
        
            Storage will determine policy, under which archives can be considered
            safely backed
        """
        # by default, no file is considered safe
        return []

    def write_manifest(self, worker):
        raise NotImplementedError
    
    def consume_manifests(self, worker, producer):
        """Continuously write manifests, as generated by producer
        
            @param worker is used to setup storage parameters from
            @param producer a generator, which will yield lists of manifests.
                Each list will be written as soon as it is produced
        """
        raise NotImplementedError

class DryStorage(BaseStorageInterface):
    """Dry-run mode: just print results
    """

    def filter_needed(self, in_fnames, worker):
        return in_fnames

    def write_manifest(self, worker):
        print "Results:"
        from pprint import pprint
        pprint(worker.get_out_manifest())

class JSONStorage(BaseStorageInterface):
    log = logging.getLogger('storage.json')
    def __init__(self, opts):
        self.fname = opts.output
        self.old_manifest = []

    def filter_needed(self, in_fnames, worker):
        """Read existing JSON file, re-using previous results
        """
        if os.path.exists(self.fname):
            fp = file(self.fname, 'rb')
            data = json.load(fp)
            assert isinstance(data, list), "Bad data: %s" % type(data)
            self.old_manifest = data
            old_fnames = set([o['name'] for o in self.old_manifest])

            self.log.info("Old data read from %s", self.fname)
            return filter(lambda f: f not in old_fnames, in_fnames)
        else:
            return in_fnames

    def write_manifest(self, worker):
        self.old_manifest += worker.get_out_manifest()
        fp = open(self.fname, 'wb')
        json.dump(self.old_manifest, fp)
        fp.close()
        self.log.info("Results saved to %s", self.fname)

    def consume_manifests(self, worker, producer):
        for batch in producer:
            self.old_manifest += batch
            # inefficient to write the full JSON each time, but safe
            fp = open(self.fname, 'wb')
            json.dump(self.old_manifest, fp)
            fp.close()

class F3Storage(BaseStorageInterface):
    log = logging.getLogger('storage.f3')
    def __init__(self, opts):
        self.ssl_verify = True
        if opts.insecure:
            self.ssl_verify = False
        self.rsession = requests.Session()
        cj = cookielib.MozillaCookieJar()
        if opts.cookies_file and os.path.exists(opts.cookies_file):
            cj.load(opts.cookies_file)
        self.rsession.cookies = cj
        self.upload_url = opts.upload_to

    def filter_needed(self, in_fnames, worker):
        headers = {'Content-type': 'application/json', }
        post_data = {'mode': 'filter-needed', 'entries': in_fnames }
        for key in ('vol_label', 'uuid', 'fstype'):
            if key in worker.context:
                post_data[key] = worker.context[key]
        pres = self.rsession.post(self.upload_url, headers=headers,
                                  verify=self.ssl_verify,
                                  data=json.dumps(post_data)
                                 )
        pres.raise_for_status()
        data = pres.json()
        assert isinstance(data, list), type(data)
        return data

    def filter_checked(self, in_fnames, worker):
        headers = {'Content-type': 'application/json', }
        post_data = {'mode': 'filter-checked', 'entries': in_fnames }
        pres = self.rsession.post(self.upload_url, headers=headers,
                                  verify=self.ssl_verify,
                                  data=json.dumps(post_data)
                                 )
        pres.raise_for_status()
        data = pres.json()
        assert isinstance(data, list), type(data)
        return data

    def write_manifest(self, worker):
        self.consume_manifests(worker, [worker.get_out_manifest()])

    def consume_manifests(self, worker, producer):
        """Continuously write manifests, as generated by producer
        
            @param worker is used to setup storage parameters from
            @param producer a generator, which will yield lists of manifests.
                Each list will be written as soon as it is produced
        """
        headers = {'Content-type': 'application/json', }
        post_data = {'mode': 'upload', 'entries': None, 'final': False}
        url = self.upload_url
        for key in ('vol_label', 'uuid', 'fstype'):
            if key in worker.context:
                post_data[key] = worker.context[key]
        
        for batch in producer:
            batch_len = len(batch)
            if batch_len == 1:
                # Single-item parameters get simplified in Request Params handler
                batch = [batch[0], {}]
            post2 = post_data.copy()
            post2['entries'] = batch
            pres = self.rsession.post(url, headers=headers,
                                  verify=self.ssl_verify,
                                  data=json.dumps(post2)
                                 )
            pres.raise_for_status()
            self.log.info("Uploaded %d entries", batch_len)
            
        post2 = {'mode': 'upload', 'entries': [], 'final': True}
        pres = self.rsession.post(url, headers=headers,
                                  verify=self.ssl_verify,
                                  data=json.dumps(post2)
                                 )
        pres.raise_for_status()

    def lookup_fs(self, props):
        headers = {'Content-type': 'application/json', }
        post_data = {'mode': 'lookup',}
        post_data.update(props)
        pres = self.rsession.post(self.upload_url, headers=headers,
                                  verify=self.ssl_verify,
                                  data=json.dumps(post_data)
                                 )
        pres.raise_for_status()
        return pres.json()

def array2str(arr):
    if isinstance(arr, basestring):
        return arr
    if isinstance(arr, dbus.Array) and arr.signature == 'y':
        return ''.join(map(str, arr))
    elif isinstance(arr, dbus.Array):
        raise TypeError(arr.signature)
    else:
        raise TypeError(type(arr))

class UDisks2Mgr(object):
    ORG_UDISKS2 = '/org/freedesktop/UDisks2'
    DBUS_OBJMGR = 'org.freedesktop.DBus.ObjectManager'
    log = logging.getLogger('udisks2')

    class Drive(object):
        def __init__(self, obj, iprops=None):
            self._obj = obj
            if iprops is None:
                iprops = obj.GetAll('org.freedesktop.UDisks2.Drive', dbus_interface=dbus.PROPERTIES_IFACE)
    
        def eject(self):
            self._obj.Eject({}, dbus_interface='org.freedesktop.UDisks2.Drive')

        def is_ejectable(self):
            iface = dbus.Interface(self._obj, 'org.freedesktop.UDisks2.Drive')
            return iface.Ejectable

    def __init__(self):
        self._bus = dbus.SystemBus()
        self._drives = {}
        self._work_queue = []
        self._queue_lock = threading.Condition()

    def _setup_listeners(self):
        """Setup DBus callbacks for notifications
        """
        obj = self._bus.get_object("org.freedesktop.UDisks2", self.ORG_UDISKS2)
        obj.connect_to_signal('InterfacesAdded', self._interface_added, dbus_interface=self.DBUS_OBJMGR)
        obj.connect_to_signal('InterfacesRemoved', self._interface_removed, dbus_interface=self.DBUS_OBJMGR)

    def _interface_added(self, path, intf_properties):
        """Called by DBus when some drive or media is inserted
        """
        self.log.debug("added interface: %s", path)
        if not path.startswith(self.ORG_UDISKS2):
            return

        if 'org.freedesktop.UDisks2.Job' in intf_properties:
            pass
        elif 'org.freedesktop.UDisks2.Swapspace' in intf_properties:
            pass
        elif 'org.freedesktop.UDisks2.Drive' in intf_properties:
            self.log.debug("it is a drive")
            self.get_drive(path, intf_properties.get('org.freedesktop.UDisks2.Drive', None))
        elif 'org.freedesktop.UDisks2.Filesystem' in intf_properties:
            self.log.debug("it contains a filesystem")
            self._scan_filesystem(path, intf_properties)
        elif 'org.freedesktop.UDisks2.PartitionTable' in intf_properties:
            pass
        else:
            self.log.debug("unknown interface: %r", map(str, intf_properties.keys()))

    def _interface_removed(self, path, intfs):
        """ Called by DBus when some media is removed
        """
        if not path.startswith(self.ORG_UDISKS2):
            return
        self.log.debug("interface removed: %s %r", path, map(str, intfs))
        if 'org.freedesktop.UDisks2.Drive' in intfs:
            self._drives.pop(path, None)
        
        if 'org.freedesktop.UDisks2.Filesystem' in intfs:
            self._queue_lock.acquire()
            self._work_queue = filter(lambda t: t.path != path, self._work_queue)
            # no notify needed, queue will only shrink
            self._queue_lock.release()

    def main_loop(self, storage):
        """ This will start TWO threads: one for DBus signals and one for work-queue run
        
        """
        running = True
        def __glib_loop():
            loop = gobject.MainLoop()
            loop.run()
            
        def __work_loop():
            while running:
                self.log.debug("Work queue main-loop")
                task = None
                self._queue_lock.acquire()
                try:
                    if self._work_queue:
                        task = self._work_queue.pop(0)
                    else:
                        self._queue_lock.wait(60.0)
                except Exception:
                    self.log.exception("Cannot use work queue:")
                finally:
                    self._queue_lock.release()
                
                if task is None:
                    continue
                try:
                    task_thr = threading.Thread(target=task.execute, args=(storage,))
                    task_thr.start()
                except Exception:
                    self.log.exception("Cannot perform %s:", task, exc_info=True)

        thr = threading.Thread(target=__glib_loop)
        thr.daemon=True
        self._setup_listeners()
        self.log.info("Starting DBus loop")
        thr.start()
        
        thr2 = threading.Thread(target=__work_loop)
        thr2.daemon=True
        thr2.start()
        
        try:
            while True:
                time.sleep(10.0)
        except KeyboardInterrupt:
            pass
        self.log.info("Stopping.")
        running = False
        return

    def get_drive(self, path, i_props=None):
        if path not in self._drives:
            obj = self._bus.get_object("org.freedesktop.UDisks2", path)
            self.log.debug("need to scan drive: %s", path)
            self._drives[path] = UDisks2Mgr.Drive(obj, i_props)
        return self._drives[path]

    class EjectTask(object):
        def __init__(self, path, drive):
            self.path = path
            self.drive = drive

        def execute(self, storage):
            self.drive.eject()

    class ScanTask(object):
        log = logging.getLogger('tasks.scan')

        def __init__(self, path, drive, bus, block_props):
            self.path = path
            self.drive = drive
            self._bus = bus
            self.block_props = block_props
            
        def execute(self, storage):
            props = { 'vol_label': self.block_props['IdLabel'],
                       'uuid': self.block_props['IdUUID'],
                       'size': self.block_props['Size'],
                       'fstype': self.block_props['IdType'],
                       }
            device = array2str(self.block_props['Device'])
            try:
                res = storage.lookup_fs(props)
                if not res:
                    self.log.info("No need to scan %s",device )
                    return
                action = res.get('action', False)
            except requests.exceptions.RequestException, e:
                self.log.warning("Cannot lookup FS %s: %s", props['vol_label'], e)
                return
            except Exception, e:
                self.log.warning("Cannot lookup FS %s: %s", props['vol_label'], e, exc_info=True)
                return
    
            if action == 'scan':
                ret = self.scan_volume(storage, device)
            # elif action == 'rewind':
            #    return self.rewind(storage)
            else:
                self.log.warning("Unknown volume action: %s", action)
            
            if self.drive and self.drive.is_ejectable():
                time.sleep(1.0)
                self.drive.eject()
            
            return ret

        def scan_volume(self, storage, device):
            fs_obj = self._bus.get_object("org.freedesktop.UDisks2", self.path)
            iface = dbus.Interface(fs_obj, 'org.freedesktop.UDisks2.Filesystem')
            mount_opts = dbus.Dictionary({'ro': True}, 'sv')
            mpoint = iface.Mount(mount_opts)
            self.log.info("Mounted %s on %s", device, mpoint)

            worker = VolumeManifestor(label=self.block_props['IdLabel'],
                                      uuid=self.block_props['IdUUID'])
            worker.scan_dir(mpoint)

            umount_opts = dbus.Dictionary({}, 'sv')
            try:
                storage.consume_manifests(worker, worker.produce_sums())
                time.sleep(1.0)
                iface.Unmount(umount_opts)
            except KeyboardInterrupt:
                log.warning('Canceling MD5 scan by user request, will still save output in 2 sec')
                time.sleep(2.0) # User can hit Ctrl+C, again, here
                iface.Unmount(umount_opts)

    def _scan_filesystem(self, path, props):
        self.log.debug("filesystem scan: %s", path)
        fs_obj = self._bus.get_object("org.freedesktop.UDisks2", path)
        if 'org.freedesktop.UDisks2.Block' in props:
            block_props = props['org.freedesktop.UDisks2.Block']
        else:
            block_props = fs_obj.GetAll('org.freedesktop.UDisks2.Block', dbus_interface=dbus.PROPERTIES_IFACE)
        
        drive_path = block_props['Drive']
        self.log.debug("drive path: %s", drive_path)
        self.log.debug("Found new %(IdType)s fs \"%(IdLabel)s\" of %(Size)s (UUID: %(IdUUID)s)" % block_props)
        drive = self.get_drive(drive_path)
        with self._queue_lock:
            if block_props['IdType'] in ('iso9660', 'udf', 'vfat'):
                self._work_queue.append(UDisks2Mgr.ScanTask(path, drive, self._bus, block_props))
                self._queue_lock.notifyAll()
            else:
                self.log.info("Ignoring %s filesystem on %s", block_props['IdType'], array2str(block_props['Device']))
                if drive.is_ejectable:
                    self._work_queue.append(UDisks2Mgr.EjectTask(path, drive))
                self._queue_lock.notifyAll()

if options.opts.upload_to:
    storage = F3Storage(options.opts)
elif options.opts.output:
    storage = JSONStorage(options.opts)
elif options.opts.dry_run:
    storage = DryStorage(options.opts)
else:
    log.error("Must select storage mode: dry-run, output-file or upload-to URL")
    sys.exit(1)

comp_kwargs = {}
if options.opts.fast_run:
    comp_kwargs['time_limit'] = 10.0 # sec
    comp_kwargs['size_limit'] = pow(1024.0, 3)

if options.opts.mode == 'sources':
    worker = SourceManifestor(options.opts.prefix)
    for fpath in options.args:
        worker.scan_dir(fpath)

    worker.filter_in(storage)
    if options.opts.small_first:
        log.debug("Sorting by size")
        worker.sort_by_size()
    try:
        if options.opts.fast_run:
            worker.compute_sums(**comp_kwargs)
        else:
            storage.consume_manifests(worker, worker.produce_sums())
    except KeyboardInterrupt:
        log.warning('Canceling MD5 scan by user request, will still save output in 2 sec')
        time.sleep(2.0) # User can hit Ctrl+C, again, here

    if worker.out_manifest:
        storage.write_manifest(worker)
    else:
        log.warning("No manifest entries, nothing to save")

elif options.opts.mode == 'volume-dir':
    if len(options.args) != 2:
        log.error("Must supply 2 arguments: $0 <Label> <path>")
        sys.exit(1)
    
    worker = VolumeManifestor(label=options.args[0])
    worker.scan_dir(options.args[1])
    # no need to filter, assume we want a full scan, again
    
    if options.opts.small_first:
        log.debug("Sorting by size")
        worker.sort_by_size()
    
    try:
        worker.compute_sums(**comp_kwargs)
    except KeyboardInterrupt:
        log.warning('Canceling MD5 scan by user request, will still save output in 2 sec')
        time.sleep(2.0) # User can hit Ctrl+C, again, here

    if worker.manifest:
        storage.write_manifest(worker)
    else:
        log.warning("No manifest entries, nothing to save")

elif options.opts.mode in ('udisks', 'udisks2'):
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop, threads_init
    import gobject

    gobject.threads_init()
    threads_init()
    DBusGMainLoop(set_as_default=True)
    
    umgr = UDisks2Mgr()
    umgr.main_loop(storage)

elif options.opts.mode == 'move':
    worker = MoveManifestor(options.opts.prefix)
    for fpath in options.args:
        worker.scan_dir(fpath)

    worker.filter_in(storage)
    if worker.move_manifest:
        if not options.opts.outdir:
            log.error("Move mode requested but no output dir, aborting")
            sys.exit(1)
        worker.move_to(options.opts.outdir, dry=options.opts.dry_run)
    else:
        log.warning("No manifest entries, nothing to move")

else:
    log.error("Invalid mode: %s", options.opts.mode)
    sys.exit(1)

#eof
