# Makefile: build, install and package the MEGAcmd applet for each desktop.
# SPDX-License-Identifier: GPL-3.0-or-later
#
#   make test            run the test suites of the core and the COSMIC applet,
#                        or one of them with test-core or test-cosmic
#   make install         install the core and every desktop's part under
#                        PREFIX (default ~/.local), or one by one with
#                        install-core and the part, e.g.
#                        make install-core install-kde
#   make install-core    the shared core, guided dialogs and the engine's
#                        systemd user unit
#   make install-omarchy the Omarchy plugin, beside the core
#   make install-kde     the Plasma widget (add it from Add Widgets)
#   make install-gnome   the GNOME Shell extension (log out and in to load it)
#   make install-cosmic  the COSMIC panel applet (add it in the panel settings)
#   make kde gnome       build the Plasma widget and GNOME extension in build/,
#                        each with its own copy of the core
#   make cosmic          build the COSMIC panel applet
#   make dist            build the release files in build/dist/
#   make crates          fetch the crates the COSMIC applet needs into
#                        build/megacmd-applet-crates-VERSION.tar.gz
#
# Installed under PREFIX, the KDE and GNOME parts reach the core installed in
# PREFIX/share/megacmd-applet through a link; built with make kde or make
# gnome they carry their own copy, so they work without it. The version is
# the one in manifest.json.
#
# The crates archive unpacks to crates/ at the top of the source; while that
# folder is there, cargo takes every crate from it and never uses the network,
# which lets distribution build systems build the applet offline.

VERSION := $(shell python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
KDE_ID := io.github.yardquit.megacmd
GNOME_UUID := megacmd@yardquit.github.io
PREFIX ?= $(HOME)/.local
DESTDIR ?=
SHARE := $(DESTDIR)$(PREFIX)/share
CORE_DIR := $(PREFIX)/share/megacmd-applet
BUILD := build
DIST := $(BUILD)/dist
CORE_FILES := bin core fixtures
ARCH := $(shell uname -m)
# The interpreter named in the first line of the installed core's command.
PYTHON_INTERPRETER ?= /usr/bin/python3
# systemd reads user units from ~/.local/share/systemd/user in the home
# folder, and from lib/systemd/user under /usr and /usr/local.
ifneq ($(filter $(HOME)/%,$(PREFIX)),)
USER_UNIT_DIR ?= $(PREFIX)/share/systemd/user
else
USER_UNIT_DIR ?= $(PREFIX)/lib/systemd/user
endif
# Targets whose crates make crates fetches.
CRATE_TARGETS ?= x86_64-unknown-linux-gnu aarch64-unknown-linux-gnu
CRATES_ARCHIVE := $(BUILD)/megacmd-applet-crates-$(VERSION).tar.gz
ifneq ($(wildcard crates/registry),)
export CARGO_HOME := $(CURDIR)/crates
export CARGO_NET_OFFLINE := true
endif

.PHONY: test test-core test-cosmic kde gnome cosmic install install-core install-omarchy \
	install-kde install-gnome install-cosmic dist crates clean

test: test-core test-cosmic

test-core:
	python3 -m unittest discover -s tests

test-cosmic:
	cargo test --release --locked --manifest-path cosmic/Cargo.toml

# Copies the shared core into the folder $(1), leaving out Python caches.
define copy_core
	mkdir -p $(1)
	cp -r $(CORE_FILES) $(1)/
	find $(1) -name __pycache__ -type d -prune -exec rm -rf {} +
endef

kde:
	rm -rf $(BUILD)/kde
	mkdir -p $(BUILD)/kde
	cp -r kde $(BUILD)/kde/$(KDE_ID)
	$(call copy_core,$(BUILD)/kde/$(KDE_ID)/contents/megacmd)

gnome:
	rm -rf $(BUILD)/gnome
	mkdir -p $(BUILD)/gnome
	cp -r gnome $(BUILD)/gnome/$(GNOME_UUID)
	glib-compile-schemas $(BUILD)/gnome/$(GNOME_UUID)/schemas
	$(call copy_core,$(BUILD)/gnome/$(GNOME_UUID)/megacmd)

cosmic:
	cargo build --release --locked --manifest-path cosmic/Cargo.toml

install: install-core install-omarchy install-kde install-gnome install-cosmic

install-core:
	rm -rf $(DESTDIR)$(CORE_DIR)/bin $(DESTDIR)$(CORE_DIR)/core $(DESTDIR)$(CORE_DIR)/fixtures
	$(call copy_core,$(DESTDIR)$(CORE_DIR))
	sed -i '1s|^#!/usr/bin/env python3$$|#!$(PYTHON_INTERPRETER)|' $(DESTDIR)$(CORE_DIR)/bin/megacmd-applet
	install -D -m 644 -t $(DESTDIR)$(USER_UNIT_DIR) systemd/mega-cmd-server.service

# The core's folder becomes the plugin: Omarchy reads manifest.json there.
install-omarchy:
	rm -rf $(DESTDIR)$(CORE_DIR)/omarchy
	mkdir -p $(DESTDIR)$(CORE_DIR)
	cp -r omarchy $(DESTDIR)$(CORE_DIR)/
	install -m 644 manifest.json $(DESTDIR)$(CORE_DIR)/

install-kde:
	rm -rf $(SHARE)/plasma/plasmoids/$(KDE_ID)
	mkdir -p $(SHARE)/plasma/plasmoids
	cp -r kde $(SHARE)/plasma/plasmoids/$(KDE_ID)
	ln -sr $(DESTDIR)$(CORE_DIR) $(SHARE)/plasma/plasmoids/$(KDE_ID)/contents/megacmd

install-gnome:
	rm -rf $(SHARE)/gnome-shell/extensions/$(GNOME_UUID)
	mkdir -p $(SHARE)/gnome-shell/extensions
	cp -r gnome $(SHARE)/gnome-shell/extensions/$(GNOME_UUID)
	glib-compile-schemas $(SHARE)/gnome-shell/extensions/$(GNOME_UUID)/schemas
	ln -sr $(DESTDIR)$(CORE_DIR) $(SHARE)/gnome-shell/extensions/$(GNOME_UUID)/megacmd

# The applet finds the core in <data folder>/megacmd-applet, searching
# $XDG_DATA_HOME and $XDG_DATA_DIRS. The licence texts of the crates built
# into it go beside it. The panel starts the applet by the absolute path
# written into its desktop file, as PREFIX/bin may not be on the session's
# PATH.
install-cosmic: cosmic
	install -D -m 755 cosmic/target/release/cosmic-applet-megacmd $(DESTDIR)$(PREFIX)/bin/cosmic-applet-megacmd
	mkdir -p $(SHARE)/licenses/megacmd-applet-cosmic $(SHARE)/applications
	python3 scripts/third-party-licences.py > $(SHARE)/licenses/megacmd-applet-cosmic/THIRD-PARTY-LICENCES
	sed 's|^Exec=cosmic-applet-megacmd|Exec=$(PREFIX)/bin/cosmic-applet-megacmd|' \
		cosmic/data/io.github.yardquit.MegaCmd.desktop > $(SHARE)/applications/io.github.yardquit.MegaCmd.desktop
	chmod 644 $(SHARE)/applications/io.github.yardquit.MegaCmd.desktop
	install -D -m 644 -t $(SHARE)/icons/hicolor/scalable/apps cosmic/data/icons/*.svg

# Release files: the COSMIC applet as a tree to unpack under /usr, the
# Plasma widget for kpackagetool6, the GNOME extension for gnome-extensions
# install, and their SHA256SUMS.
dist: kde gnome
	rm -rf $(DIST) $(BUILD)/cosmic-root
	mkdir -p $(DIST)
	$(MAKE) install-core install-cosmic DESTDIR=$(BUILD)/cosmic-root PREFIX=/usr
	tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 \
		-C $(BUILD)/cosmic-root -czf $(DIST)/megacmd-applet-cosmic-$(VERSION)-$(ARCH).tar.gz usr
	cd $(BUILD)/kde/$(KDE_ID) && find . -type f | LC_ALL=C sort | \
		TZ=UTC zip -q -X -D -@ $(CURDIR)/$(DIST)/megacmd-applet-kde-$(VERSION).plasmoid
	cd $(BUILD)/gnome/$(GNOME_UUID) && find . -type f | LC_ALL=C sort | \
		TZ=UTC zip -q -X -D -@ $(CURDIR)/$(DIST)/$(GNOME_UUID).shell-extension.zip
	cd $(DIST) && sha256sum *.tar.gz *.plasmoid *.zip > SHA256SUMS

# A cargo home holding the crates of cosmic/Cargo.lock for CRATE_TARGETS,
# without the unpacked copies cargo makes again from the archives.
crates:
	rm -rf $(BUILD)/crates
	CARGO_HOME=$(CURDIR)/$(BUILD)/crates CARGO_NET_OFFLINE=false cargo fetch --locked \
		$(addprefix --target ,$(CRATE_TARGETS)) --manifest-path cosmic/Cargo.toml
	tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 -C $(BUILD) -czf $(CRATES_ARCHIVE) \
		crates/registry/cache crates/registry/index crates/git/db crates/git/checkouts

clean:
	rm -rf $(BUILD) cosmic/target
