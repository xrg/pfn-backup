#!/bin/bash

# global backup
# by P. Christeas, (c) 2005-6
# This is free software!

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

# Quick and dirty set of root's home, so that gpg works
if [ -z $HOME ] ; then
	export HOME=/root
fi
for FILE in $BACKUP_DIR/*.gz ; do 
	gpg -o $BACKUP_DIR/gpg/$(basename $FILE) -r 'my_key' -e $FILE && \
       		rm $FILE
done 

#eof
