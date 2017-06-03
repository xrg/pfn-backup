#!/bin/bash

set -e

function decho {
 if [ "$VERBOSE" == "y" ] ; then
	echo "$@"
 fi
}

TMP_TAR_OPTIONS=""
TMP_TAR_FILE=/dev/null
TMP_TAR_DIRS=""
TRASH_MAILBOX=".EXPUNGED/"
TRASH_DIR=~/.doveTrash
VERBOSE=


while [ -n "$1" ] ; do

	case "$1" in
	 '--dry-run')
		DRY_RUN=y
		;;
	'--fcode')
		FCODE="$2"
		shift 1
	;;
	'--config')
		TMP_CFGFILE="$2"
		shift 1
	;;
	'-v')
		VERBOSE=-v
	;;
	*)
		[ -n "$1" ] && \
		 TMP_TAR_DIRS="$TMP_TAR_DIRS $1"
	;;
	esac
	shift 1
done

[ -r /etc/backup/options ] && . /etc/backup/options && decho "Loading options from /etc/backup/options"
 if [ -n "$TMP_CFGFILE" ]; then
	decho "Loading options from $TMP_CFGFILE"
	. "$TMP_CFGFILE"	
else
	[ -r ~/.backupoptions ] && . ~/.backupoptions && decho "Loading options from ~/.backupoptions"
fi

# Create two stamps, one for the filename, and one for the index file
DSTAMP=$(date +'%Y%m%d')
TSTAMP=$(date -Iminute)

decho "First: cleaning duplicates in $TRASH_MAILBOX"
doveadm $VERBOSE deduplicate mailbox "$TRASH_MAILBOX*"

if [ ! -n "$TAR_FILE_BASE" ] ; then
	if [ -n "$BACKUP_DIR" ] ; then
	TAR_FILE_BASE="$BACKUP_DIR/incoming/backup"
	else
	TAR_FILE_BASE="/tmp/backup"
	fi
fi

TMP_LIST=$(mktemp)

TMP_TAR_FILE="${TAR_FILE_BASE}-dovetrash-$USER-$DSTAMP.tar.xz"

decho "Second: archiving $TRASH_DIR into $TMP_TAR_FILE"
pushd $TRASH_DIR > /dev/null
    find -type f -ctime +7 -regextype posix-extended \
        -regex '.*/cur/[0-9]{9}.*,S' > "$TMP_LIST"
    if [ -n "$DRY_RUN" ] ; then
        echo "List of mails is at $TMP_LIST"
    else
        tar $VERBOSE -cf $TMP_TAR_FILE --xz --remove-files -T "$TMP_LIST"
        rm -f "$TMP_LIST"
    fi
popd

#eof
