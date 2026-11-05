import { useEffect, useState } from "react";
import { CheckField, Button, Modal } from "./controls";
import { desktopInvoke, errorMessage } from "../desktop";
import type { Settings } from "../types";
import type { UpdateCheckStatus } from "../updater";
export function SettingsDialog({
  open,
  setOpen,
  settings,
  cookieExists,
  busy,
  save,
  currentVersion,
  updateStatus,
  updateVersion,
  updateError,
  checkForUpdates,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
  settings: Settings;
  cookieExists: boolean;
  busy: boolean;
  save: (changes: Partial<Settings>) => Promise<void>;
  currentVersion: string;
  updateStatus: UpdateCheckStatus;
  updateVersion: string | null;
  updateError: string;
  checkForUpdates: () => void;
}) {
  const [draft, setDraft] = useState(settings);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (open) {
      setDraft(settings);
      setError("");
    }
  }, [open]); // Snapshot updates never overwrite an in-progress edit.
  const submit = async () => {
    setSaving(true);
    try {
      await save({
        cookies_path: draft.cookies_path,
        headless: draft.headless,
        org_headless: draft.org_headless,
        dark_mode: draft.dark_mode,
      });
      setOpen(false);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };
  const choose = async () => {
    try {
      const value = await desktopInvoke<string | null>("choose_path", {
        field: "cookies_path",
        initial: draft.cookies_path,
      });
      if (value !== null) setDraft({ ...draft, cookies_path: value });
    } catch (error) {
      setError(errorMessage(error));
    }
  };
  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      title="Account & appearance"
      description="Shared access settings for your magazine and track-plan downloads."
      footer={
        <>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="primary"
            disabled={saving || busy}
            onClick={() => void submit()}
          >
            {saving ? "Saving…" : "Save settings"}
          </Button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="cookie-path">Cookie file path</label>
        <div className="path-control">
          <input
            id="cookie-path"
            value={draft.cookies_path}
            disabled={busy}
            spellCheck={false}
            onChange={(event) =>
              setDraft({ ...draft, cookies_path: event.target.value })
            }
          />
          <Button disabled={busy} onClick={() => void choose()}>
            Choose file
          </Button>
        </div>
        <p className="field-note">
          {draft.cookies_path === settings.cookies_path
            ? cookieExists
              ? "Cookie file found."
              : "Cookie file not found."
            : "Save this path to check the file."}{" "}
          Sign-in is checked when a job starts.
        </p>
      </div>
      <div className="settings-group">
        <h3>Browser visibility</h3>
        <CheckField
          label="Keep magazine browser hidden"
          checked={draft.headless}
          disabled={busy}
          onChange={(checked) => setDraft({ ...draft, headless: checked })}
        />
        <CheckField
          label="Hide browser for missing-issue downloads"
          checked={draft.org_headless}
          disabled={busy}
          onChange={(checked) => setDraft({ ...draft, org_headless: checked })}
        />
        <p className="field-note">
          On first use, Chrome opens for you to sign in.
        </p>
      </div>
      <div className="settings-group">
        <h3>Appearance</h3>
        <CheckField
          label="Dark mode"
          checked={draft.dark_mode}
          onChange={(checked) => setDraft({ ...draft, dark_mode: checked })}
        />
      </div>
      <div className="settings-group">
        <h3>Updates</h3>
        <p className="field-note">
          Version {currentVersion || "Checking…"}
        </p>
        <p
          className={updateStatus === "error" ? "inline-error" : "field-note"}
          role={updateStatus === "error" ? "alert" : "status"}
        >
          {updateStatus === "checking" && "Checking GitHub for updates…"}
          {updateStatus === "current" && "You're up to date."}
          {updateStatus === "available" &&
            `Update available: ${updateVersion ?? "new version"}`}
          {updateStatus === "error" && updateError}
          {updateStatus === "idle" && "Check GitHub for a newer release."}
        </p>
        <Button
          disabled={updateStatus === "checking"}
          onClick={checkForUpdates}
        >
          {updateStatus === "checking" ? "Checking…" : "Check for updates"}
        </Button>
      </div>
      {busy && (
        <p className="field-note">
          Account changes can be saved after the current job finishes.
        </p>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
    </Modal>
  );
}
