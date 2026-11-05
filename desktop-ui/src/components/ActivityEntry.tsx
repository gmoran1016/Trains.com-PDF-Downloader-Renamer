import {
  ArrowRight,
  BookOpen,
  Check,
  Circle,
  CircleAlert,
  List,
  Minus,
} from "lucide-react";
import type { LogEntry } from "../types";

const actions: Record<
  string,
  { label: string; icon: typeof Circle; note?: string }
> = {
  moved: { label: "Moved", icon: ArrowRight },
  unchanged: { label: "Already organized", icon: Check },
  conflict: {
    label: "Conflict",
    icon: CircleAlert,
    note: "Both files preserved.",
  },
  corrupt: {
    label: "Unreadable PDF",
    icon: CircleAlert,
    note: "Left in place; the PDF could not be read.",
  },
  unrecognized: {
    label: "Skipped",
    icon: Minus,
    note: "Left in place; no publication date found.",
  },
  stage: { label: "Stage", icon: Circle },
  coverage: { label: "Coverage", icon: BookOpen },
  summary: { label: "Summary", icon: List },
  warning: { label: "Warning", icon: CircleAlert },
  error: { label: "Error", icon: CircleAlert },
};

export function ActivityEntry({ entry }: { entry: LogEntry }) {
  const [first, ...details] = entry.message.trim().split(/\r?\n/);
  const tag = first.match(/^\[([a-z-]+)\]\s*/i);
  const action = tag ? actions[tag[1].toLowerCase()] : undefined;
  const headline = action ? first.slice(tag![0].length) : first;
  const label =
    action?.label ??
    (entry.level === "debug"
      ? "Detail"
      : entry.level[0].toUpperCase() + entry.level.slice(1));
  const Icon =
    action?.icon ??
    (entry.level === "error" || entry.level === "warning"
      ? CircleAlert
      : Circle);
  const date = entry.timestamp_ms ? new Date(entry.timestamp_ms) : null;
  const metadataWarning = details.some((line) =>
    line.startsWith("Metadata warning:"),
  );
  const partialCoverage =
    tag?.[1] === "coverage" &&
    details.some((line) => line.startsWith("Scan: Partial"));

  return (
    <div className={`log-row ${entry.level}`}>
      <time
        className="log-time"
        dateTime={date?.toISOString()}
        title={date?.toLocaleString()}
      >
        {date
          ? date.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            })
          : "—"}
      </time>
      <span className="log-level">
        <Icon size={15} aria-hidden="true" />
        {label}
      </span>
      <div className="log-content">
        <span className={action ? "log-headline" : undefined}>{headline}</span>
        {action?.note && <p className="log-note">{action.note}</p>}
        {metadataWarning && (
          <p className="log-note warning">Metadata needs attention.</p>
        )}
        {partialCoverage && (
          <p className="log-note warning">
            Partial scan; coverage includes processed files only.
          </p>
        )}
        {details.length > 0 && (
          <details>
            <summary>Details</summary>
            <div className="log-details">{details.join("\n")}</div>
          </details>
        )}
      </div>
    </div>
  );
}
