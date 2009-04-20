#!/bin/bash

# 
# by P. Christeas, (c) 2008
# This is free software!

set -e
GPG_BIN=/usr/bin/gpg
GPG_CMD="nice -n 10 $GPG_BIN"

# run-parts from crond sets the HOME as /
if [ "$HOME" == "/" ] ; then
	export HOME=/root
fi

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

if [ "x$BACKUP_USE_GPG" != "xy" ] ; then
	exit 0
fi

if [ -z "${BACKUP_GPG_KEY}" ] ; then
	echo "Backup GPG key not specified"
	exit 2
fi

[ -d $BACKUP_DIR/gpg ] || mkdir "$BACKUP_DIR/gpg"

encrypt_file() {
	BASEFILE=$(basename "$1" .gz)
	
	OUTFILE="$BACKUP_DIR/gpg/$BASEFILE.gpg"
	TMCOUNT=1
	while [ -e "$OUTFILE" ] ; do
		if [ $TMCOUNT -gt 9 ] ; then
			echo "File $BASEFILE is encrypted $TMCOUNT files already." >&2
			return 1
		fi
		OUTFILE="$BACKUP_DIR/gpg/$BASEFILE-$TMCOUNT.gpg"
		TMCOUNT=$(expr $TMCOUNT '+' 1)
	done
	
	$GPG_CMD -o "$OUTFILE" -r ${BACKUP_GPG_KEY} -e "$1" && \
		rm -f "$1"
}

for FILE in $BACKUP_DIR/incoming/*.gz ; do
	# if no incoming file, next check will fail
	[ ! -f "$FILE" ] && continue
	encrypt_file "$FILE"
done

if [ -d ${BACKUP_DIR}/pgsql/wals ] ; then
	for FILE in $BACKUP_DIR/pgsql/wals/* ; do
		encrypt_file "$FILE"
	done
fi

#eof

