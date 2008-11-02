#!/bin/bash

# 
# by P. Christeas, (c) 2008
# This is free software!

set -e

. /etc/backup/options || ( echo "Default options not found, exiting" ; exit 1)

[ -n ${BACKUP_GPG_KEY} ] || ( echo  "Backup GPG key not specified" ; exit 2 )

[ -d $BACKUP_DIR/gpg ] || mkdir "$BACKUP_DIR/gpg"

for FILE in $BACKUP_DIR/incoming/*.gz ; do
	gpg -o $BACKUP_DIR/gpg/$(basename $FILE) -r ${BACKUP_GPG_KEY} -e $FILE && \
		rm $FILE
done 

#eof

