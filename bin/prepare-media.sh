#!/bin/bash 
# 
# Copyright (C) P. Christeas <p_christ@hol.gr>, 2008
# This is free software.
#


file_size() {
	[ ! -f "$1" ] && return 1
	ls -f -s -k "$1" | cut -f 1 -d ' '
}

put_large() {
	echo "Large:" $1
	DDIR=$(dirname "$(echo $1 | sed 's|^[^/]*/||')")
	if [ ! -d "$BK_LARGE_DIR" ] ; then
		mkdir -p "$BK_LARGE_DIR" || exit 2
	fi
	$DRY mv "$1" "$BK_LARGE_DIR/$DDIR"/ || return $?
}

put_media() {
	local SIZ=$3
	# echo "Media \"${MEDIA_NAME[$1]}\" += $2, $3, ${MEDIA_SIZE[$1]}"
	
	DDIR=$(dirname "$(echo $2 | sed 's|^[^/]*/||')")
	DEST_DIR="$BK_MEDIA_DIR/${MEDIA_NAME[$1]}/$DDIR"
	if [ ! -d "$DEST_DIR" ] ; then
		$DRY mkdir -p "$DEST_DIR" || exit 2
	fi
	$DRY mv "$2" "$DEST_DIR/" || return $?
	
	MEDIA_SIZE[$1]=$((${MEDIA_SIZE[$1]} - $SIZ ))
}


declare -a MEDIA_NAME
declare -a MEDIA_SIZE
let FIRST_MEDIA=0
let LAST_MEDIA=0

	#don't build more than 100 disks at a time
let MAX_MEDIA=100

let DISK_SIZE=4589843
	#waste that much space in favour of file order
let CLOSE_SIZE=1000
MEDIA_BASE_NAME="dvd"

. /etc/backup/options || true

BK_DIR="$BACKUP_DIR/incoming/"
BK_LARGE_DIR="$BACKUP_DIR/wontfit"
BK_MEDIA_DIR="$BACKUP_DIR/outgoing"
BK_PAT="*.gz"

if [ "x$BACKUP_USE_GPG" == "xy" ] ; then
	BK_DIR="$BACKUP_DIR/gpg"
fi

if [ -z "$PREPARE_MEDIA_LINE" ] ; then
	PREPARE_MEDIA_LINE="find $BK_DIR -type f"
fi

MEDIA_NAME[$LAST_MEDIA]=${MEDIA_BASE_NAME}$(( ${LAST_MEDIA} + 1))
let MEDIA_SIZE[$LAST_MEDIA]=$DISK_SIZE

if [ "$1" == '--dry-run' ] ; then
   DRY="echo"
fi

while [ -d "$BK_MEDIA_DIR/${MEDIA_NAME[$LAST_MEDIA]}" ] ; do
		#using the full path for 'du', to avoid aliases
	TMP_SIZE=$(/usr/bin/du -k -s "$BK_MEDIA_DIR/${MEDIA_NAME[$LAST_MEDIA]}" | cut -f 1)
	
	if [ $TMP_SIZE -gt $DISK_SIZE ] ; then
		MEDIA_SIZE[$LAST_MEDIA]=0
	else
		MEDIA_SIZE[$LAST_MEDIA]=$(($DISK_SIZE-$TMP_SIZE))
	fi
	
	echo "Located media: ${MEDIA_NAME[$LAST_MEDIA]}, disk- $TMP_SIZE = ${MEDIA_SIZE[$LAST_MEDIA]}"
	
	LAST_MEDIA=$(($LAST_MEDIA +1))
	
	MEDIA_NAME[$LAST_MEDIA]=${MEDIA_BASE_NAME}$(( ${LAST_MEDIA} + 1))
	let MEDIA_SIZE[$LAST_MEDIA]=$DISK_SIZE
done

pushd "$BACKUP_DIR"
for FIL in $($PREPARE_MEDIA_LINE) ; do
	if [ ! -f "$FIL" ] ; then
		continue
	fi
	SIZ=$(file_size ${FIL})
	# echo "$FIL: $SIZ"
	# continue
	if [ $SIZ -gt $DISK_SIZE ] ; then
		put_large "${FIL}" || break
	else
		let CUR_MEDIA=$FIRST_MEDIA
		while [ $SIZ -gt ${MEDIA_SIZE[$CUR_MEDIA]} ] ; do
			if [ $CUR_MEDIA == $FIRST_MEDIA ] && [ ${MEDIA_SIZE[$CUR_MEDIA]} -lt $CLOSE_SIZE ] ; then
				#don't visit this media again
				let FIRST_MEDIA+=1
			fi
			let CUR_MEDIA+=1
			if [ $CUR_MEDIA -gt $MAX_MEDIA ] ;then
				echo "Max media reached [$CUR_MEDIA]" >&2
				exit 2
			fi
			if [ -z "${MEDIA_NAME[$CUR_MEDIA]}" ] ; then
				MEDIA_NAME[$CUR_MEDIA]=${MEDIA_BASE_NAME}$((${CUR_MEDIA} + 1))
				let MEDIA_SIZE[$CUR_MEDIA]=$DISK_SIZE
			fi
		done
		put_media $CUR_MEDIA "${FIL}" $SIZ || break
	fi
done

popd

#eof
