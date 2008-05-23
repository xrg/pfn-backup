#!/bin/bash

#!/bin/bash

# by P. Christeas, (c) 2005-6
# This is free software!


FS_LABEL='Backup'
DO_BEEP=yes
BEEP_OPTS="-e /dev/tty0"
MNTPOINT=/mnt/backup
OUT='/bin/logger -t backup'
FOUND_LABEL=""
FOUND_DEVICE="/dev/disk/by-label/$FS_LABEL"
DO_VERBOSE=
BKUP_SRC=/koina/home/backup/
BKUP_DEST=/upload/$(hostname)
RSYNC_OPTS=
# RSYNC_OPTS="--delete"

[ -f /etc/backup/sync-removable.conf ] && \
	. /etc/backup/sync-removable.conf


while getopts "qfd:l:v" OPTION ; do
	case $OPTION in
	q)
		DO_BEEP=
	;;
	f)
		OUT=cat
	;;
	d)
		FOUND_DEVICE="/dev/$OPTARG"
	;;
	l)
		FOUND_LABEL="$OPTARG"
	;;
	v)
		DO_VERBOSE=y
	;;
	esac
done


if [ "$FOUND_LABEL" != "$FS_LABEL" ] ; then
	[ "$DO_VERBOSE" == 'y' ] && (echo "Label mismatch" | $OUT )
	exit
fi

if [ ! -d "$MNTPOINT" ] ; then
	mkdir "$MNTPOINT" | $OUT
fi

if [ ! -b "$FOUND_DEVICE" ] ; then
	[ "$DO_VERBOSE" == 'y' ] && (echo "Bkup dev not there, waiting 1 sec" | $OUT )
	sleep 10

	if [ ! -b "$FOUND_DEVICE" ] ; then
		echo "Backup dev '$FOUND_DEVICE' not present" | $OUT
# 		exit 0
	fi
fi

if ! mount -t ext3 "$FOUND_DEVICE" $MNTPOINT | $OUT ; then
	exit 1
fi

[ ! -z "$DO_BEEP" ] && beep -f 1000 -n -f 10 -l 50 -n -f 2000 -n -d 10 -l 100 $BEEP_OPTS

BEEP_CMD='cat'
if [ ! -z "$DO_BEEP" ] ; then
	BEEP_CMD="beep -s -f 400 -D 20 -l 10 $BEEP_OPTS"
fi

if [ -f $MNTPOINT/signature ] && cmp /root/signature $MNTPOINT/signature ; then
	echo "Performing backup!" | $OUT
	nice -n 10 rsync -a $RSYNC_OPTS -P -q "$BKUP_SRC" "$MNTPOINT/$BKUP_DEST" | $BEEP_CMD | $OUT
	umount $MNTPOINT | $OUT
	echo "Sync done,USB can be removed." | $OUT
	[ ! -z "$DO_BEEP" ] && beep -f 2000 -n -f 10 -l 50 -n -f 1000 $BEEP_OPTS
else
	echo "Signature not found! Disk may be spoofed!" | $OUT
	umount $MNTPOINT | $OUT
	[ ! -z "$DO_BEEP" ] && beep -f 200 -l 500 $BEEP_OPTS
	exit 2
fi

#eof

