use std::fs;

use serde_json::{Value, json};
use trains_com_downloader::settings::Settings;

#[test]
fn loads_existing_settings_keys() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let settings_path = data_dir.path().join("settings.json");
    fs::write(
        &settings_path,
        serde_json::to_vec(&json!({
            "base_dir": "D:/Magazine PDFs",
            "track_plans_dir": "D:/Track Plans",
            "cookies_path": "D:/account/session_cookies.json",
            "headless": true,
            "test_mode": true,
            "newest_first": false,
            "include_specials": false,
            "selected_magazines": ["Model Railroader", "Trains Magazine"],
            "org_src": "D:/Incoming",
            "org_dst": "D:/Library",
            "org_prefix": "MRR",
            "org_headless": true
        }))
        .expect("serialize fixture"),
    )
    .expect("write settings fixture");

    let loaded = Settings::load(data_dir.path());

    assert_eq!(loaded.parse_error, None);
    assert_eq!(loaded.settings.base_dir, "D:/Magazine PDFs");
    assert_eq!(loaded.settings.track_plans_dir, "D:/Track Plans");
    assert_eq!(
        loaded.settings.cookies_path,
        "D:/account/session_cookies.json"
    );
    assert!(loaded.settings.headless);
    assert!(loaded.settings.test_mode);
    assert!(!loaded.settings.newest_first);
    assert!(!loaded.settings.include_specials);
    assert_eq!(
        loaded.settings.selected_magazines,
        ["Model Railroader", "Trains Magazine"]
    );
    assert_eq!(loaded.settings.org_src, "D:/Incoming");
    assert_eq!(loaded.settings.org_dst, "D:/Library");
    assert_eq!(loaded.settings.org_prefix, "MRR");
    assert!(loaded.settings.org_headless);
}

#[test]
fn preserves_unknown_keys_on_save() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let settings_path = data_dir.path().join("settings.json");
    let unknown = json!({
        "migration": {"version": 4, "note": "keep me"},
        "future_preferences": ["one", "two"]
    });
    let mut initial = json!({"base_dir": "D:/Old"});
    initial
        .as_object_mut()
        .expect("settings object")
        .extend(unknown.as_object().expect("unknown object").clone());
    fs::write(
        &settings_path,
        serde_json::to_vec(&initial).expect("serialize fixture"),
    )
    .expect("write settings fixture");

    let mut settings = Settings::load(data_dir.path()).settings;
    settings.base_dir = "D:/New".to_owned();
    settings
        .save(data_dir.path())
        .expect("save settings without dropping unknown keys");

    let saved: Value =
        serde_json::from_slice(&fs::read(&settings_path).expect("read saved settings"))
            .expect("valid saved JSON");
    assert_eq!(saved["base_dir"], "D:/New");
    assert_eq!(saved["migration"], unknown["migration"]);
    assert_eq!(saved["future_preferences"], unknown["future_preferences"]);
}

#[test]
fn invalid_json_is_not_overwritten() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let settings_path = data_dir.path().join("settings.json");
    let original = b"{not valid json and must stay exactly as written";
    fs::write(&settings_path, original).expect("write invalid settings");

    let loaded = Settings::load(data_dir.path());

    assert!(loaded.parse_error.is_some());
    assert!(loaded.settings.save(data_dir.path()).is_err());
    assert_eq!(
        fs::read(settings_path).expect("read preserved bytes"),
        original
    );
}

#[test]
fn round_trips_unicode_paths() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let mut settings = Settings::load(data_dir.path()).settings;
    settings.base_dir = "D:/铁路/杂志/Été".to_owned();
    settings.track_plans_dir = "D:/鉄道/計画/東京".to_owned();
    settings.cookies_path = "D:/会計/session_cookies.json".to_owned();

    settings.save(data_dir.path()).expect("save unicode paths");
    let loaded = Settings::load(data_dir.path());

    assert_eq!(loaded.parse_error, None);
    assert_eq!(loaded.settings.base_dir, settings.base_dir);
    assert_eq!(loaded.settings.track_plans_dir, settings.track_plans_dir);
    assert_eq!(loaded.settings.cookies_path, settings.cookies_path);
}
