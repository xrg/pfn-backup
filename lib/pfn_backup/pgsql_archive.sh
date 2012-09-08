#!/bin/bash
# 
# Copyright (C) P. Christeas <xrg@hellug.gr>, 2008
# This is free software.
#

# exit on any non-handled error

set -e

. /etc/backup/options

WAL_ARCHIVE=$(basename "$1")

[ -d ${BACKUP_DIR}/pgsql/wals ]
if [ -f ${BACKUP_DIR}/pgsql/wals/${WAL_ARCHIVE} ] ; then
	echo "File already exists!"
	exit 1
fi

nice -n 6 cp -a "$1" ${BACKUP_DIR}/pgsql/wals/${WAL_ARCHIVE}
nice -n 6 gzip ${BACKUP_DIR}/pgsql/wals/${WAL_ARCHIVE}

#eof