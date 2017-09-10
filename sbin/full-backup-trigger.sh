#!/bin/bash

# global backup
# by P. Christeas, (c) 2005-6
# This is free software!

set -e

#defaults:
BACKUP_NICELEVEL=10
BACKUP_ALL_TFILE=/etc/backup/all.cfg

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

DSTAMP=$(date +'%Y%m%d%H%M')

if [ -e "$BACKUP_INDEX_FILE" ] ; then
   BACK_2_INDEX="$BACKUP_INDEX_FILE.$DSTAMP"
   if [ -e "$BACK_2_INDEX" ] ; then
   	echo "Index already backed up to $BACK_2_INDEX, not wise to continue"
   	exit 1
   fi
   
   mv "$BACKUP_INDEX_FILE" "$BACK_2_INDEX"
fi

#TODO: a better cross-distro check for postgres
if [ -e "/etc/init.d/postgresql" ] || which postgres > /dev/null ; then
	echo "Need full postgres backup" > "$BACKUP_INDEX_FILE"
else
	echo > "$BACKUP_INDEX_FILE"
fi

[ -n "$BACKUP_GROUP" ] && chgrp "$BACKUP_GROUP" "$BACKUP_INDEX_FILE"
chmod ug+w "$BACKUP_INDEX_FILE"

echo "Requested a full backup, now run 'all-backup.sh' to take it!"

#eof