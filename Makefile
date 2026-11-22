# Makefile: build, install and package the MEGAcmd applet for each desktop.
# SPDX-License-Identifier: GPL-3.0-or-later
#
#   make test           run the test suite
#   make kde            build the Plasma widget in build/kde/
#   make install-kde    install (or upgrade) it for this user
#   make gnome          build the GNOME Shell extension in build/gnome/
#   make install-gnome  install it for this user (log out and in to load it)
#   make cosmic         build the COSMIC panel applet
#   make install-cosmic install it under PREFIX (default ~/.local); add it in
#                       the panel settings afterwards
#   make dist           build the release files in build/dist/
#
# Each package carries its own copy of the shared core (core/, bin/,
# fixtures/), so it works without this checkout. The version is the one in
# manifest.json.

VERSION := $(shell python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
KDE_ID := io.github.yardquit.megacmd
GNOME_UUID := megacmd@yardquit.github.io
GNOME_EXTENSIONS := $(or $(XDG_DATA_HOME),$(HOME)/.local/share)/gnome-shell/extensions
PREFIX ?= $(HOME)/.local
DESTDIR ?=
BUILD := build
DIST := $(BUILD)/dist
CORE_FILES := bin core fixtures
ARCH := $(shell uname -m)

.PHONY: test kde install-kde gnome install-gnome cosmic install-cosmic dist clean

test:
	python3 -m unittest discover -s tests

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

install-kde: kde
	kpackagetool6 --type Plasma/Applet --upgrade $(BUILD)/kde/$(KDE_ID) || \
		kpackagetool6 --type Plasma/Applet --install $(BUILD)/kde/$(KDE_ID)

gnome:
	rm -rf $(BUILD)/gnome
	mkdir -p $(BUILD)/gnome
	cp -r gnome $(BUILD)/gnome/$(GNOME_UUID)
	glib-compile-schemas $(BUILD)/gnome/$(GNOME_UUID)/schemas
	$(call copy_core,$(BUILD)/gnome/$(GNOME_UUID)/megacmd)

install-gnome: gnome
	rm -rf $(GNOME_EXTENSIONS)/$(GNOME_UUID)
	mkdir -p $(GNOME_EXTENSIONS)
	cp -r $(BUILD)/gnome/$(GNOME_UUID) $(GNOME_EXTENSIONS)/

cosmic:
	cargo build --release --locked --manifest-path cosmic/Cargo.toml

# The applet finds the core in <data folder>/megacmd-applet, searching
# $XDG_DATA_HOME and $XDG_DATA_DIRS.
install-cosmic: cosmic
	install -D -m 755 cosmic/target/release/cosmic-applet-megacmd $(DESTDIR)$(PREFIX)/bin/cosmic-applet-megacmd
	rm -rf $(DESTDIR)$(PREFIX)/share/megacmd-applet
	$(call copy_core,$(DESTDIR)$(PREFIX)/share/megacmd-applet)
	install -D -m 644 -t $(DESTDIR)$(PREFIX)/share/applications cosmic/data/io.github.yardquit.MegaCmd.desktop
	install -D -m 644 -t $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps cosmic/data/icons/*.svg

# Release files: the COSMIC applet as a tree to unpack under /usr, the
# Plasma widget for kpackagetool6, the GNOME extension for gnome-extensions
# install, and their SHA256SUMS.
dist: kde gnome
	rm -rf $(DIST) $(BUILD)/cosmic-root
	mkdir -p $(DIST)
	$(MAKE) install-cosmic DESTDIR=$(BUILD)/cosmic-root PREFIX=/usr
	tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 \
		-C $(BUILD)/cosmic-root -czf $(DIST)/megacmd-applet-cosmic-$(VERSION)-$(ARCH).tar.gz usr
	cd $(BUILD)/kde/$(KDE_ID) && find . -type f | LC_ALL=C sort | \
		TZ=UTC zip -q -X -D -@ $(CURDIR)/$(DIST)/megacmd-applet-kde-$(VERSION).plasmoid
	cd $(BUILD)/gnome/$(GNOME_UUID) && find . -type f | LC_ALL=C sort | \
		TZ=UTC zip -q -X -D -@ $(CURDIR)/$(DIST)/$(GNOME_UUID).shell-extension.zip
	cd $(DIST) && sha256sum *.tar.gz *.plasmoid *.zip > SHA256SUMS

clean:
	rm -rf $(BUILD) cosmic/target
