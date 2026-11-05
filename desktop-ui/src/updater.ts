import { getVersion } from "@tauri-apps/api/app";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { relaunch } from "@tauri-apps/plugin-process";
import { check } from "@tauri-apps/plugin-updater";
import { desktopInvoke } from "./desktop";

export const PORTABLE_DOWNLOAD_URL =
  "https://github.com/gmoran1016/Trains.com-PDF-Downloader-Renamer/releases/latest/download/TrainsDownloader-windows.exe";

export interface AvailableUpdate {
  version: string;
  notes: string | null;
}

export interface DownloadProgress {
  downloaded: number;
  total: number | null;
}

export type UpdateCheckStatus =
  | "idle"
  | "checking"
  | "current"
  | "available"
  | "error";

interface UpdaterQABridge {
  records: { action: string; url?: string }[];
  getVersion: () => Promise<string>;
  check: () => Promise<AvailableUpdate | null>;
  install: (onProgress: (progress: DownloadProgress) => void) => Promise<void>;
  relaunch: () => Promise<void>;
  openUrl: (url: string) => Promise<void>;
}

declare global {
  interface Window {
    __TRAINS_UPDATER_QA__?: UpdaterQABridge;
  }
}

type TauriUpdate = NonNullable<Awaited<ReturnType<typeof check>>>;
let pendingUpdate: TauriUpdate | null = null;

function qaBridge(): UpdaterQABridge | undefined {
  return import.meta.env.DEV ? window.__TRAINS_UPDATER_QA__ : undefined;
}

export async function getInstalledVersion(): Promise<string> {
  const qa = qaBridge();
  if (qa) return qa.getVersion();
  if (!isTauri()) throw new Error("Open the desktop app to check its version.");
  return getVersion();
}

export async function isPortableBuild(): Promise<boolean> {
  if (qaBridge()) return desktopInvoke<boolean>("is_portable");
  if (!isTauri()) return false;
  return desktopInvoke<boolean>("is_portable");
}

export async function checkForUpdates(): Promise<AvailableUpdate | null> {
  const qa = qaBridge();
  if (qa) return qa.check();
  if (!isTauri()) throw new Error("Open the desktop app to check for updates.");

  pendingUpdate = await check();
  return pendingUpdate
    ? {
        version: pendingUpdate.version,
        notes: pendingUpdate.body?.trim() || null,
      }
    : null;
}

export async function installAvailableUpdate(
  onProgress: (progress: DownloadProgress) => void,
): Promise<void> {
  const qa = qaBridge();
  if (qa) {
    await qa.install(onProgress);
    return qa.relaunch();
  }
  if (!isTauri()) throw new Error("Open the desktop app to install updates.");
  if (!pendingUpdate) throw new Error("Check for an update before installing.");

  let downloaded = 0;
  let total: number | null = null;
  await pendingUpdate.downloadAndInstall((event) => {
    if (event.event === "Started") total = event.data.contentLength ?? null;
    if (event.event === "Progress") downloaded += event.data.chunkLength;
    if (event.event === "Finished" && total !== null) downloaded = total;
    onProgress({ downloaded, total });
  });
  await relaunch();
}

export async function openPortableUpdate(): Promise<void> {
  const qa = qaBridge();
  if (qa) return qa.openUrl(PORTABLE_DOWNLOAD_URL);
  if (!isTauri()) throw new Error("Open the desktop app to download updates.");
  await openUrl(PORTABLE_DOWNLOAD_URL);
}
