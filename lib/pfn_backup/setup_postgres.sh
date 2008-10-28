#!/bin/bash

# 
# Copyright (C) P. Christeas <p_christ@hol.gr>, 2008
# This is free software.
#

# exit on any non-handled error
set -e

parse_pg_conf() {
	sed 's/#.*$//' | grep -v '^[[:space:]]*$' | \
	sed -e 's/[[:space:]]*=[[:space:]]*/ = /'
}

mk_backup_dir() {
	. /etc/backup/options
	[ ! -d ${BACKUP_DIR}/pgsql/wals ] || \
		mkdir -p ${BACKUP_DIR}/pgsql/wals
	chown postgres ${BACKUP_DIR}/pgsql ${BACKUP_DIR}/pgsql/wals
	chmod -R o-rwx ${BACKUP_DIR}/pgsql
}

PGDATA=/var/lib/pgsql/data
LOGFILE=/var/log/postgres/postgresql
NAME=postgresql
PFN_SHDIR=$(dirname $0)

[ -f /etc/sysconfig/postgresql ] && . /etc/sysconfig/postgresql

[ -f /etc/sysconfig/pgsql/${NAME} ] && . /etc/sysconfig/pgsql/${NAME}

# this dir must exist
[ -d $PGDATA ]

if ! cat ${PGDATA}/postgresql.conf | parse_pg_conf | grep 'archive_mode = on' ; then

	if /etc/init.d/${NAME} status > /dev/null  ; then
		echo 'This script should not be run with postgres running.'
		echo 'Please, stop the server and try again.'
		exit 3
	fi
	
	echo "Patching ${PGDATA}/postgresql.conf"

	cp -a ${PGDATA}/postgresql.conf ${PGDATA}/postgresql.conf.bak
	
	patch -p 1 -l ${PGDATA}/postgresql.conf ${PFN_SHDIR}/postgres.conf.patch
	
fi


mk_backup_dir

#eof
