import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
interface QABridge {
  invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
  listen: (
    event: string,
    callback: (payload: unknown) => void,
  ) => Promise<() => void>;
}
declare global {
  interface Window {
    __TRAINS_QA__?: QABridge;
  }
}
export async function desktopInvoke<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (import.meta.env.DEV && window.__TRAINS_QA__)
    return (await window.__TRAINS_QA__.invoke(command, args)) as T;
  if (!isTauri())
    throw new Error("Open the desktop application to connect to your archive.");
  return invoke<T>(command, args);
}
export async function desktopListen<T>(
  event: string,
  callback: (payload: T) => void,
): Promise<() => void> {
  if (import.meta.env.DEV && window.__TRAINS_QA__)
    return window.__TRAINS_QA__.listen(event, (payload) =>
      callback(payload as T),
    );
  if (!isTauri()) return () => {};
  return listen<T>(event, ({ payload }) => callback(payload));
}
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
