import { useRef } from "react";
import type { Resume } from "./api";

interface Props {
  resume: Resume | null;
  isExample: boolean;
  highlight: string | null;
  onImport: (file: File) => void;
  importing: boolean;
}

export function ResumePanel({ resume, isExample, highlight, onImport, importing }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const mark = (id: string) => (highlight === id ? " highlight" : "");

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>My resume</h2>
        <button className="ghost" onClick={() => input.current?.click()} disabled={importing}>
          {importing ? "Importing…" : "Import .docx"}
        </button>
        <input ref={input} type="file" accept=".docx" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f); e.target.value = ""; }} />
      </header>
      {isExample && (
        <p className="notice">Showing a sample resume. Import your .docx to replace it.</p>
      )}
      {!resume ? <p className="muted">Loading…</p> : (
        <div className="resume">
          <h3 className="resume-name">{resume.name}</h3>
          <p className="muted small">{resume.contact.join(" · ")}</p>

          <h4>Profile</h4>
          <p className={"resume-text" + mark("profile")}>{resume.profile}</p>

          <h4>Skills</h4>
          {resume.skills.map((g) => (
            <p key={g.name} className={"small" + mark(`skills:${g.name}`)}>
              <strong>{g.name}:</strong> {g.items.join(" · ")}
            </p>
          ))}

          <h4>Experience</h4>
          {resume.experience.map((role) => (
            <div key={role.id} className="role">
              <p className="role-title">
                <strong>{role.title}</strong>
                <span className="muted"> · {role.company} · {role.start}–{role.end}</span>
              </p>
              <ul>
                {role.bullets.map((b) => (
                  <li key={b.id} className={mark(b.id).trim()}>
                    {b.label && <strong>{b.label}: </strong>}{b.text}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {resume.certifications.length > 0 && <>
            <h4>Certifications</h4>
            <ul>{resume.certifications.map((c) => <li key={c}>{c}</li>)}</ul>
          </>}
          {resume.education.length > 0 && <>
            <h4>Education</h4>
            <ul>{resume.education.map((c) => <li key={c}>{c}</li>)}</ul>
          </>}
        </div>
      )}
    </section>
  );
}
