#!/bin/bash

# User backup, by P. Christeas, (c) 2005-6
# This is free software!


function decho {
 if [ "$VERBOSE" == "y" ] ; then
	echo "$@"
 fi
}

# params <index_file> <code>
function get_lastdate {
	grep "$2 success at" "$1" | tail -n 1 | cut -d ' ' -f 1 | sed 's/T/ /'
}

# Filter some things from tar
function filter_tar {
	grep -v 'file is unchanged; not dumped' | \
	grep -v 'socket ignored'
	return 0
}

TMP_TAR_OPTIONS=""
TMP_TAR_FILE=/dev/null
TMP_TAR_DIRS=""

while [ -n "$1" ] ; do

	case "$1" in
	 '--dry-run')
		DRY_RUN=y
		;;
	'--full')
		FULL_BKUP=y
		;;
	'--code')
		TMP_CODE="$2"
		FCODE="$2"
		shift 1
	;;
	'--fcode')
		FCODE="$2"
		shift 1
	;;
	'--config')
		TMP_CFGFILE="$2"
		shift 1
	;;
	'--ifile')
		BACKUP_INDEX_FILE="$2"
		shift 1
	;;
	'-v')
		VERBOSE=y
	;;
	*)
		[ -n "$1" ] && \
		 TMP_TAR_DIRS="$TMP_TAR_DIRS $1"
	;;
	esac
	shift 1
done

if [ "$VERBOSE" == "y" ] ; then
	TMP_TAR_OPTIONS="$TMP_TAR_OPTIONS -v"
fi

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

if [ ! -n "$TMP_TAR_DIRS" ] ; then
	TMP_TAR_DIRS="$HOME"
fi

# Code is a unique string in the index file, so that the index file can
# describe multiple backups
if [ ! -n "$TMP_CODE" ] ; then
	TMP_CODE="$HOME"
fi
if [ ! -n "$FCODE" ] ; then
	FCODE="$USER"
fi

if [ ! -n "$TAR_FILE_BASE" ] ; then
	if [ -n "$BACKUP_DIR" ] ; then
	TAR_FILE_BASE="$BACKUP_DIR/incoming/backup-$FCODE"
	else
	TAR_FILE_BASE="/tmp/backup"
	fi
fi

TMP_NEWER=""

if [ "$FULL_BACKUP" == "y" ] || ! BKUP_LASTDATE=$(get_lastdate "$BACKUP_INDEX_FILE" "$TMP_CODE") || [ ! -n "$BKUP_LASTDATE" ]
then
	TMP_TAR_FILE="${TAR_FILE_BASE}-full-$DSTAMP"
else
	TMP_TAR_FILE="${TAR_FILE_BASE}-incr-$DSTAMP"
	TMP_NEWER="--newer"
	TMP_NEWER2="$BKUP_LASTDATE"
fi

case "$TAR_COMPRESSION" in
	gzip)
		TMP_TAR_OPTIONS="$TMP_TAR_OPTIONS -z"
		TMP_TAR_EXT="tar.gz"
	;;

	bzip2)
		TMP_TAR_OPTIONS="$TMP_TAR_OPTIONS -j"
		TMP_TAR_EXT="tar.bz2"
	;;
	*)
		TMP_TAR_OPTIONS="$TMP_TAR_OPTIONS -z"
		TAR_COMPRESSION=gzip
		TMP_TAR_EXT="tar.gz"
	;;
esac

TMP_NUM=1
if [ -e "${TMP_TAR_FILE}.${TMP_TAR_EXT}" ] ; then
	while [ -e "${TMP_TAR_FILE}-${TMP_NUM}.${TMP_TAR_EXT}" ] ; do
		TMP_NUM=$(expr $TMP_NUM '+' 1 )
		# If more than 20 bkups per day, we cannot do better..
		if [ "$TMP_NUM" == '20' ] ; then
			break
		fi
	done
	TMP_TAR_FILE="${TMP_TAR_FILE}-${TMP_NUM}.${TMP_TAR_EXT}"
else
	TMP_TAR_FILE="${TMP_TAR_FILE}.${TMP_TAR_EXT}"
fi


[ -n "$BACKUP_INDEX_FILE" ] && \
	echo "$TSTAMP" $TMP_CODE "Backup started now." >> "$BACKUP_INDEX_FILE"

decho "Starting backup.."
umask 0077

if [ "$DRY_RUN" == "y" ] ; then
	TMP_PRE_CMD=echo
fi

if [ -n "$TMP_NEWER" ] ; then
	#after timestamp
	decho $TAR -cf $TMP_TAR_FILE $TAR_DEFAULT_OPTIONS $TMP_TAR_OPTIONS $TAR_EXCLUDE_OPTIONS $TMP_NEWER "$TMP_NEWER2" -- $TMP_TAR_DIRS
	$TMP_PRE_CMD $TAR -cf $TMP_TAR_FILE $TAR_DEFAULT_OPTIONS $TMP_TAR_OPTIONS $TAR_EXCLUDE_OPTIONS $TMP_NEWER "$TMP_NEWER2" $TMP_TAR_DIRS 
	TAR_EXIT=$?
	if [ $TAR_EXIT == 0 ] ; then
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "success at" $(date) >> "$BACKUP_INDEX_FILE" || \
				exit $?
		decho "Backup finished"
	elif [ $TAR_EXIT == 1 ] ; then
		# it is a non-fatal tar exit
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "success at" $(date) " with warnings." >> "$BACKUP_INDEX_FILE"
	else
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "FAILED." >> "$BACKUP_INDEX_FILE"
		decho "Backup FAILED!"
		exit $TAR_EXIT
	fi
else
	#full backup
	decho $TAR -cf $TMP_TAR_FILE $TAR_DEFAULT_OPTIONS $TMP_TAR_OPTIONS $TAR_EXCLUDE_OPTIONS -- $TMP_TAR_DIRS
	$TMP_PRE_CMD $TAR -cf $TMP_TAR_FILE $TAR_DEFAULT_OPTIONS $TMP_TAR_OPTIONS $TAR_EXCLUDE_OPTIONS $TMP_TAR_DIRS
	TAR_EXIT=$?
	if  [ $TAR_EXIT == 0 ]; then
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "success at" $(date) >> "$BACKUP_INDEX_FILE" || \
				exit $?
		decho "Backup finished"
	elif [ $TAR_EXIT == 1 ] ; then
		# it is a non-fatal tar exit
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "success at" $(date) " with warnings." >> "$BACKUP_INDEX_FILE"
	else
		[ -n "$BACKUP_INDEX_FILE" ] && \
			echo "$TSTAMP" $TMP_TAR_FILE $TMP_CODE "FAILED." >> "$BACKUP_INDEX_FILE"
		decho "Backup FAILED!"
		exit $TAR_EXIT
	fi
fi
#eof
