use std::fs;

use trains_com_downloader::worker_bundle::extract_worker;

#[test]
fn extracts_worker_to_unique_temp_path() {
    let root = tempfile::tempdir().expect("temporary worker root");

    let first = extract_worker(b"fake worker executable", root.path(), "1.8.6")
        .expect("first worker extraction");
    let second = extract_worker(b"fake worker executable", root.path(), "1.8.6")
        .expect("second worker extraction");

    assert_ne!(first.path(), second.path());
    assert_eq!(fs::read(first.path()).unwrap(), b"fake worker executable");
    assert_eq!(fs::read(second.path()).unwrap(), b"fake worker executable");
}

#[test]
fn empty_worker_is_rejected() {
    let root = tempfile::tempdir().expect("temporary worker root");

    let error = extract_worker(b"", root.path(), "1.8.6").expect_err("empty worker must fail");

    assert!(error.to_string().contains("empty"));
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), 0);
}

#[test]
fn worker_temp_is_removed_only_when_owned() {
    let root = tempfile::tempdir().expect("temporary worker root");
    let unrelated = root.path().join("keep-this-file.txt");
    fs::write(&unrelated, "user file").unwrap();
    let worker = extract_worker(b"worker", root.path(), "1.8.6").expect("worker extraction");
    let worker_path = worker.path().to_path_buf();
    let owned_directory = worker_path.parent().unwrap().to_path_buf();

    drop(worker);

    assert!(
        !owned_directory.exists(),
        "only the owned temp directory is removed"
    );
    assert!(
        unrelated.exists(),
        "files outside the owned temp directory survive"
    );
}

#[cfg(unix)]
#[test]
fn unix_extracted_worker_is_executable() {
    use std::os::unix::fs::PermissionsExt;

    let root = tempfile::tempdir().expect("temporary worker root");
    let worker = extract_worker(b"worker", root.path(), "1.8.6").expect("worker extraction");
    let permissions = fs::metadata(worker.path()).unwrap().permissions();

    assert_ne!(permissions.mode() & 0o111, 0);
}
