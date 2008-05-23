%define git_repodir /home/panos/build/
%define git_repo pfn-backup
%define git_head HEAD

%define name pfn-backup
%define version 0.1
%define release 1

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
#install -d %{buildroot}%{_datadir}/a2billing

%clean
[ -n "%{buildroot}" -a "%{buildroot}" != / ] && rm -rf %{buildroot}

%files
%defattr(-,root,root)
%config(noreplace)	%{_sysconfdir}/backup/*
%attr(0755,root,users)	%{_bindir}/user-backup.sh
%attr(0755,root,root)	%{_sbindir}/*

