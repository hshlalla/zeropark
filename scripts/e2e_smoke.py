# -*- coding: utf-8 -*-
"""Live E2E smoke test against a running gateway (default http://localhost:8080).

Exercises every path the web UI uses, plus jobs/stream/workflow/rag.
Run:  python scripts/e2e_smoke.py
"""
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail else ""))


client = httpx.Client(base_url=BASE, timeout=180.0)

# 1. health / modes / profile / catalog (no auth)
r = client.get("/health")
check("GET /health", r.status_code == 200 and r.json()["status"] == "ok")
engines = [p["id"] for p in r.json()["providers"]]

r = client.get("/modes")
check("GET /modes", r.status_code == 200 and "slides" in r.json()["modes"], str(list(r.json().get("modes", {}).keys())))
modes = list(r.json()["modes"].keys())

r = client.get("/api/v1/profile")
check("GET /api/v1/profile", r.status_code == 200 and "branding" in r.json())

r = client.get("/api/v1/usage")
check("GET /api/v1/usage", r.status_code == 200 and "tasks_total" in r.json())

# 2. auth: guest login (admin + user)
r = client.post("/api/v1/auth/guest/login?role=admin")
ok = r.status_code == 200 and "access_token" in r.json()
check("POST /api/v1/auth/guest/login (admin)", ok, "" if ok else r.text[:200])
admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"} if ok else {}

r = client.post("/api/v1/auth/guest/login?role=user")
user_headers = {"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code == 200 else {}
check("POST /api/v1/auth/guest/login (user)", r.status_code == 200)

# 3. admin stats (Dashboard.tsx)
r = client.get("/api/v1/admin/stats", headers=admin_headers)
check("GET /api/v1/admin/stats (admin)", r.status_code == 200, "" if r.status_code == 200 else r.text[:200])

r = client.get("/api/v1/admin/users", headers=admin_headers)
check("GET /api/v1/admin/users (admin)", r.status_code == 200, "" if r.status_code == 200 else r.text[:200])

# RBAC: user must NOT access admin
r = client.get("/api/v1/admin/stats", headers=user_headers)
check("RBAC: user blocked from admin stats", r.status_code == 403, f"got {r.status_code}")

# 4. tasks per mode (AppViewer.tsx posts {prompt, mode, params})
def run_task(mode: str, prompt: str, params: dict | None = None) -> httpx.Response:
    return client.post(
        "/api/v1/tasks",
        headers=user_headers,
        json={"prompt": prompt, "mode": mode, "params": params or {}},
    )

# slides (no LLM needed when outline given)
r = run_task("slides", "Company overview", {"title": "Overview", "outline": [{"title": "Intro", "bullets": ["hi"]}]})
check("POST /api/v1/tasks mode=slides", r.status_code == 200 and r.json()["status"] == "succeeded", "" if r.status_code == 200 else r.text[:300])

# chat (the default conversation surface)
r = run_task("chat", "Reply with exactly: PONG")
ok = r.status_code == 200 and r.json().get("status") == "succeeded"
detail = (r.json()["artifacts"][0].get("inline") or "")[:60] if ok else r.text[:300]
check("POST /api/v1/tasks mode=chat (LLM)", ok, detail)

# chat with history (multi-turn)
r = client.post(
    "/api/v1/tasks", headers=user_headers,
    json={"prompt": "What number did I just tell you?", "mode": "chat",
          "params": {"history": [
              {"role": "user", "content": "Remember the number 42."},
              {"role": "assistant", "content": "Got it, 42."}]}},
)
ok = r.status_code == 200 and "42" in (r.json()["artifacts"][0].get("inline") or "")
check("chat multi-turn history", ok, "" if ok else r.text[:200])

# super_agent (real LLM loop)
r = run_task("super_agent", "What is 17*23? Use python if available, then answer briefly.")
ok = r.status_code == 200 and r.json().get("status") == "succeeded"
detail = ""
if ok:
    inline = (r.json()["artifacts"][0].get("inline") or "")[:80]
    detail = f"answer: {inline!r}"
else:
    detail = r.text[:300]
check("POST /api/v1/tasks mode=super_agent (LLM)", ok, detail)

# every advertised mode at least routes (200/503 acceptable, 500 not)
for mode in modes:
    rr = client.post("/route", json={"prompt": "x", "mode": mode})
    check(f"POST /route mode={mode}", rr.status_code == 200, "" if rr.status_code == 200 else rr.text[:150])

# 5. SSE stream (slides)
with client.stream(
    "POST", "/api/v1/tasks/stream", headers=user_headers,
    json={"prompt": "Deck", "mode": "slides", "params": {"title": "T", "outline": [{"title": "A", "bullets": ["x"]}]}},
) as r:
    body = "".join(chunk for chunk in r.iter_text())
ok = r.status_code == 200 and '"done"' in body and '"artifact"' in body
check("POST /api/v1/tasks/stream (SSE)", ok, "" if ok else body[:200])

# 6. workflow run (input -> llm) + run log
wf = {
    "nodes": [
        {"id": "n1", "data": {"type": "input", "topic": "Mars"}},
        {"id": "n2", "data": {"type": "llm", "prompt": "One short fact about {{topic}}."}},
    ],
    "edges": [{"source": "n1", "target": "n2"}],
    "initial_inputs": {},
}
r = client.post("/api/v1/workflow/run", json=wf)
ok = r.status_code == 200 and r.json().get("status") == "success"
check("POST /api/v1/workflow/run (input->llm)", ok, "" if ok else r.text[:300])
if ok:
    run_id = r.json()["run_id"]
    r2 = client.get(f"/api/v1/workflow/runs/{run_id}")
    check("GET /api/v1/workflow/runs/{id}", r2.status_code == 200 and len(r2.json()["node_runs"]) == 2, "" if r2.status_code == 200 else r2.text[:200])

# 7. RAG upload + query (embeddings + LLM)
files = [("files", ("note.txt", b"Zeropark was founded to build native AI workspaces. The capital of France is Paris.", "text/plain"))]
r = client.post("/api/v1/rag/upload", headers=user_headers, files=files)
check("POST /api/v1/rag/upload", r.status_code == 200, "" if r.status_code == 200 else r.text[:300])

r = client.post("/api/v1/rag/query", headers=user_headers, json={"query": "What is the capital of France?"})
ok = r.status_code == 200 and r.json().get("status") == "succeeded"
check("POST /api/v1/rag/query", ok, "" if ok else r.text[:300])

# 8. background job (slides) + poll + events
r = client.post("/api/v1/jobs", headers=user_headers, json={"mode": "slides", "prompt": "Deck", "params": {"title": "J", "outline": [{"title": "A", "bullets": ["x"]}]}})
ok = r.status_code == 200 and "job_id" in r.json()
check("POST /api/v1/jobs", ok, "" if ok else r.text[:300])
if ok:
    job_id = r.json()["job_id"]
    import time
    status = None
    for _ in range(20):
        time.sleep(0.5)
        jr = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers)
        status = jr.json().get("status")
        if status in ("succeeded", "failed"):
            break
    check("GET /api/v1/jobs/{id} reaches terminal state", status == "succeeded", f"status={status}")

# 9. crawl with SSRF guard
r = client.post("/crawl", json={"url": "http://169.254.169.254/latest/meta-data/"})
check("SSRF guard blocks metadata IP", r.status_code == 400, f"got {r.status_code}")

r = client.post("/crawl", json={"url": "https://example.com"})
check("POST /crawl public URL", r.status_code == 200, "" if r.status_code == 200 else r.text[:200])

# 10. usage incremented
r = client.get("/api/v1/usage")
check("usage counters incremented", r.json().get("tasks_total", 0) >= 3, json.dumps(r.json()))

print()
fails = [n for n, ok, _ in results if not ok]
print(f"==== {len(results) - len(fails)}/{len(results)} passed ====")
if fails:
    print("FAILED:", *fails, sep="\n  - ")
    sys.exit(1)
