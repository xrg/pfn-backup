#!/bin/sh

#	Desc:	pfn-backup .deb packaging script
#	Author:	Jimmy Angelakos <vyruss@hellug.gr>

# Variables to be passed on to the package
version=0.5.2
maintainer="Jimmy Angelakos <vyruss@hellug.gr>"

# Make temp dir
echo Making temp dir...
tempdir="temp-$(date +%Y%m%d)"
mkdir $tempdir

# Make required folders
echo Making required folders...
cd $tempdir 
mkdir etc usr usr/share usr/share/doc usr/share/doc/pfn-backup \
      var var/backup
cd ..

# Copy files into package dir
echo Copying files into package dir...
cp -a bin $tempdir/usr
cp -a sbin $tempdir/usr
cp -a etc/* $tempdir/etc
cp -a doc/* $tempdir/usr/share/doc/pfn-backup
size=$(du -ks $tempdir)

# Make debian package dir
echo Adding Debian required files...
mkdir $tempdir/DEBIAN
sed "s/@maintainer/$maintainer/;s/@version/$version/;s/@size/$size/" \
    debian_templates/control > $tempdir/DEBIAN/control1
sed "/Inst/s/$tempdir//" $tempdir/DEBIAN/control1 > $tempdir/DEBIAN/control 
sed "s/@maintainer/$maintainer/;s/@date/$(date -R)/" \
    debian_templates/copyright > $tempdir/DEBIAN/copyright

# Create package & remove temp files
echo Creating the package...
dpkg -b $tempdir pfn-backup-$version-0ubuntu1-all.deb
echo Removing temporary files...
rm -fr $tempdir
