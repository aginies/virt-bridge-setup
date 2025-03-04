#
# spec file for package virt-bridge-setup
#
# Copyright (c) 2025 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#

Name:           virt-bridge-setup
Version:        0.1
Release:        1%{?dist}
Summary:        Script to setup virtual bridges
License:        GPL
URL:            https://github.com/aginies/virt-bridge-setup
Source0:        %{name}-%{version}.tar.bz2
BuildArch:      noarch
Requires:       NetworkManager
Requires:       make
Requires:       python3

%description
virt-bridge-setup is a script to automate the setup of virtual bridges using NetworkManager.
It simplifies the process of creating and managing network bridges for virtualization environments.

%prep
%setup -q

%build

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot}
#mkdir -p %{buildroot}/%{_sbindir}
#install -m 755 %{name}.py %{buildroot}/%{_sbindir}/%{name}

%files
%license LICENSE
%doc README.md
%attr(0755,root,root) %{_sbindir}
%{_sbindir}/%{name}

%changelog
