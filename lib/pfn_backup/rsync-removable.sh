#!/bin/bash

#!/bin/bash

# by P. Christeas, (c) 2005-6
# This is free software!

set -e

FS_LABEL=''
DO_BEEP=yes
BEEP_CMD=true
BEEP_OPTS="-e /dev/tty0"
MNTPOINT=/mnt/backup
OUT='/bin/logger -t backup'
FOUND_LABEL="$HAL_PROP_VOLUME_LABEL"
FOUND_DEVICE="$HAL_PROP_BLOCK_DEVICE"
DO_VERBOSE=
BKUP_SRC=/var/backup/
BKUP_DEST=/upload/$(hostname)
RSYNC_OPTS=
# RSYNC_OPTS="--delete"

[ -f /etc/backup/options ] && \
	. /etc/backup/options


while getopts "qfd:l:v" OPTION ; do
	case $OPTION in
	q)
		DO_BEEP=
	;;
	f)
		OUT=cat
	;;
	d)
		FOUND_DEVICE="$OPTARG"
	;;
	l)
		FOUND_LABEL="$OPTARG"
	;;
	v)
		DO_VERBOSE=y
	;;
	esac
done

if [ ! -b "$FOUND_DEVICE" ] ; then
	echo "Device \"$FOUND_DEVICE\" is not a block one!"
	exit 3
fi

if [ -n "$BACKUP_DIR" ] ; then
	BKUP_SRC="$BACKUP_DIR/gpg"
fi

if [ "$DO_BEEP" == "yes" ] ; then
	 BEEP_CMD="$(which beep) $BEEP_OPTS"
fi

if [ -n "$FS_LABEL" ] && [ "$FOUND_LABEL" != "$FS_LABEL" ] ; then
	[ "$DO_VERBOSE" == 'y' ] && (echo "Label mismatch" | $OUT )
	exit
fi

if [ ! -d "$MNTPOINT" ] ; then
	mkdir "$MNTPOINT" | $OUT
fi

mount "$FOUND_DEVICE" $MNTPOINT | $OUT

$BEEP_CMD -f 1000 -n -f 10 -l 50 -n -f 2000 -n -d 10 -l 100

BEEP_CMD2="$BEEP_CMD -s -f 400 -D 20 -l 10"

if [ -f $MNTPOINT/signature ] && cmp /root/signature $MNTPOINT/signature ; then
	echo "Performing backup!" | $OUT
	[ "$DO_VERBOSE" == 'y' ] && (echo "rsync a $RSYNC_OPTS -P -q $BKUP_SRC $MNTPOINT/$BKUP_DEST" | $OUT )
	nice -n 10 rsync -a $RSYNC_OPTS -P -q "$BKUP_SRC" "$MNTPOINT/$BKUP_DEST" | $BEEP_CMD2 2| $OUT
	umount $MNTPOINT | $OUT
	echo "Sync done,USB can be removed." | $OUT
	$BEEP_CMD -f 2000 -n -f 10 -l 50 -n -f 1000
else
	sleep 1
	echo "Signature not found! Disk may be spoofed!" | $OUT
	umount $MNTPOINT | $OUT || true
	$BEEP_CMD -f 200 -l 500
	exit 2
fi

#eof

