import { useEffect, useState } from "react";
import type { Job, Resume, Tailored } from "./api";
import { STATUSES } from "./api";
import { scoreClass } from "./JobsPanel";

interface Props {
  job: Job | null;
  resume: Resume | null;
  busy: string | null;
  onScore: () => void;
  onTailor: () => void;
  onStatus: (status: string) => void;
  onExport: (accepted: number[], useOrder: boolean) => void;
  onHover: (target: string | null) => void;
}

function targetLabel(target: string, resume: Resume | null) {
  if (target === "profile") return "Profile";
  if (target.startsWith("skills:")) return `Skills · ${target.slice(7)}`;
  for (const role of resume?.experience ?? []) {
    const i = role.bullets.findIndex((b) => b.id === target);
    if (i >= 0) return `${role.company} ${role.start} · ${role.bullets[i].label || `bullet ${i + 1}`}`;
  }
  return target;
}

export function TailorPanel({ job, resume, busy, onScore, onTailor, onStatus, onExport, onHover }: Props) {
  const tailored: Tailored | null | undefined = job?.tailored;
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [useOrder, setUseOrder] = useState(true);
  const [showDesc, setShowDesc] = useState(false);

  // New suggestions: pre-accept the ones without warnings; flagged ones need a deliberate click.
  useEffect(() => {
    setAccepted(new Set(tailored?.edits.flatMap((e, i) => (e.warnings.length ? [] : [i])) ?? []));
  }, [tailored]);

  if (!job) {
    return (
      <section className="panel">
        <header className="panel-head"><h2>Tailored resume</h2></header>
        <p className="muted empty">Pick a job to see how well you match and get suggested resume edits.</p>
      </section>
    );
  }

  const toggle = (i: number) => {
    const next = new Set(accepted);
    next.has(i) ? next.delete(i) : next.add(i);
    setAccepted(next);
  };

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2 className="job-heading">{job.title}</h2>
          <p className="muted small">
            {job.company} · {job.remote ? "Remote" : job.location}{job.salary && ` · ${job.salary}`}
          </p>
        </div>
        <select value={job.status} onChange={(e) => onStatus(e.target.value)} aria-label="Status">
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </header>

      <div className="links">
        {[...new Map(job.sources.map((s) => [s.url, s])).values()].map((s) => (
          <a key={s.url} href={s.url} target="_blank" rel="noreferrer">
            Open on {s.source} ↗
          </a>
        ))}
        <button className="link" onClick={() => setShowDesc(!showDesc)}>
          {showDesc ? "Hide description" : "Show description"}
        </button>
      </div>
      {showDesc && <pre className="description">{job.description || "No description provided."}</pre>}

      <div className="card">
        {job.score ? (
          <>
            <div className="row">
              <span className={"score big " + scoreClass(job.score.score)}>{job.score.score}</span>
              <p>{job.score.summary}</p>
            </div>
            <div className="two-col">
              <div><h4>Strengths</h4><ul>{job.score.strengths.map((s) => <li key={s}>{s}</li>)}</ul></div>
              <div><h4>Gaps</h4><ul>{job.score.gaps.map((s) => <li key={s}>{s}</li>)}</ul></div>
            </div>
          </>
        ) : (
          <div className="row">
            <p className="muted">Not scored yet.</p>
            <button className="ghost" onClick={onScore} disabled={!!busy}>
              {busy === "score-one" ? "Scoring…" : "Score match"}
            </button>
          </div>
        )}
      </div>

      <div className="row spread">
        <h3>Suggested edits</h3>
        <button onClick={onTailor} disabled={!!busy}>
          {busy === "tailor" ? "Tailoring… (can take a minute)" : tailored ? "Re-run" : "Tailor my resume"}
        </button>
      </div>

      {!tailored ? (
        <p className="muted">Claude suggests rewrites, removals and a better bullet order using only what is
          already on your resume. You approve each change before exporting.</p>
      ) : (
        <>
          {tailored.keywords.length > 0 && (
            <p className="tags">{tailored.keywords.map((k) => <span key={k} className="tag">{k}</span>)}</p>
          )}
          <ul className="edits">
            {tailored.edits.map((e, i) => (
              <li key={i} className={"edit" + (accepted.has(i) ? " on" : "")}
                onMouseEnter={() => onHover(e.target)} onMouseLeave={() => onHover(null)}>
                <label className="edit-head">
                  <input type="checkbox" checked={accepted.has(i)} onChange={() => toggle(i)} />
                  <strong>{targetLabel(e.target, resume)}</strong>
                  <span className="tag subtle">{e.action}</span>
                </label>
                <p className="reason">{e.reason}</p>
                <p className="diff-old">{e.original}</p>
                {e.action === "rewrite" && <p className="diff-new">{e.proposed}</p>}
                {e.warnings.map((w) => <p key={w} className="warning">⚠ Check this: {w}</p>)}
              </li>
            ))}
          </ul>
          {tailored.bullet_order.length > 0 && (
            <label className="row small">
              <input type="checkbox" checked={useOrder} onChange={(e) => setUseOrder(e.target.checked)} />
              Reorder bullets by relevance ({tailored.bullet_order.length} role{tailored.bullet_order.length > 1 ? "s" : ""})
            </label>
          )}
          {tailored.rejected.length > 0 && (
            <details className="small">
              <summary>{tailored.rejected.length} suggestion(s) blocked by the safety checks</summary>
              <ul>{tailored.rejected.map((r, i) => <li key={i}><strong>{r.target}</strong>: {r.why}</li>)}</ul>
            </details>
          )}
          <div className="row spread sticky-actions">
            <span className="muted small">{accepted.size} of {tailored.edits.length} edits accepted</span>
            <button onClick={() => onExport([...accepted].sort((a, b) => a - b), useOrder)} disabled={!!busy}>
              Export .docx
            </button>
          </div>
        </>
      )}
    </section>
  );
}
