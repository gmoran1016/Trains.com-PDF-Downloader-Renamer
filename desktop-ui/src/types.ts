export type WorkArea = "magazines" | "track-plans" | "organize";
export type JobKind = WorkArea | "download-missing";
export type Outcome =
  "idle" | "running" | "success" | "no-results" | "failed" | "cancelled";
export interface Settings {
  base_dir: string;
  track_plans_dir: string;
  cookies_path: string;
  headless: boolean;
  test_mode: boolean;
  newest_first: boolean;
  include_specials: boolean;
  selected_magazines: string[];
  org_src: string;
  org_dst: string;
  org_prefix: string;
  org_headless: boolean;
  selected_page: WorkArea;
  window_width: number;
  window_height: number;
  activity_height: number;
  activity_collapsed: boolean;
  dark_mode: boolean;
}
export interface LogEntry {
  level: "debug" | "info" | "warning" | "error";
  message: string;
}
export interface OrganizerSummary {
  scan_complete?: boolean;
  moved?: number;
  already_correct?: number;
  unrecognized?: number;
  corrupt?: number;
  conflicts?: number;
  metadata_stamped?: number;
  report?: string[];
  missing_by_prefix_year?: Record<string, Record<string, string[]>>;
}
export interface Snapshot {
  settings: Settings;
  settings_error: string | null;
  busy: boolean;
  job: {
    outcome: Outcome;
    message: string;
    done: number | null;
    total: number | null;
    per_magazine: Record<string, { done: number; total: number }>;
    stop_requested: boolean;
    summary: OrganizerSummary | null;
  };
  log_count: number;
  error_count: number;
  cookie_file_exists: boolean;
  organizer_summary: OrganizerSummary | null;
  organizer_outcome: Outcome;
  can_download_missing: boolean;
  notice: string | null;
  tray_available: boolean;
}
export interface ActivityPage {
  entries: LogEntry[];
  total: number;
}
