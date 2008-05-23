#!/bin/bash

# by P. Christeas, (c) 2005-6
# This is free software!


FS_LABEL='Backup_home'
DO_BEEP=yes
MNTPOINT=/mnt/backup

OUT=cat
if [ "$1" == '-s' ] ; then
	OUT='/bin/logger -t backup'
	shift 1
fi

if [ "$1" == "-q" ] ; then
	DO_BEEP=
fi

if [ ! -d "$MNTPOINT" ] ; then
	mkdir "$MNTPOINT" | $OUT
fi


if [ ! -b /dev/disk/by-label/$FS_LABEL ] ; then
	echo "Backup dev not present" | $OUT
	exit 0
fi

(mount -t ext3 /dev/disk/by-label/$FS_LABEL $MNTPOINT | $OUT ) || exit 1

[ ! -z "$DO_BEEP" ] && beep -f 1000 -n -f 10 -l 50 -n -f 2000 -n -d 10 -l 100 -e /dev/tty0

BEEP_CMD='cat'
if [ ! -z "$DO_BEEP" ] ; then
 BEEP_CMD='beep -s -f 400 -D 20 -l 10 -e /dev/tty0'
fi

if [ -f $MNTPOINT/signature ] && cmp /root/signature $MNTPOINT/signature ; then
	echo "Performing backup!" | $OUT
	rsync -ah --delete  -P -q /home $MNTPOINT | $BEEP_CMD | $OUT
	umount $MNTPOINT | $OUT
	echo "Sync done,USB can be removed." | $OUT
	[ ! -z "$DO_BEEP" ] && beep -f 2000 -n -f 10 -l 50 -n -f 1000 -e /dev/tty0
else
	echo "Signature not found! Disk may be spoofed!" | $OUT
	umount $MNTPOINT | $OUT
	[ ! -z "$DO_BEEP" ] && beep -f 200 -l 500 -e /dev/tty0
	exit 2
fi

#eof

