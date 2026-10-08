use std::{
    error::Error,
    fmt, fs,
    path::{Path, PathBuf},
};

use tempfile::{Builder, TempDir};

/// An extracted worker executable and the private temporary directory that owns it.
///
/// Keep this value alive for as long as a worker process can still be running.
#[derive(Debug)]
pub struct ExtractedWorker {
    path: PathBuf,
    _directory: TempDir,
}

impl ExtractedWorker {
    pub fn path(&self) -> &Path {
        &self.path
    }
}

#[derive(Debug)]
pub enum WorkerBundleError {
    Empty,
    CreateDirectory(std::io::Error),
    WriteExecutable(std::io::Error),
    SetExecutablePermissions(std::io::Error),
}

impl fmt::Display for WorkerBundleError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Empty => formatter.write_str(
                "The bundled Python worker is missing or empty. Rebuild the app package before starting a job.",
            ),
            Self::CreateDirectory(_) => {
                formatter.write_str("A private temporary folder for the Python worker could not be created.")
            }
            Self::WriteExecutable(_) => {
                formatter.write_str("The bundled Python worker could not be extracted.")
            }
            Self::SetExecutablePermissions(_) => {
                formatter.write_str("The extracted Python worker could not be made executable.")
            }
        }
    }
}

impl Error for WorkerBundleError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Empty => None,
            Self::CreateDirectory(error)
            | Self::WriteExecutable(error)
            | Self::SetExecutablePermissions(error) => Some(error),
        }
    }
}

/// Extract a bundled worker into a unique, app-owned temporary directory.
pub fn extract_worker(
    data: &[u8],
    temp_root: &Path,
    version: &str,
) -> Result<ExtractedWorker, WorkerBundleError> {
    if data.is_empty() {
        return Err(WorkerBundleError::Empty);
    }

    let safe_version = version
        .chars()
        .filter(|character| {
            character.is_ascii_alphanumeric() || *character == '.' || *character == '-'
        })
        .collect::<String>();
    let prefix = format!(
        "trains-downloader-{}-",
        if safe_version.is_empty() {
            "app"
        } else {
            &safe_version
        }
    );
    let directory = Builder::new()
        .prefix(&prefix)
        .tempdir_in(temp_root)
        .map_err(WorkerBundleError::CreateDirectory)?;
    let path = directory.path().join(worker_file_name());
    fs::write(&path, data).map_err(WorkerBundleError::WriteExecutable)?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let permissions = fs::Permissions::from_mode(0o700);
        fs::set_permissions(&path, permissions)
            .map_err(WorkerBundleError::SetExecutablePermissions)?;
    }

    Ok(ExtractedWorker {
        path,
        _directory: directory,
    })
}

fn worker_file_name() -> &'static str {
    if cfg!(windows) {
        "worker.exe"
    } else {
        "worker"
    }
}

pub(crate) const EMBEDDED_WORKER: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/worker.bin"));
