# Pfn backup

Pfn-backup is a set of shell (bash) scripts that direct GNU tar into
making your everyday backups. Backups are stored on some local 
filesystem, which is then mirrored to any remote media.

## Design principles

Pfn backup:

* uses existing tools, no custom binaries or long scripts
* heavily depends on capabilities of `tar` , which was built for
backups on the first place
* requires NO custom procedures to restore backups. You can open
them on any machine, just don't loose your GPG key!
* works offline, does not assume the final backup media is always
available
* has an incremental mode, takes backups often, but with minimal
size of each one.

## How it works

Pfn backup is just scripts. It's a way to call `tar` every day / week
/ month and keep these archives in a reasonable order.

It works in 3 stages:
 - prepares backups on a *local* disk, on fixed intervals (eg. daily)
 - optionally encrypt the archives with your GPG key
 - sends or copies these archives to the backup media, whenever
available.

All these steps are incremental and repeatable, you can take extra
backups or skip a step (on error), next time the scripts are run will
cover the missing ones.

### Foreword: internals, setup

Pfn-backup uses 3 locations on your (unix) system to store its configuration
and data:

1. `/etc/backup` to store all config files, namely `/etc/backup/all.cfg`
    and `/etc/backup/options` , for a start.
2. `/var/backup/index` is a machine log of backups taken, used as a reference
    for incremental archives.
3. `/<some-path>/backup/` set of folders, where backups and encrypted archives
    are placed
    * `/<some-path>/backup/incoming`  holds temp. unencrypted tars
    * `/<some-path>/backup/gpg` holds encrypted tars, can be rsynced to out
    * `/<some-path>/backup/pgsql` holds unencrypted Postgres WALs

### Step 1: preparation of tars

Each night (ideally), `all-backup.sh` will run and perform a set of `tar` runs.
Prepares one tar per user, or "partition" of data.
eg. standard configuration has:
* one ".tar" per user covered
* an archive for `/var/`
* an archive for `/etc/`
* (optionally) more archives for custom paths or sub-paths containing large amount
of data

Unlike other backup solutions, we only depend on `tar` to do file-selection and
path traversal. A single pass through our filesystem(s), for performance.

pfn-backup takes each line of `all.cfg` and executes `user-backup.sh` for them.
`user-backup.sh` runs as suid for each user (if needed) and performs `tar` for
the set of files in the configuration. It logs start and finish times in
`/var/backup/index`

Unless the `--full` option is given, `user-backup.sh` will only select files that
have been modified since last run (as seen in `/var/backup/index` ).

File selection can be fine-grained using any of the `tar` options available.

> In that context, I have long maintained the custom `auto-exclude` option in
> `tar`, which can further limit number of files considered. But that is *not*
> a requirement for pfn-backup operation.

Each month, `/var/backup/index` is rotated. This means, no reference will exist
for incremental mode, and thus next run will take full backups.

### Step 2: encryption

Simple, if you set:
```
BACKUP_USE_GPG=y
BACKUP_GPG_KEY=<0xYour-key>
```
in `/etc/backup/options` , this script will attempt to encrypt each file in
`/<some-path>/backup/incoming` moving it into `/<some-path>/backup/gpg/`

Then, you know that all files in `/<some-path>/backup/gpg/` are ready to
transport or copy to the final backup media. As long as your GPG key is safe,
you shall not worry about security of the transport mechanism or backup media
you use (just don't lose them!).

### Step 3: store to a safe place

You can put a manual `rsync` command after `all-backup.sh` and `backup-encrypt.sh`
are run, to send those files to any other storage you consider reliable enough.

You can use any other, custom, way to transport those files, HTTP PUT, upload
or even `tar` again to magnetic tapes (say).

In case your backup media is damaged/lost, you could make a second copy of
`/<some-path>/backup/gpg/` .

There is a helper `HAL` -based script which would copy the encrypted archives
onto a USB disk (or storage), whenever a *signed* device would attach to this
computer. This was used in standalone machines, where I wanted to plug the disk,
wait a little, and take the disk out with the backups in it, no console or GUI
interaction.

Feel free to develop your own copy scripts.

## Copyright, legal

pfn-backup is free, as in "I don't really care whatever you do with it"

In that context, I - or any other contributors - take **no** responsibility
whatsoever about your data and the way you store them using this tool. It's
absolutely **your** duty to configure it correctly and verify that your
backups contain the files you meant to preserve, are copied to a reliable
place and your GPG key is handled properly.

