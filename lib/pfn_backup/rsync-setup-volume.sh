#!/bin/bash

# Copyright (C) P. Christeas <p_christ@hol.gr>, 2008
# This is free software.
#
LIST_MOUNTED=0
LIST_REMOVABLE=0
VERBOSE=
OUTFILE=20-usb-rsync.fdi

vecho() {
	if [ "$VERBOSE" == 'y' ] ; then
		echo $@
	fi
}

echo "Device list:"
echo "---------------"

hal-find-by-capability --capability 'volume' | \
while read UDI ; do
	vecho "Processing volume $UDI"
	if [ "$(hal-get-property --udi $UDI --key 'volume.fsusage')" != 'filesystem' ] ; then
		vecho "Volume is not filesystem"
		continue
	fi
	SDEVICE=$(hal-get-property --udi $UDI --key 'block.storage_device')
	SMODEL=$(hal-get-property --udi $SDEVICE --key 'storage.model')
	SREMOVABLE=$(hal-get-property --udi $SDEVICE --key 'storage.removable')
	
	UUID=$(hal-get-property --udi $UDI --key 'volume.uuid')
	FSTYPE=$(hal-get-property --udi $UDI --key 'volume.fstype')
	MOUNTED=$(hal-get-property --udi $UDI --key 'volume.is_mounted')
	LABEL=$(hal-get-property --udi $UDI --key 'volume.label')
	if [ "$SREMOVABLE" != "true" ] && [ "$LIST_REMOVABLE" == "1" ]; then
		continue
	fi
	if [ "$MOUNTED" == "true" ] && [ "$LIST_MOUNTED" == "0" ]; then
		continue
	fi
	if [ "$MOUNTED" == "true" ]; then
		MNTED="@$(hal-get-property --udi $UDI --key 'volume.mount_point')"
	fi
	
	echo -n $SMODEL
	[ "$SREMOVABLE" == "true" ] && echo -n "(r)"
	echo -n "  UUID: $UUID"
	[ -n "$LABEL" ] && echo -n " \"$LABEL\""
		
	echo "	FS: $FSTYPE$MNTED"
done
	
echo
while read -p "Please enter the UUID of the device you want to setup: " SET_UUID ; do
	vecho "Attempting UUID: $SET_UUID"
	if ! SET_UDI=$(hal-find-by-property --key 'volume.uuid' --string $SET_UUID) ; then
		echo "Volume not found. Please try again, or press Ctrl+C to stop."
		continue
	fi
	
cat '-' > $OUTFILE <<EOF
<?xml version="1.0" encoding="ISO-8859-1"?>

<!--
 File: $OUTFILE
 based on work done by Wayne D at http://wdawe.com, Jimmy Angelakos

 This is the fdi file that makes HAL call usb-rsync-callout when it finds that our USB key has been added.
-->

<deviceinfo version="0.2">
<device>
	<match key="volume.uuid" string="$SET_UUID">
	<append key="info.callouts.add" type="strlist">usb-rsync-callout</append>
	</match>
</device>
</deviceinfo>

EOF

	echo "Now, please inspect $OUTFILE and move it to /etc/hal/fdi/information/"
	break
done

#eof
