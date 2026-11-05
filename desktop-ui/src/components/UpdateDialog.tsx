import { Button, Modal } from "./controls";
import type { AvailableUpdate, DownloadProgress } from "../updater";

export function UpdateDialog({
  open,
  setOpen,
  currentVersion,
  update,
  portable,
  busy,
  installing,
  progress,
  error,
  install,
  openPortable,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
  currentVersion: string;
  update: AvailableUpdate | null;
  portable: boolean;
  busy: boolean;
  installing: boolean;
  progress: DownloadProgress | null;
  error: string;
  install: () => void;
  openPortable: () => void;
}) {
  const percent =
    progress?.total && progress.total > 0
      ? Math.min(100, Math.floor((progress.downloaded / progress.total) * 100))
      : null;

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!installing) setOpen(next);
      }}
      title="Update available"
      description={`Version ${update?.version ?? ""} is ready. You're using ${currentVersion}.`}
      footer={
        <>
          <Button disabled={installing} onClick={() => setOpen(false)}>
            Later
          </Button>
          {portable ? (
            <Button
              variant="primary"
              disabled={installing}
              onClick={openPortable}
            >
              Download portable update
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={installing || busy}
              onClick={install}
            >
              Install and restart
            </Button>
          )}
        </>
      }
    >
      {update?.notes && (
        <section className="update-notes" aria-label="Release notes">
          <h3>What's new</h3>
          <p>{update.notes}</p>
        </section>
      )}
      {portable ? (
        <div className="portable-update-note">
          <p>Download the portable version for your computer.</p>
          <p>Close the app before replacing it.</p>
          <p>Keep the files beside the executable to retain your settings.</p>
        </div>
      ) : (
        <p className="field-note">
          {busy
            ? "Finish the current job before installing an update."
            : "The update downloads and installs after you choose Install and restart."}
        </p>
      )}
      {installing && (
        <div className="update-progress">
          <p role="status">
            {percent === null
              ? "Downloading update…"
              : `Downloading update… ${percent}%`}
          </p>
          {progress?.total !== null && progress?.total !== undefined && (
            <progress
              value={progress.downloaded}
              max={progress.total || 1}
              aria-label="Update download progress"
            />
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
    </Modal>
  );
}
