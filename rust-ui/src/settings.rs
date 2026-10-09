//! Persistent application settings, compatible with the existing JSON file.

use std::{
    collections::BTreeMap,
    error::Error,
    fmt, fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tempfile::NamedTempFile;

use crate::model::AppPage;

const SETTINGS_FILE: &str = "settings.json";
const COOKIES_FILE: &str = "session_cookies.json";

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub base_dir: String,
    pub track_plans_dir: String,
    pub cookies_path: String,
    pub headless: bool,
    pub test_mode: bool,
    pub newest_first: bool,
    pub include_specials: bool,
    pub selected_magazines: Vec<String>,
    pub org_src: String,
    pub org_dst: String,
    pub org_prefix: String,
    pub org_headless: bool,
    pub selected_page: AppPage,
    pub window_width: f32,
    pub window_height: f32,
    pub activity_height: f32,
    pub activity_collapsed: bool,
    pub dark_mode: bool,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl Default for Settings {
    fn default() -> Self {
        let data_dir = default_app_data_dir();
        Self::for_data_dir(&data_dir)
    }
}

impl Settings {
    fn for_data_dir(data_dir: &Path) -> Self {
        let home = home_directory().unwrap_or_else(|| data_dir.to_path_buf());
        let downloads = home.join("Downloads");

        Self {
            base_dir: path_string(&downloads.join("TrainsMagazines")),
            track_plans_dir: path_string(&downloads.join("TrainsTrackPlans")),
            cookies_path: path_string(&data_dir.join(COOKIES_FILE)),
            headless: false,
            test_mode: false,
            newest_first: true,
            include_specials: true,
            selected_magazines: vec![
                "Model Railroader".to_owned(),
                "Trains Magazine".to_owned(),
                "Classic Toy Trains".to_owned(),
                "Classic Trains".to_owned(),
                "Garden Railways".to_owned(),
            ],
            org_src: String::new(),
            org_dst: String::new(),
            org_prefix: "Auto-detect".to_owned(),
            org_headless: false,
            selected_page: AppPage::Magazines,
            window_width: 1120.0,
            window_height: 760.0,
            activity_height: 220.0,
            activity_collapsed: true,
            dark_mode: false,
            extra: BTreeMap::new(),
        }
    }

    pub fn load(data_dir: &Path) -> SettingsLoad {
        let path = data_dir.join(SETTINGS_FILE);
        let defaults = Self::for_data_dir(data_dir);
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return SettingsLoad {
                    settings: defaults,
                    parse_error: None,
                };
            }
            Err(_) => {
                return SettingsLoad {
                    settings: defaults,
                    parse_error: Some(
                        "settings.json could not be read; default settings are in use.".to_owned(),
                    ),
                };
            }
        };

        let value: Value = match serde_json::from_slice::<Value>(&bytes) {
            Ok(value) if value.is_object() => value,
            _ => {
                return SettingsLoad {
                    settings: defaults,
                    parse_error: Some(
                        "settings.json is invalid; default settings are in use and the original file was preserved."
                            .to_owned(),
                    ),
                };
            }
        };
        let cookies_path_is_set = value.get("cookies_path").is_some();
        let mut settings: Settings = match serde_json::from_value(value) {
            Ok(settings) => settings,
            Err(_) => {
                return SettingsLoad {
                    settings: defaults,
                    parse_error: Some(
                        "settings.json contains invalid values; default settings are in use and the original file was preserved."
                            .to_owned(),
                    ),
                };
            }
        };
        if !cookies_path_is_set {
            settings.cookies_path = defaults.cookies_path;
        }

        SettingsLoad {
            settings,
            parse_error: None,
        }
    }

    pub fn save(&self, data_dir: &Path) -> Result<(), SettingsError> {
        let path = data_dir.join(SETTINGS_FILE);
        let mut output = self.clone();

        match fs::read(&path) {
            Ok(bytes) => {
                let existing: Settings = serde_json::from_slice(&bytes)
                    .map_err(|_| SettingsError::InvalidExistingFile)?;
                for (key, value) in existing.extra {
                    output.extra.entry(key).or_insert(value);
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(SettingsError::ReadExisting(error)),
        }

        let serialized = serde_json::to_vec_pretty(&output).map_err(SettingsError::Serialize)?;
        fs::create_dir_all(data_dir).map_err(SettingsError::CreateDirectory)?;
        let mut temporary = NamedTempFile::new_in(data_dir).map_err(SettingsError::CreateTemp)?;
        temporary
            .write_all(&serialized)
            .map_err(SettingsError::WriteTemp)?;
        temporary
            .as_file()
            .sync_all()
            .map_err(SettingsError::SyncTemp)?;
        temporary
            .persist(&path)
            .map_err(|error| SettingsError::Persist(error.error))?;
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct SettingsLoad {
    pub settings: Settings,
    pub parse_error: Option<String>,
}

#[derive(Debug)]
pub enum SettingsError {
    ReadExisting(io::Error),
    InvalidExistingFile,
    Serialize(serde_json::Error),
    CreateDirectory(io::Error),
    CreateTemp(io::Error),
    WriteTemp(io::Error),
    SyncTemp(io::Error),
    Persist(io::Error),
}

impl fmt::Display for SettingsError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ReadExisting(error) => {
                write!(formatter, "could not read current settings: {error}")
            }
            Self::InvalidExistingFile => {
                formatter.write_str("current settings are invalid; the original file was preserved")
            }
            Self::Serialize(error) => write!(formatter, "could not serialize settings: {error}"),
            Self::CreateDirectory(error) => {
                write!(formatter, "could not create data folder: {error}")
            }
            Self::CreateTemp(error) => write!(
                formatter,
                "could not create temporary settings file: {error}"
            ),
            Self::WriteTemp(error) => write!(
                formatter,
                "could not write temporary settings file: {error}"
            ),
            Self::SyncTemp(error) => write!(
                formatter,
                "could not flush temporary settings file: {error}"
            ),
            Self::Persist(error) => write!(formatter, "could not replace settings file: {error}"),
        }
    }
}

impl Error for SettingsError {}

fn home_directory() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
}

fn default_app_data_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(PathBuf::from))
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."))
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}
