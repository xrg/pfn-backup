#!/bin/bash

# 
# by P. Christeas, (c) 2008
# This is free software!

set -e
GPG_BIN=/usr/bin/gpg
GPG_CMD="nice -n 10 $GPG_BIN"

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

if [ "x$BACKUP_USE_GPG" != "xy" ] ; then
	exit 0
fi

if [ -z "${BACKUP_GPG_KEY}" ] ; then
	echo "Backup GPG key not specified"
	exit 2
fi

[ -d $BACKUP_DIR/gpg ] || mkdir "$BACKUP_DIR/gpg"

for FILE in $BACKUP_DIR/incoming/*.gz ; do
	$GPG_CMD -o $BACKUP_DIR/gpg/$(basename $FILE).gpg -r ${BACKUP_GPG_KEY} -e $FILE && \
		rm $FILE
done

if [ -d ${BACKUP_DIR}/pgsql/wals ] ; then
	for FILE in $BACKUP_DIR/pgsql/wals/* ; do
		$GPG_CMD -o $BACKUP_DIR/gpg/$(basename $FILE).gpg -r ${BACKUP_GPG_KEY} -e $FILE && \
			rm $FILE
	done
fi

#eof

