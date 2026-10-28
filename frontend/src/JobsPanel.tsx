import type { Job } from "./api";
import { STATUSES } from "./api";

export interface Filters { q: string; remote: "" | "true" | "false"; status: string }

interface Props {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  filters: Filters;
  onFilters: (f: Filters) => void;
  onRefresh: () => void;
  onScoreBatch: () => void;
  busy: string | null;
}

export function scoreClass(score: number) {
  return score >= 80 ? "good" : score >= 60 ? "ok" : "low";
}

function age(iso: string) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "1 day ago" : `${days} days ago`;
}

export function JobsPanel({ jobs, selectedId, onSelect, filters, onFilters, onRefresh, onScoreBatch, busy }: Props) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Jobs <span className="muted">({jobs.length})</span></h2>
        <div className="row">
          <button className="ghost" onClick={onScoreBatch} disabled={!!busy}
            title="Ask Claude to score up to 10 unscored jobs">
            {busy === "score" ? "Scoring…" : "Score 10"}
          </button>
          <button onClick={onRefresh} disabled={!!busy}>
            {busy === "refresh" ? "Fetching…" : "Fetch jobs"}
          </button>
        </div>
      </header>

      <div className="filters">
        <input type="search" placeholder="Search title, company, description"
          value={filters.q} onChange={(e) => onFilters({ ...filters, q: e.target.value })} />
        <select value={filters.remote} onChange={(e) => onFilters({ ...filters, remote: e.target.value as Filters["remote"] })}>
          <option value="">Any location</option>
          <option value="true">Remote</option>
          <option value="false">On-site / hybrid</option>
        </select>
        <select value={filters.status} onChange={(e) => onFilters({ ...filters, status: e.target.value })}>
          <option value="">All (not hidden)</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {jobs.length === 0 ? (
        <p className="muted empty">No jobs yet. Click <strong>Fetch jobs</strong> to pull from your sources.</p>
      ) : (
        <ul className="job-list">
          {jobs.map((job) => (
            <li key={job.id}>
              <button className={"job" + (job.id === selectedId ? " selected" : "")} onClick={() => onSelect(job.id)}>
                <div className="job-main">
                  <span className="job-title">{job.title}</span>
                  <span className="muted small">
                    {job.company} · {job.remote ? "Remote" : job.location || "—"}
                    {job.posted_at && ` · ${age(job.posted_at)}`}
                  </span>
                  <span className="tags">
                    {job.status !== "new" && <span className="tag">{job.status}</span>}
                    {[...new Set(job.sources.map((s) => s.source))].map((s) => <span key={s} className="tag subtle">{s}</span>)}
                  </span>
                </div>
                {job.score
                  ? <span className={"score " + scoreClass(job.score.score)}>{job.score.score}</span>
                  : <span className="score none">–</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
