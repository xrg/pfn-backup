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

GPG_BACKUP_DIR="$BACKUP_DIR/gpg"
if [ "x$BACKUP_GPG_MONTH" == "xy" ] ; then
	GPG_BACKUP_DIR+="$(date +'/%Y%m')"
fi

[ -d "$GPG_BACKUP_DIR" ] || mkdir "$GPG_BACKUP_DIR"

encrypt_file() {
	BASEFILE=$(basename "$1" "$2")
	
	OUTFILE="$GPG_BACKUP_DIR/$BASEFILE.gpg"
	TMCOUNT=1
	while [ -e "$OUTFILE" ] ; do
		if [ $TMCOUNT -gt 9 ] ; then
			echo "File $BASEFILE is encrypted $TMCOUNT files already." >&2
			return 1
		fi
		OUTFILE="$GPG_BACKUP_DIR/$BASEFILE-$TMCOUNT.gpg"
		TMCOUNT=$(expr $TMCOUNT '+' 1)
	done
	
	$GPG_CMD -o "$OUTFILE" -r ${BACKUP_GPG_KEY} -e "$1" && \
		rm -f "$1"
}

for EXT in '.gz' '.xz' '.bz2' ; do
  find $BACKUP_DIR/incoming -type f -name '*'$EXT | \
        while read FILE ; do encrypt_file "$FILE" "$EXT" ; done
done

if [ -d ${BACKUP_DIR}/pgsql/wals ] ; then
  find $BACKUP_DIR/pgsql/wals/ -type f | \
        while read FILE ; do encrypt_file "$FILE" ; done
fi

#eof

