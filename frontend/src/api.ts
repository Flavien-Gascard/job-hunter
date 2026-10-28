// Typed wrappers around the backend REST API.

export interface Bullet { id: string; label: string; text: string }
export interface Role {
  id: string; title: string; company: string; location: string;
  start: string; end: string; bullets: Bullet[];
}
export interface Resume {
  name: string; contact: string[]; profile: string;
  skills: { name: string; items: string[] }[];
  experience: Role[]; certifications: string[]; education: string[];
}
export interface Score { score: number; summary: string; strengths: string[]; gaps: string[] }
export interface Job {
  id: string; title: string; company: string; location: string; remote: boolean;
  url: string; description: string; salary: string; posted_at: string; status: string;
  sources: { source: string; source_id: string; url: string }[];
  score: Score | null;
  tailored?: Tailored | null;
}
export interface TailorEdit {
  target: string; action: "rewrite" | "remove"; proposed: string;
  reason: string; original: string; warnings: string[];
}
export interface Tailored {
  edits: TailorEdit[];
  bullet_order: { role_id: string; bullet_ids: string[] }[];
  keywords: string[];
  rejected: (TailorEdit & { why: string })[];
}
export interface Health {
  ai_configured: boolean; model: string; resume_loaded: boolean; adzuna_configured: boolean;
}

export const STATUSES = ["new", "saved", "applied", "interview", "offer", "rejected", "hidden"];

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => call<Health>("/api/health"),
  resume: () => call<Resume>("/api/resume"),
  importResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<Resume>("/api/resume/import", { method: "POST", body: form });
  },
  jobs: (params: { q?: string; remote?: boolean; status?: string }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.remote !== undefined) qs.set("remote", String(params.remote));
    if (params.status) qs.set("status", params.status);
    return call<Job[]>(`/api/jobs?${qs}`);
  },
  job: (id: string) => call<Job>(`/api/jobs/${id}`),
  refresh: () => call<Record<string, unknown>>("/api/jobs/refresh", post()),
  scoreBatch: () => call<{ scored: number; errors: string[] }>("/api/jobs/score-batch", post()),
  score: (id: string) => call<Score>(`/api/jobs/${id}/score`, post()),
  tailor: (id: string) => call<Tailored>(`/api/jobs/${id}/tailor`, post()),
  setStatus: (id: string, status: string) =>
    call(`/api/jobs/${id}`, { ...post({ status }), method: "PATCH" }),
  exportDocx: async (id: string, accepted: number[], useOrder: boolean) => {
    const resp = await fetch(`/api/jobs/${id}/export`, post({ accepted, use_order: useOrder }));
    if (!resp.ok) throw new Error((await resp.json()).detail ?? "Export failed");
    const name = /filename="([^"]+)"/.exec(resp.headers.get("content-disposition") ?? "")?.[1];
    const url = URL.createObjectURL(await resp.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name ?? "resume.docx" });
    a.click();
    URL.revokeObjectURL(url);
  },
};
