// main.rs: start the MEGA applet in the COSMIC panel.
// SPDX-License-Identifier: GPL-3.0-or-later

mod app;
mod config;
mod core;
mod model;
mod popup;

fn main() -> cosmic::iced::Result {
    cosmic::applet::run::<app::Applet>(())
}
