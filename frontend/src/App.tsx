import { useCallback, useEffect, useState } from "react";
import { api, type Health, type Job, type Resume } from "./api";
import { JobsPanel, type Filters } from "./JobsPanel";
import { ResumePanel } from "./ResumePanel";
import { TailorPanel } from "./TailorPanel";

type Tab = "resume" | "jobs" | "tailor";

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [resume, setResume] = useState<Resume | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [filters, setFilters] = useState<Filters>({ q: "", remote: "", status: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("jobs");

  // Run an action with a busy flag and turn failures into a visible message.
  const run = useCallback(async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true });
    } finally {
      setBusy(null);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    setJobs(await api.jobs({
      q: filters.q || undefined,
      remote: filters.remote === "" ? undefined : filters.remote === "true",
      status: filters.status || undefined,
    }));
  }, [filters]);

  const loadJob = async (id: string) => setJob(await api.job(id));

  useEffect(() => {
    api.health().then(setHealth).catch(() => setMessage({ text: "Backend not reachable on :8000", error: true }));
    api.resume().then(setResume).catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(() => loadJobs().catch(() => {}), 250); // debounce the search box
    return () => clearTimeout(t);
  }, [loadJobs]);

  const select = (id: string) => run("load", async () => { await loadJob(id); setTab("tailor"); });

  return (
    <div className="app">
      <header className="topbar">
        <h1>Job Hunter</h1>
        {health && !health.ai_configured && (
          <span className="pill warn">No ANTHROPIC_API_KEY: AI features are off</span>
        )}
        {health?.ai_configured && <span className="pill">AI: {health.model}</span>}
        {message && (
          <span className={"pill " + (message.error ? "error" : "")} role="status">
            {message.text}
            <button className="link" onClick={() => setMessage(null)} aria-label="Dismiss">×</button>
          </span>
        )}
      </header>

      <nav className="tabs" aria-label="Panels">
        {(["resume", "jobs", "tailor"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t === "resume" ? "Resume" : t === "jobs" ? "Jobs" : "Tailor"}
          </button>
        ))}
      </nav>

      <main className={"columns show-" + tab}>
        <ResumePanel
          resume={resume}
          isExample={!!health && !health.resume_loaded}
          highlight={highlight}
          importing={busy === "import"}
          onImport={(file) => run("import", async () => {
            setResume(await api.importResume(file));
            setHealth(await api.health());
            setMessage({ text: "Resume imported. Check it over: scores and edits are now based on it." });
            await loadJobs();
          })}
        />
        <JobsPanel
          jobs={jobs}
          selectedId={job?.id ?? null}
          onSelect={select}
          filters={filters}
          onFilters={setFilters}
          busy={busy}
          onRefresh={() => run("refresh", async () => {
            const r = (await api.refresh()) as { new: number; unique: number; sources: Record<string, { error?: string }> };
            const failed = Object.entries(r.sources).filter(([, v]) => v.error).map(([k]) => k);
            setMessage({
              text: `${r.new} new job(s), ${r.unique} total in this fetch` +
                (failed.length ? `. Failed sources: ${failed.join(", ")}` : ""),
              error: failed.length > 0,
            });
            await loadJobs();
          })}
          onScoreBatch={() => run("score", async () => {
            const r = await api.scoreBatch();
            if (r.errors.length) throw new Error(r.errors[0]);
            setMessage({ text: `Scored ${r.scored} job(s).` });
            await loadJobs();
          })}
        />
        <TailorPanel
          job={job}
          resume={resume}
          busy={busy}
          onHover={setHighlight}
          onScore={() => run("score-one", async () => {
            await api.score(job!.id);
            await Promise.all([loadJob(job!.id), loadJobs()]);
          })}
          onTailor={() => run("tailor", async () => {
            const tailored = await api.tailor(job!.id);
            setJob({ ...job!, tailored });
          })}
          onStatus={(status) => run("status", async () => {
            await api.setStatus(job!.id, status);
            setJob({ ...job!, status });
            await loadJobs();
          })}
          onExport={(accepted, useOrder) => run("export", () => api.exportDocx(job!.id, accepted, useOrder))}
        />
      </main>
    </div>
  );
}
