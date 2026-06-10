// Zeropark API client — drop into your Vite/React/TS frontend (e.g. src/lib/zeropark.ts).
// Framework-agnostic: no React/Vue imports. Uses fetch + the streaming body reader,
// so the SSE endpoint works over POST with an Authorization header (EventSource can't).
//
// Configure the gateway URL via Vite env: VITE_ZEROPARK_API=http://localhost:8080

const BASE: string =
  (import.meta as any).env?.VITE_ZEROPARK_API ?? "http://localhost:8080";

// ---- Types (mirror zeropark_core.models) ----------------------------------

export type ArtifactKind =
  | "report" | "deck" | "sheet" | "page" | "file" | "data" | "message" | "image" | "audio";

export interface Artifact {
  id: string;
  kind: ArtifactKind;
  title?: string | null;
  mime_type?: string | null;
  uri?: string | null;
  inline?: unknown;
  metadata?: Record<string, unknown>;
}

export interface SourceRef {
  url?: string | null;
  title?: string | null;
  snippet?: string | null;
  score?: number | null;
  provider_id?: string | null;
}

export interface TaskResult {
  task_id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  capability: string;
  provider_id: string;
  artifacts: Artifact[];
  sources: SourceRef[];
  metrics: Record<string, unknown>;
  error?: string | null;
  mode?: string;
  initiated_by?: string;
}

export interface RunEvent {
  type: "status" | "log" | "source" | "artifact" | "error" | "token" | "done";
  task_id: string;
  provider_id?: string | null;
  at?: string;
  message?: string | null;
  data?: Record<string, any>;
}

export interface ModePlan {
  primary: string;
  pipeline: string[];
  description: string;
}

export interface RunOptions {
  mode: string;
  prompt: string;
  params?: Record<string, unknown>;
  providerId?: string;
  token?: string;
}

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---- Auth ------------------------------------------------------------------

export async function login(
  username: string,
  password: string,
): Promise<{ access_token: string; token_type: string }> {
  const body = new URLSearchParams({ username, password });
  const r = await fetch(`${BASE}/api/v1/auth/login`, { method: "POST", body });
  if (!r.ok) throw new Error("Login failed");
  return r.json();
}

/** Dev/login bypass: returns a JWT for the given role without a password. */
export async function guestLogin(role = "admin"): Promise<{ access_token: string; user: any }> {
  const r = await fetch(`${BASE}/api/v1/auth/guest/login?role=${role}`, { method: "POST" });
  if (!r.ok) throw new Error("Guest login failed");
  return r.json();
}

export function googleLoginUrl(): string {
  return `${BASE}/api/v1/auth/google/login`;
}

// ---- Introspection (public, no token) --------------------------------------

export async function getModes(): Promise<Record<string, ModePlan>> {
  const r = await fetch(`${BASE}/modes`);
  return (await r.json()).modes;
}

export async function getProviders(): Promise<Array<{ id: string; name: string; capabilities: string[] }>> {
  const r = await fetch(`${BASE}/providers`);
  return (await r.json()).providers;
}

export async function getHealth(): Promise<any> {
  return (await fetch(`${BASE}/health`)).json();
}

// ---- Execution -------------------------------------------------------------

/** Run a task synchronously and return the final result. */
export async function runTask(opts: RunOptions): Promise<TaskResult> {
  const r = await fetch(`${BASE}/api/v1/tasks`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(opts.token) },
    body: JSON.stringify({
      mode: opts.mode,
      prompt: opts.prompt,
      params: opts.params ?? {},
      provider_id: opts.providerId,
    }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Task failed (${r.status})`);
  }
  return r.json();
}

/**
 * Run a task and stream RunEvents (Server-Sent Events). `onEvent` fires for each
 * event (status -> [engine events] -> artifact(s) -> done). Returns the final
 * TaskResult parsed from the `done` event.
 */
export async function streamTask(
  opts: RunOptions,
  onEvent: (e: RunEvent) => void,
  signal?: AbortSignal,
): Promise<TaskResult | null> {
  const r = await fetch(`${BASE}/api/v1/tasks/stream`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(opts.token) },
    body: JSON.stringify({
      mode: opts.mode,
      prompt: opts.prompt,
      params: opts.params ?? {},
      provider_id: opts.providerId,
    }),
    signal,
  });
  if (!r.ok || !r.body) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Stream failed (${r.status})`);
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: TaskResult | null = null;

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.replace(/^data:\s?/, "").trim();
      if (!line) continue;
      const event = JSON.parse(line) as RunEvent;
      onEvent(event);
      if (event.type === "done" && event.data?.result) {
        final = event.data.result as TaskResult;
      }
    }
  }
  return final;
}
