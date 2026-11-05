import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  FolderTree,
  Map,
  Settings as SettingsIcon,
  AlertCircle,
} from "lucide-react";
import { desktopInvoke, desktopListen, errorMessage } from "./desktop";
import type { JobKind, Settings, Snapshot, WorkArea } from "./types";
import { Button, Modal } from "./components/controls";
import { headings, WorkflowAction, Workflows } from "./components/Workflows";
import { SettingsDialog } from "./components/SettingsDialog";
import { Activity } from "./components/Activity";
import { UpdateDialog } from "./components/UpdateDialog";
import {
  checkForUpdates,
  getInstalledVersion,
  installAvailableUpdate,
  isPortableBuild,
  openPortableUpdate,
} from "./updater";
import type {
  AvailableUpdate,
  DownloadProgress,
  UpdateCheckStatus,
} from "./updater";
const navigation: [WorkArea, string, typeof BookOpen][] = [
  ["magazines", "Magazines", BookOpen],
  ["track-plans", "Track Plans", Map],
  ["organize", "Organize", FolderTree],
];
export default function App() {
  const [state, setState] = useState<Snapshot | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const [cacheOpen, setCacheOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [currentVersion, setCurrentVersion] = useState("");
  const [updateStatus, setUpdateStatus] = useState<UpdateCheckStatus>("idle");
  const [availableUpdate, setAvailableUpdate] =
    useState<AvailableUpdate | null>(null);
  const [updateError, setUpdateError] = useState("");
  const [portable, setPortable] = useState(false);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [updateProgress, setUpdateProgress] =
    useState<DownloadProgress | null>(null);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const startupUpdateCheckStarted = useRef(false);
  const updateCheckInFlight = useRef(false);
  const checkForUpdatesInSettings = async () => {
    if (updateCheckInFlight.current) return;
    updateCheckInFlight.current = true;
    setUpdateStatus("checking");
    setUpdateError("");
    try {
      const [version, isPortable] = await Promise.all([
        getInstalledVersion(),
        isPortableBuild(),
      ]);
      setCurrentVersion(version);
      setPortable(isPortable);
      const update = await checkForUpdates();
      setAvailableUpdate(update);
      if (update) {
        setUpdateStatus("available");
        setUpdateDialogOpen(true);
      } else {
        setUpdateStatus("current");
      }
    } catch (error) {
      setUpdateError(errorMessage(error));
      setUpdateProgress(null);
      setUpdateStatus("error");
    } finally {
      updateCheckInFlight.current = false;
    }
  };
  const installUpdate = async () => {
    setInstallingUpdate(true);
    setUpdateProgress({ downloaded: 0, total: null });
    setUpdateError("");
    try {
      await installAvailableUpdate(setUpdateProgress);
      setAvailableUpdate(null);
      setUpdateStatus("current");
      setUpdateDialogOpen(false);
    } catch (error) {
      setUpdateError(errorMessage(error));
      setUpdateProgress(null);
      setUpdateStatus("error");
    } finally {
      setInstallingUpdate(false);
    }
  };
  const downloadPortableUpdate = async () => {
    setUpdateError("");
    try {
      await openPortableUpdate();
    } catch (error) {
      setUpdateError(errorMessage(error));
      setUpdateStatus("error");
    }
  };
  useEffect(() => {
    let active = true;
    const unlisteners: (() => void)[] = [];
    const subscribe = async () => {
      for (const [event, callback] of [
        [
          "state-changed",
          (next: unknown) => {
            if (active) setState(next as Snapshot);
          },
        ],
        [
          "close-requested",
          () => {
            if (active) setCloseOpen(true);
          },
        ],
      ] as const) {
        const unlisten = await desktopListen(event, callback);
        if (active) unlisteners.push(unlisten);
        else unlisten();
      }
    };
    void subscribe()
      .then(() => desktopInvoke<Snapshot>("get_snapshot"))
      .then((next) => {
        if (active) {
          setState(next);
          setSettings(next.settings);
        }
      })
      .catch((error) => {
        if (active) setError(errorMessage(error));
      });
    return () => {
      active = false;
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, []);
  useEffect(() => {
    if (!state || startupUpdateCheckStarted.current) return;
    startupUpdateCheckStarted.current = true;
    void checkForUpdatesInSettings();
  }, [state]);
  useEffect(() => {
    document.documentElement.dataset.theme = settings?.dark_mode
      ? "dark"
      : "light";
  }, [settings?.dark_mode]);
  const patch = (changes: Partial<Settings>) => {
    setSettings((current) => (current ? { ...current, ...changes } : current));
    const update = queue.current
      .catch(() => {})
      .then(async () => {
        const next = await desktopInvoke<Snapshot>("update_settings", {
          changes,
        });
        setState(next);
        setError("");
      });
    queue.current = update;
    void update.catch((error) => setError(errorMessage(error)));
    return update;
  };
  const start = async (kind: JobKind) => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      await queue.current.catch(() => {});
      // Retry all displayed job options atomically so an earlier save failure cannot
      // silently start with old destinations or options after a navigation save.
      const {
        base_dir,
        track_plans_dir,
        cookies_path,
        headless,
        test_mode,
        newest_first,
        include_specials,
        selected_magazines,
        org_src,
        org_dst,
        org_prefix,
        org_headless,
      } = settings!;
      setState(
        await desktopInvoke<Snapshot>("update_settings", {
          changes: {
            base_dir,
            track_plans_dir,
            cookies_path,
            headless,
            test_mode,
            newest_first,
            include_specials,
            selected_magazines,
            org_src,
            org_dst,
            org_prefix,
            org_headless,
          },
        }),
      );
      setState(await desktopInvoke<Snapshot>("start_job", { kind }));
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setWorking(false);
    }
  };
  const stop = () => {
    void desktopInvoke<Snapshot>("stop_job")
      .then(setState)
      .catch((error) => setError(errorMessage(error)));
  };
  const close = async (choice: string) => {
    try {
      await desktopInvoke("close_action", { choice });
      setCloseOpen(false);
    } catch (error) {
      setError(errorMessage(error));
    }
  };
  if (!state || !settings)
    return (
      <main className="connection-state">
        <BookOpen size={36} />
        <h1>Trains.com Archive</h1>
        <p role={error ? "alert" : "status"}>
          {error || "Connecting to your archive…"}
        </p>
        {error && (
          <Button onClick={() => location.reload()}>Retry connection</Button>
        )}
      </main>
    );
  const area = settings.selected_page;
  const [heading, description] = headings[area];
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <BookOpen size={23} aria-hidden="true" />
          <span>
            Trains.com <strong>Archive</strong>
          </span>
        </div>
        <Button
          data-layout-critical
          variant="quiet"
          onClick={() => setAccountOpen(true)}
          aria-label="Settings"
        >
          <SettingsIcon size={18} />
          <span>Settings</span>
        </Button>
      </header>
      <nav className="navigation" aria-label="Work areas">
        {navigation.map(([page, label, Icon]) => (
          <button
            type="button"
            data-layout-critical
            key={page}
            className={area === page ? "selected" : ""}
            aria-current={area === page ? "page" : undefined}
            onClick={() => void patch({ selected_page: page }).catch(() => {})}
          >
            <Icon size={20} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <main className="workspace" aria-label={heading}>
        <div className="work-scroll" key={area}>
          <div className="work-content">
            <div className="work-heading">
              <h1>{heading}</h1>
              <p>{description}</p>
            </div>
            {(error || state.settings_error) && (
              <div role="alert" className="error-banner">
                <AlertCircle size={20} />
                <span>{error || state.settings_error}</span>
                <Button
                  variant="quiet"
                  onClick={() => setError("")}
                  disabled={!error}
                >
                  Dismiss
                </Button>
              </div>
            )}
            {state.notice && (
              <p className="notice" role="status">
                {state.notice}
              </p>
            )}
            <Workflows
              area={area}
              settings={settings}
              state={{ ...state, busy: state.busy || working }}
              patch={patch}
              draft={(changes) =>
                setSettings((current) =>
                  current ? { ...current, ...changes } : current,
                )
              }
              onError={setError}
            />
          </div>
        </div>
        <WorkflowAction
          area={area}
          settings={settings}
          state={{ ...state, busy: state.busy || working }}
          start={(kind) => void start(kind)}
          onClearCache={() => setCacheOpen(true)}
        />
      </main>
      <Activity
        state={state}
        settings={settings}
        patch={patch}
        stop={stop}
        onError={setError}
      />
      <SettingsDialog
        open={accountOpen}
        setOpen={setAccountOpen}
        settings={settings}
        cookieExists={state.cookie_file_exists}
        busy={state.busy}
        save={patch}
        currentVersion={currentVersion}
        updateStatus={updateStatus}
        updateVersion={availableUpdate?.version ?? null}
        updateError={updateError}
        checkForUpdates={() => void checkForUpdatesInSettings()}
      />
      <UpdateDialog
        open={updateDialogOpen}
        setOpen={setUpdateDialogOpen}
        currentVersion={currentVersion}
        update={availableUpdate}
        portable={portable}
        busy={state.busy || working}
        installing={installingUpdate}
        progress={updateProgress}
        error={updateError}
        install={() => void installUpdate()}
        openPortable={() => void downloadPortableUpdate()}
      />
      <Modal
        open={cacheOpen}
        onOpenChange={setCacheOpen}
        title="Clear download cache?"
        description="Remove the download progress and special-issue index so they can be rebuilt."
        footer={
          <>
            <Button onClick={() => setCacheOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              disabled={state.busy}
              onClick={() =>
                void desktopInvoke("clear_cache")
                  .then(() => setCacheOpen(false))
                  .catch((error) => setError(errorMessage(error)))
              }
            >
              Clear cache
            </Button>
          </>
        }
      >
        <p>Your settings, account file, logs, and downloaded PDFs are kept.</p>
      </Modal>
      <Modal
        open={closeOpen}
        onOpenChange={setCloseOpen}
        title="A job is still running"
        description="Choose how to handle the current job before closing."
        footer={
          <>
            <Button onClick={() => void close("cancel")}>Cancel</Button>
            <Button
              disabled={!state.tray_available}
              onClick={() => void close("tray")}
            >
              Minimize to Tray
            </Button>
            <Button variant="danger" onClick={() => void close("stop-quit")}>
              Stop & Quit
            </Button>
          </>
        }
      >
        <p>
          Stop & Quit waits for the worker to finish safely. Completed files are
          kept.
        </p>
        {!state.tray_available && (
          <p className="field-note">
            The system tray is unavailable on this desktop.
          </p>
        )}
      </Modal>
    </div>
  );
}
