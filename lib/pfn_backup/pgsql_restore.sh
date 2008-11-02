#!/bin/bash
# 
# Copyright (C) P. Christeas <p_christ@hol.gr>, 2008
# This is free software.
#

# exit on any non-handled error

set -e

. /etc/backup/options

WAL_ARCHIVE=$(basename "$1")

[ -d ${BACKUP_DIR}/pgsql/wals ]

if [ ! -f ${BACKUP_DIR}/pgsql/wals/${WAL_ARCHIVE}.gz ] ; then
	echo "File ${WAL_ARCHIVE}.gz doesn't exist"
	exit 2
fi

cat ${BACKUP_DIR}/pgsql/wals/${WAL_ARCHIVE}.gz | gunzip -c > "$2"

#eof