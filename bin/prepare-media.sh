#!/bin/bash

file_size() {
	[ ! -f "$1" ] && return 1
	ls -f -s -k "$1" | cut -f 1 -d ' '
}

put_large() {
	echo "Large:" $1
}

put_media() {
	local SIZ=$3
	MEDIA_SIZE[$1]=$((${MEDIA_SIZE[$1]} - $SIZ ))
	echo "Media \"${MEDIA_NAME[$1]}\" += $2, $3, ${MEDIA_SIZE[$1]}"
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

MEDIA_NAME[$LAST_MEDIA]="media"$(( ${LAST_MEDIA} + 1))
let MEDIA_SIZE[$LAST_MEDIA]=$DISK_SIZE

pushd /koina/home/backup
for FIL in *.tar.gz ; do
	SIZ=$(file_size ${FIL})
	# echo "$FIL: $SIZ"
	# continue
	if [ $SIZ -gt $DISK_SIZE ] ; then
		put_large "${FIL}"
	else
		let CUR_MEDIA=$FIRST_MEDIA
		while [ $SIZ -gt ${MEDIA_SIZE[$CUR_MEDIA]} ] ; do
			if [ $CUR_MEDIA == $FIRST_MEDIA ] && [ ${MEDIA_SIZE[$CUR_MEDIA]} -lt $CLOSE_SIZE ]; then
				#don't visit this media again
				let FIRST_MEDIA+=1
			fi
			let CUR_MEDIA+=1
			if [ $CUR_MEDIA -gt $MAX_MEDIA ] ;then
				echo "Max media reached [$CUR_MEDIA]" >&2
				exit 2
			fi
			if [ -z "${MEDIA_NAME[$CUR_MEDIA]}" ] ; then
				MEDIA_NAME[$CUR_MEDIA]="media"$((${CUR_MEDIA} + 1))
				let MEDIA_SIZE[$CUR_MEDIA]=$DISK_SIZE
			fi
		done
		put_media $CUR_MEDIA "${FIL}" $SIZ
	fi
done

popd

#eof
