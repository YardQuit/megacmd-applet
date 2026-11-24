# megacmd-applet.spec: Fedora packages of the MEGAcmd applet.
# SPDX-License-Identifier: GPL-3.0-or-later

Name:           megacmd-applet
Version:        0.2.1
Release:        1%{?dist}
Summary:        MEGA sync folders, backups, storage and transfers in the desktop's panel
License:        GPL-3.0-or-later
URL:            https://github.com/YardQuit/megacmd-applet
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
# The crates the COSMIC applet is built from, so it builds without the
# network; made from the source by make crates.
Source1:        %{name}-crates-%{version}.tar.gz

# Fedora's compiler flags, the same for every step, so cargo builds only once.
%global make_with_flags RUSTFLAGS='%{build_rustflags}' make

BuildRequires:  cargo
BuildRequires:  cargo-rpm-macros
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  python3
BuildRequires:  glib2
BuildRequires:  systemd-rpm-macros
BuildRequires:  pkgconfig(xkbcommon)
BuildRequires:  pkgconfig(wayland-client)
BuildRequires:  pkgconfig(egl)
BuildRequires:  pkgconfig(dbus-1)
BuildRequires:  pkgconfig(libudev)

Requires:       python3
Requires:       gum
Requires:       procps-ng
Requires:       xdg-utils
Requires:       glib2
# MEGAcmd comes from MEGA's own repository, not from Fedora's.
Recommends:     megacmd

%global _description %{expand:
MEGA in the desktop's panel, driven by MEGAcmd: sync folders, backups, storage
and transfers, with a notification once per problem.}

%description %{_description}

This package holds the shared core and the guided dialogs; install the one
for your desktop: %{name}-kde, %{name}-gnome or %{name}-cosmic.

%package kde
Summary:        MEGAcmd applet for the KDE Plasma panel
BuildArch:      noarch
Requires:       %{name} = %{version}-%{release}
Requires:       plasma-workspace

%description kde %{_description}

The Plasma 6 panel widget.

%package gnome
Summary:        MEGAcmd applet for the GNOME Shell top bar
BuildArch:      noarch
Requires:       %{name} = %{version}-%{release}
Requires:       gnome-shell >= 48

%description gnome %{_description}

The GNOME Shell extension; turn it on in the Extensions app.

%package cosmic
Summary:        MEGAcmd applet for the COSMIC panel
# The applet and the crates linked into it, as scripts/third-party-licences.py
# --summary lists them, with those of the crates that state none: MPL-2.0
# (libcosmic), GPL-3.0-only (cosmic-panel), MIT (window_clipboard) and
# Unlicense (apply).
License:        (0BSD OR Apache-2.0 OR MIT) AND (Apache-2.0 OR Apache-2.0 WITH LLVM-exception OR MIT) AND (Apache-2.0 OR BSD-2-Clause OR MIT) AND (Apache-2.0 OR BSD-3-Clause) AND (Apache-2.0 OR GPL-2.0-only) AND (Apache-2.0 OR MIT OR Zlib) AND (Apache-2.0 OR MIT) AND (LGPL-3.0-or-later OR MIT) AND (MIT OR Unlicense) AND Apache-2.0 AND BSD-2-Clause AND BSD-3-Clause AND CC0-1.0 AND GPL-3.0-only AND GPL-3.0-or-later AND ISC AND MIT AND MPL-2.0 AND Unicode-3.0 AND Unlicense AND Zlib
Requires:       %{name} = %{version}-%{release}
Recommends:     cosmic-panel

%description cosmic %{_description}

The COSMIC panel applet; add it in Settings, Desktop, Panel, Applets.

%prep
%autosetup -a 1

%build
%{make_with_flags} cosmic

%install
%{make_with_flags} install-core install-kde install-gnome install-cosmic DESTDIR=%{buildroot} PREFIX=%{_prefix}

%check
%{make_with_flags} test

%post
%systemd_user_post mega-cmd-server.service

%preun
%systemd_user_preun mega-cmd-server.service

%files
%license LICENSE
%doc README.md
%{_datadir}/%{name}/
%{_userunitdir}/mega-cmd-server.service

%files kde
%{_datadir}/plasma/plasmoids/io.github.yardquit.megacmd/

%files gnome
%{_datadir}/gnome-shell/extensions/megacmd@yardquit.github.io/

%files cosmic
%{_bindir}/cosmic-applet-megacmd
%{_datadir}/applications/io.github.yardquit.MegaCmd.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.yardquit.MegaCmd-*-symbolic.svg
%dir %{_licensedir}/%{name}-cosmic
%license %{_licensedir}/%{name}-cosmic/THIRD-PARTY-LICENCES

%changelog
* Mon Nov 23 2026 YardQuit <yardquit@pm.me> - 0.2.1-1
- First release with the Fedora, Ubuntu and Arch Linux packages.

* Sun Nov 22 2026 YardQuit <yardquit@pm.me> - 0.2.0-1
- Packages for the shared core and the KDE, GNOME and COSMIC applets.
