#!/bin/bash
# 
# Copyright (C) P. Christeas <xrg@hellug.gr>, 2008
# This is free software.
#

# exit on any non-handled error
set -e
trap 'echo Error at $0:$LINENO $BASH_COMMAND >&2 ; exit' ERR SIGINT SIGQUIT

function decho {
 if [ "$VERBOSE" == "y" ] ; then
	echo "$@"
 fi
}

PGSQL_BACKUP_USER=postgres
PGSQL_BACKUP_DB=postgres

. /etc/backup/options

PGDATA=/var/lib/pgsql/data
LOGFILE=/var/log/postgres/postgresql
NAME=postgresql

while [ -n "$1" ] ; do

	case "$1" in
	'-v')
		VERBOSE=y
	;;
	esac
	shift 1
done

[ -f /etc/sysconfig/postgresql ] && . /etc/sysconfig/postgresql

[ -f /etc/sysconfig/pgsql/${NAME} ] && . /etc/sysconfig/pgsql/${NAME}

# this dir must exist
[ -d $PGDATA ]

DSTAMP=$(date +'%Y%m%d')
TSTAMP=$(date -Iminute)

[ -d "$BACKUP_DIR/pgsql" ]

# we do name a capital P to avoid conflict with any other backup

TAR_FILE="$BACKUP_DIR/incoming/backup-Pgsql-full-$DSTAMP.tar.gz"

[ -n "$BACKUP_INDEX_FILE" ] && \
	echo "$TSTAMP" 'Pgsql' "Backup started now. full_$DSTAMP" >> "$BACKUP_INDEX_FILE"

decho "Starting backup.."
pg_basebackup -D "$BACKUP_DIR/pgsql/full-$DSTAMP" -F plain -R -U $PGSQL_BACKUP_USER

tar -czf ${TAR_FILE} -C "$BACKUP_DIR/pgsql/full-$DSTAMP" ./
rm -rf "$BACKUP_DIR/pgsql/full-$DSTAMP"

[ -n "$BACKUP_INDEX_FILE" ] && \
	echo "$TSTAMP" $TAR_FILE Pgsql "success at" $(date) "." >> "$BACKUP_INDEX_FILE"

decho "Finished full Postgres backup!"
#eof
