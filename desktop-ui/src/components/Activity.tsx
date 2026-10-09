import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Check,
  Circle,
  CircleAlert,
  LoaderCircle,
  Pause,
  Search,
} from "lucide-react";
import { Button } from "./controls";
import { desktopInvoke, errorMessage } from "../desktop";
import type { ActivityPage, Outcome, Settings, Snapshot } from "../types";
const outcomes: Record<Outcome, [string, typeof Circle]> = {
  idle: ["Ready", Circle],
  running: ["Running", LoaderCircle],
  success: ["Complete", Check],
  "no-results": ["No results", Circle],
  failed: ["Failed", CircleAlert],
  cancelled: ["Cancelled", Pause],
};
export function Activity({
  state,
  settings,
  patch,
  stop,
  onError,
}: {
  state: Snapshot;
  settings: Settings;
  patch: (changes: Partial<Settings>) => Promise<void>;
  stop: () => void;
  onError: (error: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<ActivityPage>({ entries: [], total: 0 });
  const [copied, setCopied] = useState(false);
  const [height, setHeight] = useState(settings.activity_height);
  const revision = useRef("");
  const reportError = useRef(onError);
  const expanded = !settings.activity_collapsed;
  useEffect(
    () => setHeight(settings.activity_height),
    [settings.activity_height],
  );
  useEffect(() => {
    revision.current = `${state.log_count}:${state.error_count}`;
    reportError.current = onError;
  }, [state.log_count, state.error_count, onError]);
  useEffect(() => {
    const timer = setTimeout(() => setFilter(query), 80);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    if (!expanded) return;
    let active = true;
    let fetchedRevision: string | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      const currentRevision = revision.current;
      if (currentRevision !== fetchedRevision) {
        try {
          const next = await desktopInvoke<ActivityPage>("get_activity", {
            query: filter,
            offset,
            limit: 100,
          });
          if (active) setRows(next);
        } catch (error) {
          if (active) reportError.current(errorMessage(error));
        }
        fetchedRevision = currentRevision;
      }
      // Worker snapshots never restart this clock. Slow requests finish before
      // scheduling the next fetch, and revisions received in flight stay pending.
      if (active) timer = setTimeout(() => void refresh(), 150);
    };
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [expanded, filter, offset]);
  const [label, Icon] = outcomes[state.job.outcome];
  const message = state.job.outcome === "idle" ? "" : state.job.message;
  const progress =
    state.job.total && state.job.total > 0
      ? Math.min(
          100,
          Math.max(0, ((state.job.done || 0) / state.job.total) * 100),
        )
      : null;
  const copy = async () => {
    try {
      await desktopInvoke("copy_errors");
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      onError(errorMessage(error));
    }
  };
  const resize = (event: React.PointerEvent<HTMLDivElement>) => {
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const start = event.clientY;
    const initial = handle.parentElement!.getBoundingClientRect().height;
    handle.onpointermove = (event) =>
      setHeight(
        Math.max(
          160,
          Math.min(window.innerHeight * 0.38, initial + start - event.clientY),
        ),
      );
    handle.onpointerup = () => {
      handle.onpointermove = null;
      handle.onpointerup = null;
      void patch({
        activity_height: handle.parentElement!.getBoundingClientRect().height,
      }).catch(() => {});
    };
  };
  return (
    <section
      className={`activity ${expanded ? "expanded" : ""}`}
      aria-label="Activity"
      style={
        expanded
          ? ({ "--activity-height": height + "px" } as React.CSSProperties)
          : undefined
      }
    >
      {expanded && (
        <div
          className="activity-resize"
          role="separator"
          aria-label="Resize Activity"
          aria-orientation="horizontal"
          tabIndex={0}
          onPointerDown={resize}
          onKeyDown={(event) => {
            if (["ArrowUp", "ArrowDown"].includes(event.key)) {
              event.preventDefault();
              void patch({
                activity_height: Math.max(
                  160,
                  Math.min(
                    window.innerHeight * 0.38,
                    height + (event.key === "ArrowUp" ? 24 : -24),
                  ),
                ),
              }).catch(() => {});
            }
          }}
        />
      )}
      <div className="activity-header">
        <Button
          data-layout-critical
          variant="quiet"
          className="activity-toggle"
          aria-label={expanded ? "Hide Activity" : "Show Activity"}
          aria-expanded={expanded}
          onClick={() =>
            void patch({ activity_collapsed: expanded }).catch(() => {})
          }
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
          Activity<span className="event-count">{state.log_count}</span>
        </Button>
        <div
          className={`job-status ${state.job.outcome}`}
          role="status"
          aria-live="polite"
        >
          <Icon
            size={17}
            className={state.job.outcome === "running" ? "spinner" : ""}
          />
          <strong>{label}</strong>
          <span className="job-message" title={message}>
            {message}
          </span>
        </div>
        {state.busy && (
          <Button
            data-layout-critical
            variant="danger"
            disabled={state.job.stop_requested}
            onClick={stop}
          >
            Stop job
          </Button>
        )}
      </div>
      {expanded && (
        <div className="activity-body">
          {progress !== null && (
            <div className="job-progress">
              <progress value={progress} max={100} aria-label="Job progress" />
              <span>
                {state.job.done} / {state.job.total}
              </span>
            </div>
          )}
          <div className="activity-toolbar">
            <div className="activity-search">
              <Search size={16} />
              <input
                aria-label="Filter activity"
                placeholder="Filter activity"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setOffset(0);
                }}
              />
            </div>
            <span className="error-count">{state.error_count} errors</span>
            <Button
              className="compact-button"
              disabled={!state.error_count}
              onClick={() => void copy()}
            >
              {copied ? "Copied" : "Copy errors"}
            </Button>
            <Button
              className="compact-button"
              disabled={!state.log_count}
              onClick={() => {
                setOffset(0);
                void desktopInvoke("clear_activity").catch((error) =>
                  onError(errorMessage(error)),
                );
              }}
            >
              Clear activity
            </Button>
          </div>
          <div className="activity-events" role="log" aria-live="off">
            {Object.keys(state.job.per_magazine).length > 0 && (
              <div className="publication-progress">
                {Object.entries(state.job.per_magazine).map(([name, p]) => (
                  <span key={name}>
                    {name}: {p.done} / {p.total}
                  </span>
                ))}
              </div>
            )}
            {state.log_count === 0 ? (
              <p className="muted">No activity yet.</p>
            ) : rows.total === 0 ? (
              <p className="muted">No activity matches this filter.</p>
            ) : (
              rows.entries.map((entry, index) => (
                <div className={`log-row ${entry.level}`} key={offset + index}>
                  <span className="log-level">
                    {entry.level === "debug"
                      ? "Detail"
                      : entry.level[0].toUpperCase() + entry.level.slice(1)}
                  </span>
                  <span>{entry.message}</span>
                </div>
              ))
            )}
          </div>
          {rows.total > 100 && state.log_count > 0 && (
            <div className="activity-pagination">
              <span>
                {offset + 1}–{Math.min(offset + 100, rows.total)} of{" "}
                {rows.total}
              </span>
              <Button
                className="compact-button"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Newer
              </Button>
              <Button
                className="compact-button"
                disabled={offset + 100 >= rows.total}
                onClick={() => setOffset(offset + 100)}
              >
                Older
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
