import { ArrowDownToLine } from "lucide-react";
import { Button, CheckField, PathField, Section } from "./controls";
import type {
  JobKind,
  OrganizerSummary,
  Settings,
  Snapshot,
  WorkArea,
} from "../types";
const publications = [
  ["Model Railroader", "MRR", "Monthly"],
  ["Trains Magazine", "TRN", "Monthly"],
  ["Classic Toy Trains", "CTT", "Monthly"],
  ["Classic Trains", "CTR", "Quarterly"],
  ["Garden Railways", "GRW", "Seasonal / archived"],
];
export const headings: Record<WorkArea, [string, string]> = {
  magazines: [
    "Magazine archive",
    "Download publications into your local collection.",
  ],
  "track-plans": [
    "Track plans",
    "Download PDFs from the Model Railroader Track Plan Database.",
  ],
  organize: [
    "PDF organizer",
    "Sort PDFs, review coverage, and find missing issues.",
  ],
};
interface Props {
  area: WorkArea;
  settings: Settings;
  state: Snapshot;
  patch: (changes: Partial<Settings>) => Promise<void>;
  draft: (changes: Partial<Settings>) => void;
  onError: (message: string) => void;
}
export function Workflows({
  area,
  settings: s,
  state,
  patch,
  draft,
  onError,
}: Props) {
  const path = (
    field: "base_dir" | "track_plans_dir" | "org_src" | "org_dst",
    label: string,
  ) => (
    <PathField
      key={field}
      label={label}
      field={field}
      value={s[field]}
      disabled={state.busy}
      onChange={(value) => draft({ [field]: value })}
      onCommit={(value) => patch({ [field]: value })}
      onError={onError}
    />
  );
  const check = (
    key:
      | "newest_first"
      | "include_specials"
      | "test_mode"
      | "headless"
      | "org_headless",
    label: string,
  ) => (
    <CheckField
      key={key}
      label={label}
      checked={s[key]}
      disabled={state.busy}
      onChange={(checked) => void patch({ [key]: checked }).catch(() => {})}
    />
  );
  if (area === "magazines")
    return (
      <>
        <Section
          title="Publications"
          actions={
            <>
              <Button
                variant="quiet"
                disabled={state.busy}
                onClick={() =>
                  void patch({
                    selected_magazines: publications.map(([name]) => name),
                  }).catch(() => {})
                }
              >
                Select all
              </Button>
              <Button
                variant="quiet"
                disabled={state.busy}
                onClick={() =>
                  void patch({ selected_magazines: [] }).catch(() => {})
                }
              >
                Clear all
              </Button>
            </>
          }
        >
          <div className="publication-list">
            {publications.map(([name, prefix, schedule]) => (
              <label key={name} className="publication-row">
                <input
                  type="checkbox"
                  checked={s.selected_magazines.includes(name)}
                  disabled={state.busy}
                  onChange={(event) =>
                    void patch({
                      selected_magazines: event.target.checked
                        ? [...s.selected_magazines, name]
                        : s.selected_magazines.filter(
                            (value) => value !== name,
                          ),
                    }).catch(() => {})
                  }
                />
                <span className="publication-name">
                  {name}
                  <span className="publication-schedule">{schedule}</span>
                </span>
                <span className="publication-prefix">{prefix}</span>
              </label>
            ))}
          </div>
        </Section>
        <Section title="Destination">
          {path("base_dir", "Magazine save folder")}
          <p className="field-note">
            Existing PDFs are checked before downloads resume.
          </p>
        </Section>
        <Section title="Download options">
          <div className="options-grid">
            {check("newest_first", "Newest issues first")}
            {check("include_specials", "Include special issues")}
            {check("test_mode", "Test mode (first 3 archive pages)")}
            {check("headless", "Keep magazine browser hidden")}
          </div>
        </Section>
      </>
    );
  if (area === "track-plans")
    return (
      <>
        <Section title="Destination">
          {path("track_plans_dir", "Track-plan save folder")}
          <p className="field-note">
            Original filenames are kept. Plans already in this folder are
            skipped.
          </p>
        </Section>
        <Section title="Source">
          <p className="source-name">Model Railroader Track Plan Database</p>
          <p className="muted">
            The app scans the database and downloads the available plan PDFs
            using your shared account access.
          </p>
        </Section>
      </>
    );
  return (
    <>
      <Section title="Folders">
        <div className="folder-fields">
          {path("org_src", "Source folder")}
          {path("org_dst", "Archive destination")}
        </div>
        <div className="field prefix-field">
          <label htmlFor="org_prefix">Magazine prefix</label>
          <select
            id="org_prefix"
            value={s.org_prefix}
            disabled={state.busy}
            onChange={(event) =>
              void patch({ org_prefix: event.target.value }).catch(() => {})
            }
          >
            {["Auto-detect", "MRR", "TRN", "CTT", "CTR", "GRW"].map(
              (prefix) => (
                <option key={prefix}>{prefix}</option>
              ),
            )}
          </select>
          <p className="field-note">
            Use Auto-detect unless filenames need a hint.
          </p>
        </div>
        {check("org_headless", "Hide browser for missing-issue downloads")}
      </Section>
      {state.organizer_summary ? (
        <OrganizerResults
          summary={state.organizer_summary}
          verified={
            state.organizer_outcome === "success" ||
            state.organizer_outcome === "no-results"
          }
        />
      ) : (
        <div className="empty-summary">
          <h2>Coverage report</h2>
          <p className="muted">
            After a scan, review organized files, conflicts, and missing issues
            here.
          </p>
        </div>
      )}
    </>
  );
}
function OrganizerResults({
  summary: s,
  verified,
}: {
  summary: OrganizerSummary;
  verified: boolean;
}) {
  const complete = s.scan_complete && verified;
  const metrics: [keyof OrganizerSummary, string][] = [
    ["moved", "Moved"],
    ["already_correct", "Already correct"],
    ["unrecognized", "Unrecognized"],
    ["corrupt", "Corrupt"],
    ["conflicts", "Conflicts"],
    ["metadata_stamped", "Metadata updated"],
  ];
  const report = Array.isArray(s.report)
    ? s.report.filter((line) => typeof line === "string")
    : [];
  const gaps = Object.entries(s.missing_by_prefix_year || {}).flatMap(
    ([prefix, years]) =>
      Object.entries(years).flatMap(([year, months]) =>
        Array.isArray(months) && months.length
          ? [{ prefix, year, months }]
          : [],
      ),
  );
  return (
    <Section
      title="Scan results"
      actions={
        <span className={`scan-state ${complete ? "complete" : "incomplete"}`}>
          {complete ? "Complete scan" : "Incomplete scan"}
        </span>
      }
    >
      {!complete && (
        <p className="inline-warning">
          These are partial findings. Run a complete scan before downloading
          missing issues.
        </p>
      )}
      <dl className="summary-counts">
        {metrics.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{typeof s[key] === "number" ? String(s[key]) : "0"}</dd>
          </div>
        ))}
      </dl>
      {gaps.length > 0 && (
        <div className="coverage-index">
          <h3>Missing issues</h3>
          {gaps.map(({ prefix, year, months }) => (
            <div className="coverage-row" key={prefix + year}>
              <strong>
                {prefix} <span>{year}</span>
              </strong>
              <span>{months.join(", ")}</span>
            </div>
          ))}
        </div>
      )}
      {report.length > 0 && (
        <details className="report-details">
          <summary>
            Full coverage report <span>{report.length} lines</span>
          </summary>
          <div>
            {report.map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>
        </details>
      )}
    </Section>
  );
}
export function WorkflowAction({
  area,
  settings: s,
  state,
  start,
  onClearCache,
}: {
  area: WorkArea;
  settings: Settings;
  state: Snapshot;
  start: (kind: JobKind) => void;
  onClearCache: () => void;
}) {
  const labels: Record<WorkArea, string> = {
    magazines: "Download selected magazines",
    "track-plans": "Download all track plans",
    organize: "Organize PDFs",
  };
  const ready =
    area === "magazines"
      ? s.selected_magazines.length > 0 && !!s.base_dir.trim()
      : area === "track-plans"
        ? !!s.track_plans_dir.trim()
        : !!s.org_src.trim() && !!s.org_dst.trim();
  const hint = !ready
    ? area === "organize"
      ? "Choose source and destination folders."
      : area === "magazines"
        ? "Select publications and a destination."
        : "Choose a destination folder."
    : "";
  return (
    <footer className="workflow-actions">
      <div className="primary-actions">
        <Button
          data-layout-critical
          variant="primary"
          disabled={!ready || state.busy}
          onClick={() => start(area)}
        >
          <ArrowDownToLine size={17} />
          {labels[area]}
        </Button>
        {area === "organize" && state.can_download_missing && (
          <Button
            data-layout-critical
            onClick={() => start("download-missing")}
          >
            Download Missing
          </Button>
        )}
        {hint && <span className="action-hint">{hint}</span>}
      </div>
      {area === "magazines" && (
        <Button variant="quiet" disabled={state.busy} onClick={onClearCache}>
          Clear cache
        </Button>
      )}
    </footer>
  );
}
