#!/bin/bash

# global backup
# by P. Christeas, (c) 2005-6
# This is free software!

set -e

#defaults:
BACKUP_NICELEVEL=10
BACKUP_ALL_TFILE=/etc/backup/all.cfg
BACKUP_POSTGRES_FULL_SH=/usr/lib/pfn_backup/pgsql_full_backup.sh

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

if [ ! -d $BACKUP_DIR/incoming ] ; then
	mkdir -p "$BACKUP_DIR/incoming"
	[ -n "$BACKUP_GROUP" ] && chgrp "$BACKUP_GROUP" "$BACKUP_DIR/incoming"
	chmod ug+w "$BACKUP_DIR/incoming"
fi
if [ ! -e "$BACKUP_INDEX_FILE" ] ; then
	echo > "$BACKUP_INDEX_FILE"
	[ -n "$BACKUP_GROUP" ] && chgrp "$BACKUP_GROUP" "$BACKUP_INDEX_FILE"
	chmod ug+w "$BACKUP_INDEX_FILE"
fi

NICE_CMD=""
if [ -n "$BACKUP_NICELEVEL" ] ; then
	NICE_CMD="nice -n $BACKUP_NICELEVEL"
fi

GT_EXIT=0

if tail -n 3 "$BACKUP_INDEX_FILE" | grep "^Need full postgres backup" > /dev/null ; then
	$BACKUP_POSTGRES_FULL_SH || EXIT_CODE=$?
	if [ "$EXIT_CODE" != 0 ]  ; then
		echo $BACKUP_POSTGRES_FULL_SH
		echo "Exit code: $EXIT_CODE for full Postgres backup."
		if [ "$GT_EXIT" -lt "$EXIT_CODE" ] ; then
			GT_EXIT=$EXIT_CODE
		fi
	fi
fi

grep -v '^#' $BACKUP_ALL_TFILE | \
grep -v '^$' | \
while read B_USER B_LINE ; do
	if [ "$B_USER" == 'root' ] ; then
		EXIT_CODE=0
		$NICE_CMD $USER_BACKUP $B_LINE $@ || EXIT_CODE=$?
		if [ "$EXIT_CODE" != 0 ]  ; then
			echo "Exit code: $EXIT_CODE from line $B_LINE."
			if [ "$GT_EXIT" -lt "$EXIT_CODE" ] ; then
				GT_EXIT=$EXIT_CODE
			fi
		fi
	else
		EXIT_CODE=0
		su $B_USER -s /bin/bash -c "$NICE_CMD ${USER_BACKUP} ${B_LINE} $@" || EXIT_CODE=$?
		if [ "$EXIT_CODE" != 0 ]  ; then
			echo "Exit code: $EXIT_CODE from user $B_USER."
			if [ "$GT_EXIT" -lt "$EXIT_CODE" ] ; then
				GT_EXIT=$EXIT_CODE
			fi
		fi
	fi
done

exit "$GT_EXIT"

#eof
