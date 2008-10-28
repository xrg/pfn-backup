%define git_repo pfn-backup
%define git_head HEAD

%define name pfn-backup
%define version 0.3
%define release %mkrel 1

# this will force "/usr/lib/" even on 64-bit
%define libndir %{_exec_prefix}/lib

Name:		%{name}
Version:	%{version}
Release:	%{release}
Summary:	Pefnos Backup scripts
Group:		Archiving/
BuildArch:	noarch
License:	GPL
Source0:	pfn-backup-%{version}.tar.gz

#BuildRequires:	gettext
Requires(pre): tar
Requires(postun): gnupg

%description
Pfn-backup is a set of shell (bash) scripts that direct GNU tar into
making your everyday backups. Backups are stored on some local 
filesystem, which is then mirrored to any remote media.

Note: in order to setup Postgresql hot-backup (PITR) for the first time,
you may need to install this package with the Postgres server stopped.

%prep
%git_get_source
%setup -q

%build
# nothing to build!

%install
[ -n "%{buildroot}" -a "%{buildroot}" != / ] && rm -rf %{buildroot}
install -d %{buildroot}%{_sysconfdir}/backup \
	%{buildroot}%{_bindir} \
	%{buildroot}%{_sbindir}
install -D etc/backup/* %{buildroot}%{_sysconfdir}/backup/
install bin/* %{buildroot}%{_bindir}/
install sbin/* %{buildroot}%{_sbindir}/
install -d %{buildroot}%{_sysconfdir}/cron.daily
install -d %{buildroot}/var/backup
install -d %{buildroot}%{libndir}/pfn_backup/
install lib/pfn_backup/* %{buildroot}%{libndir}/pfn_backup/

cat '-' >%{buildroot}%{_sysconfdir}/cron.daily/all-backup.sh  <<EOF
#!/bin/bash
nice %{_sbindir}/all-backup.sh
EOF

touch	%{buildroot}/var/backup/index

%clean
[ -n "%{buildroot}" -a "%{buildroot}" != / ] && rm -rf %{buildroot}

%pre
%_pre_groupadd backup

%post
%create_ghostfile /var/backup/index root backup 664
if [ -d "%{_localstatedir}/pgsql" ] ; then
	if ! %{libndir}/pfn_backup/setup_postgres.sh ; then
		echo "Cannot automatically setup Postgres for hot backup."
		echo "Please run %{libndir}/pfn_backup/setup_postgres.sh"
	fi
fi

%files
%defattr(-,root,root)
%config(noreplace)	%{_sysconfdir}/backup/*
%attr(0755,root,backup)	%{_bindir}/user-backup.sh
%attr(0755,root,root)	%{_sbindir}/*
%attr(0744,root,root)	%{_sysconfdir}/cron.daily/all-backup.sh
			%{libndir}/pfn_backup/*
%attr(0775,root,backup) %dir /var/backup
%attr(0664,root,backup) %ghost /var/backup/index
