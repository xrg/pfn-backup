#!/bin/bash
# 
# Copyright (C) P. Christeas <p_christ@hol.gr>, 2008
# This is free software.
#

# exit on any non-handled error
set -e

PGSQL_BACKUP_USER=postgres
PGSQL_BACKUP_DB=postgres

. /etc/backup/options

PGDATA=/var/lib/pgsql/data
LOGFILE=/var/log/postgres/postgresql
NAME=postgresql

[ -f /etc/sysconfig/postgresql ] && . /etc/sysconfig/postgresql

[ -f /etc/sysconfig/pgsql/${NAME} ] && . /etc/sysconfig/pgsql/${NAME}

# this dir must exist
[ -d $PGDATA ]

PSQL="/usr/bin/psql -U ${PGSQL_BACKUP_USER} -d ${PGSQL_BACKUP_DB}"
DSTAMP=$(date +'%Y%m%d')

[ -d "$BACKUP_DIR/pgsql" ]

# we do name a capital P to avoid conflict with any other backup

TAR_FILE="$BACKUP_DIR/backup-Pgsql-full-$DSTAMP.tar"


$PSQL -c "SELECT pg_start_backup('full_$DSTAMP');"
tar -cvf ${TAR_FILE} --exclude=pg_xlog $PGDATA/
$PSQL -c "SELECT pg_stop_backup();"
sleep 20
tar -rvf ${TAR_FILE} ${BACKUP_DIR}/pgsql/wals
gzip ${TAR_FILE}
mv ${TAR_FILE}.gz "$BACKUP_DIR/incoming"

# do that as quicly (atomic) as possible. Still, the pgsql_archive.sh will
# tolerate a missing wals/ 

mv ${BACKUP_DIR}/pgsql/wals ${BACKUP_DIR}/pgsql/wals.old
mkdir ${BACKUP_DIR}/pgsql/wals.new
chown postgres ${BACKUP_DIR}/pgsql/wals.new
chmod -R o-rwx ${BACKUP_DIR}/pgsql/wals.new
mv ${BACKUP_DIR}/pgsql/wals.new ${BACKUP_DIR}/pgsql/wals

# we have backed them up, remove them.
rm -rf ${BACKUP_DIR}/pgsql/wals.old

echo "Done!"
#eof
