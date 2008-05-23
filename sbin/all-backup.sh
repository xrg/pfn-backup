#!/bin/bash

# global backup

#defaults:
BACKUP_ALL_TFILE=/etc/backup/all.cfg

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

if [ ! -d $BACKUP_DIR ] ; then
	mkdir -p "$BACKUP_DIR"
	[ -n "$BACKUP_GROUP" ] && chgrp "$BACKUP_GROUP" "$BACKUP_DIR"
	chmod ug+w "$BACKUP_DIR"
fi
if [ ! -e "$BACKUP_INDEX_FILE" ] ; then
	echo > "$BACKUP_INDEX_FILE"
	[ -n "$BACKUP_GROUP" ] && chgrp "$BACKUP_GROUP" "$BACKUP_INDEX_FILE"
	chmod ug+w "$BACKUP_INDEX_FILE"
fi

grep -v '^#' $BACKUP_ALL_TFILE | \
grep -v '^$' | \
while read B_USER B_LINE ; do
	if [ "$B_USER" == 'root' ] ; then
		$USER_BACKUP $B_LINE $@
	else
		su $B_USER -c "${USER_BACKUP} ${B_LINE} $@"
	fi
done


#eof
