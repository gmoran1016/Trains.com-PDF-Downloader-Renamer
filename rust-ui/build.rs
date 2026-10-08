use std::{env, fs, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=TRAINSDOWNLOADER_WORKER");

    let out_dir = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo must set OUT_DIR"));
    let output = out_dir.join("worker.bin");
    let profile = env::var("PROFILE").unwrap_or_default();

    match env::var_os("TRAINSDOWNLOADER_WORKER") {
        Some(worker_path) => {
            let worker_path = PathBuf::from(worker_path);
            println!("cargo:rerun-if-changed={}", worker_path.display());
            let metadata = fs::metadata(&worker_path).unwrap_or_else(|error| {
                panic!(
                    "TRAINSDOWNLOADER_WORKER points to an unreadable file ({}): {error}",
                    worker_path.display()
                )
            });
            assert!(
                metadata.is_file() && metadata.len() > 0,
                "TRAINSDOWNLOADER_WORKER must point to a non-empty worker executable"
            );
            fs::copy(&worker_path, &output)
                .unwrap_or_else(|error| panic!("could not embed the Python worker: {error}"));
        }
        None if profile == "release" => {
            panic!(
                "TRAINSDOWNLOADER_WORKER is required for release builds; package the Python worker first"
            );
        }
        None => {
            // A zero-byte development stub keeps cargo test and desktop smoke builds simple.
            // EmbeddedWorkerLauncher rejects it before attempting to spawn a process.
            fs::write(&output, []).expect("could not write the empty development worker stub");
        }
    }
}
