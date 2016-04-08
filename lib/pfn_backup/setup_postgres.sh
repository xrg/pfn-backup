#!/bin/bash

# 
# Copyright (C) P. Christeas <xrg@hellug.gr>, 2008-2015
# This is free software.
#

# Note, this may be Postgres 8.3 specific.

# exit on any non-handled error
set -e

parse_pg_conf() {
	sed 's/#.*$//' | grep -v '^[[:space:]]*$' | \
	sed -e 's/[[:space:]]*=[[:space:]]*/ = /'
}

mk_backup_dir() {
	. /etc/backup/options
	[ -d ${BACKUP_DIR}/pgsql/wals ] || \
		mkdir -p ${BACKUP_DIR}/pgsql/wals
	chown postgres ${BACKUP_DIR}/pgsql ${BACKUP_DIR}/pgsql/wals
	chmod -R o-rwx ${BACKUP_DIR}/pgsql
}

if [ "$1" == "-f" ] ; then
	FORCE=y
	shift 1
fi

PGDATA=/var/lib/pgsql/data
LOGFILE=/var/log/postgres/postgresql
NAME=postgresql
PFN_SHDIR=$(dirname $0)

[ -f /etc/sysconfig/postgresql ] && . /etc/sysconfig/postgresql

[ -f /etc/sysconfig/pgsql/${NAME} ] && . /etc/sysconfig/pgsql/${NAME}

# this dir must exist
[ -d $PGDATA ]

if ! cat ${PGDATA}/postgresql.conf | parse_pg_conf | grep 'archive_mode = on' ; then

	if [ "$FORCE" != "y" ] && service ${NAME} status > /dev/null  ; then
		echo 'This script should not be run with postgres running.'
		echo 'Please, stop the server and try again.'
		exit 3
	fi
	
	echo "Patching ${PGDATA}/postgresql.conf"

	sed -i.bak "s/#archive_mode\s*=\s*/archive_mode = on/;s/#archive_command\s*=\s*''.*/archive_command = '\/usr\/lib\/pfn_backup\/pgsql_archive.sh \"%p\"'/;s/#archive_timeout\s*=\s*0/archive_timeout = 600/;s/#wal_level\s*=\s*minimal/wal_level = archive/" ${PGDATA}/postgresql.conf
	
fi


mk_backup_dir

#eof
