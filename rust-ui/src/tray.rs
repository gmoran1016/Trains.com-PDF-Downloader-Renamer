use std::sync::mpsc::{self, Receiver, TryRecvError};

use eframe::egui;
#[cfg(target_os = "macos")]
use tray_icon::menu::Submenu;
use tray_icon::{
    Icon, TrayIcon, TrayIconBuilder,
    menu::{Menu, MenuEvent, MenuItem},
};

const SHOW_WINDOW_ID: &str = "trains-show-window";
const QUIT_ID: &str = "trains-quit";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TrayAction {
    ShowWindow,
    Quit,
}

pub trait TrayController {
    fn available(&self) -> bool;
    fn drain_actions(&mut self) -> Vec<TrayAction>;
}

pub struct DesktopTray {
    _icon: TrayIcon,
    receiver: Receiver<TrayAction>,
}

impl DesktopTray {
    pub fn create(ctx: egui::Context) -> Result<Self, String> {
        #[cfg(target_os = "linux")]
        require_status_notifier_host(status_notifier_host_registered())?;

        let show_window = MenuItem::with_id(SHOW_WINDOW_ID, "Show Window", true, None);
        let quit = MenuItem::with_id(QUIT_ID, "Quit", true, None);
        let menu = Menu::new();

        #[cfg(target_os = "macos")]
        {
            let submenu = Submenu::new("Trains.com Archive", true);
            submenu
                .append(&show_window)
                .map_err(|error| error.to_string())?;
            submenu.append(&quit).map_err(|error| error.to_string())?;
            menu.append(&submenu).map_err(|error| error.to_string())?;
        }

        #[cfg(not(target_os = "macos"))]
        {
            menu.append(&show_window)
                .map_err(|error| error.to_string())?;
            menu.append(&quit).map_err(|error| error.to_string())?;
        }

        let icon = archive_icon()?;
        let tray_icon = TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip("Trains.com Archive")
            .with_icon(icon)
            .build()
            .map_err(|error| error.to_string())?;

        let (sender, receiver) = mpsc::channel();
        MenuEvent::set_event_handler(Some(move |event: MenuEvent| {
            let action = match event.id.as_ref() {
                SHOW_WINDOW_ID => Some(TrayAction::ShowWindow),
                QUIT_ID => Some(TrayAction::Quit),
                _ => None,
            };
            if let Some(action) = action
                && sender.send(action).is_ok()
            {
                ctx.request_repaint();
            }
        }));

        Ok(Self {
            _icon: tray_icon,
            receiver,
        })
    }
}

impl TrayController for DesktopTray {
    fn available(&self) -> bool {
        true
    }

    fn drain_actions(&mut self) -> Vec<TrayAction> {
        let mut actions = Vec::new();
        loop {
            match self.receiver.try_recv() {
                Ok(action) => actions.push(action),
                Err(TryRecvError::Empty | TryRecvError::Disconnected) => return actions,
            }
        }
    }
}

fn archive_icon() -> Result<Icon, String> {
    const SIZE: u32 = 32;
    const NAVY: [u8; 4] = [25, 55, 86, 255];
    const PAPER: [u8; 4] = [255, 250, 230, 255];
    const ORANGE: [u8; 4] = [245, 157, 35, 255];

    let mut pixels = vec![0_u8; (SIZE * SIZE * 4) as usize];
    for y in 3..29 {
        for x in 3..29 {
            let is_frame = ((7..25).contains(&x) && matches!(y, 8 | 23))
                || ((7..25).contains(&y) && matches!(x, 8 | 23));
            let color = if is_frame {
                PAPER
            } else if (9..23).contains(&x) && (13..19).contains(&y) {
                ORANGE
            } else {
                NAVY
            };
            let index = ((y * SIZE + x) * 4) as usize;
            pixels[index..index + 4].copy_from_slice(&color);
        }
    }

    Icon::from_rgba(pixels, SIZE, SIZE).map_err(|error| error.to_string())
}

#[cfg(any(target_os = "linux", test))]
fn require_status_notifier_host(available: bool) -> Result<(), String> {
    if available {
        Ok(())
    } else {
        Err("No system tray host is available on this Linux desktop.".to_owned())
    }
}

#[cfg(target_os = "linux")]
fn status_notifier_host_registered() -> bool {
    use zbus::blocking::{Connection, Proxy};

    let Ok(connection) = Connection::session() else {
        return false;
    };
    let Ok(proxy) = Proxy::new(
        &connection,
        "org.kde.StatusNotifierWatcher",
        "/StatusNotifierWatcher",
        "org.kde.StatusNotifierWatcher",
    ) else {
        return false;
    };
    proxy
        .get_property::<bool>("IsStatusNotifierHostRegistered")
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::require_status_notifier_host;

    #[test]
    fn tray_is_unavailable_without_a_registered_status_notifier_host() {
        assert!(require_status_notifier_host(false).is_err());
        assert!(require_status_notifier_host(true).is_ok());
    }
}
