import type { Page } from "@playwright/test";
export async function desktopFixture(
  page: Page,
  options: {
    dark?: boolean;
    outcome?: string;
    expanded?: boolean;
    summary?: boolean;
    incomplete?: boolean;
    failSetting?: string;
  } = {},
) {
  await page.addInitScript((options) => {
    const settings = {
      base_dir:
        "D:/Railroad archive/Magazines/a very long folder name with spaces/Collected issues",
      track_plans_dir: "D:/Track plans",
      cookies_path: "D:/Private/session_cookies.json",
      headless: false,
      test_mode: false,
      newest_first: true,
      include_specials: true,
      selected_magazines: [
        "Model Railroader",
        "Trains Magazine",
        "Classic Toy Trains",
        "Classic Trains",
        "Garden Railways",
      ],
      org_src: "D:/Unsorted PDFs",
      org_dst: "D:/Organized archive",
      org_prefix: "Auto-detect",
      org_headless: false,
      selected_page: "magazines",
      window_width: 1120,
      window_height: 760,
      activity_height: 340,
      activity_collapsed: !options.expanded,
      dark_mode: !!options.dark,
    };
    const summary = options.summary
      ? {
          scan_complete: !options.incomplete,
          moved: 8,
          already_correct: 12,
          unrecognized: 2,
          corrupt: 1,
          conflicts: 3,
          metadata_stamped: 5,
          report: ["MRR 2024: missing January, March"],
          missing_by_prefix_year: { MRR: { "2024": ["January", "March"] } },
        }
      : null;
    const outcome = options.outcome || "idle";
    let current = {
      settings,
      settings_error: null,
      busy: outcome === "running",
      job: {
        outcome,
        message:
          outcome === "running"
            ? "Downloading an issue with a very long name from the magazine archive; waiting for the browser to finish safely."
            : "Ready",
        done: outcome === "running" ? 3 : null,
        total: outcome === "running" ? 12 : null,
        per_magazine: {},
        summary: null,
        logs: [],
        errors: [],
        stop_requested: false,
      },
      log_count: 0,
      error_count: 0,
      cookie_file_exists: true,
      organizer_summary: summary,
      organizer_outcome: options.incomplete ? "failed" : "success",
      can_download_missing: !!summary && !options.incomplete,
      notice: null,
      tray_available: true,
    };
    let logs = Array.from({ length: 260 }, (_, index) => ({
      level: index % 20 === 0 ? "error" : "info",
      message:
        index % 20 === 0
          ? "A network request failed " + index
          : "Downloaded issue " + index,
    }));
    current.log_count = logs.length;
    current.error_count = 13;
    const listeners = new Map<string, Set<(value: unknown) => void>>();
    const records: { command: string; args: Record<string, unknown> }[] = [];
    let streamTimer: ReturnType<typeof setInterval> | undefined;
    const emit = () =>
      listeners
        .get("state-changed")
        ?.forEach((listener) => listener(structuredClone(current)));
    const qa = {
      records,
      streaming: false,
      startLogStream: () => {
        let sequence = 0;
        qa.streaming = true;
        const append = () => {
          sequence += 1;
          logs.unshift({
            level: sequence === 1 ? "error" : "info",
            message: "Streaming event " + sequence,
          });
          current.log_count = logs.length;
          if (sequence === 1) current.error_count += 1;
          emit();
        };
        append();
        streamTimer = setInterval(append, 50);
      },
      stopLogStream: () => {
        clearInterval(streamTimer);
        qa.streaming = false;
      },
      listen: async (event: string, callback: (value: unknown) => void) => {
        if (!listeners.has(event)) listeners.set(event, new Set());
        listeners.get(event)!.add(callback);
        return () => listeners.get(event)?.delete(callback);
      },
      invoke: async (command: string, args: Record<string, unknown> = {}) => {
        records.push({ command, args });
        if (command === "get_snapshot") return structuredClone(current);
        if (command === "update_settings") {
          if (
            options.failSetting &&
            Object.hasOwn(args.changes as object, options.failSetting)
          )
            throw new Error(
              "Settings could not be saved. Check folder permissions.",
            );
          Object.assign(current.settings, args.changes);
          emit();
          return structuredClone(current);
        }
        if (command === "start_job") {
          current.busy = true;
          current.job.outcome = "running";
          current.job.message = "Starting the worker…";
          current.can_download_missing = false;
          emit();
          return structuredClone(current);
        }
        if (command === "stop_job") {
          current.job.stop_requested = true;
          current.job.message = "Stopping at the next safe point…";
          emit();
          return structuredClone(current);
        }
        if (command === "get_activity") {
          const matches = logs.filter((log) =>
            log.message
              .toLowerCase()
              .includes(String(args.query || "").toLowerCase()),
          );
          return {
            entries: matches.slice(
              Number(args.offset || 0),
              Number(args.offset || 0) + Number(args.limit || 100),
            ),
            total: matches.length,
          };
        }
        if (command === "clear_activity") {
          logs = [];
          current.log_count = 0;
          current.error_count = 0;
          emit();
          return structuredClone(current);
        }
        if (command === "choose_path") return "D:/Selected folder";
        if (command === "clear_cache") return "Download cache cleared.";
        if (command === "copy_errors" || command === "close_action")
          return null;
        throw new Error("Unexpected desktop command: " + command);
      },
      emitClose: () =>
        listeners.get("close-requested")?.forEach((listener) => listener(null)),
    };
    (window as unknown as { __TRAINS_QA__: typeof qa }).__TRAINS_QA__ = qa;
  }, options);
}
