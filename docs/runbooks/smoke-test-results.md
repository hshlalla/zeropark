# OSS Smoke Test Results

Use this file during Phase 1 to record exact commands, versions, ports, outputs, screenshots, and blockers.

Generated: 2026-06-08

## Environment

- OS: Windows / PowerShell, Git Bash available at `C:\Program Files\Git\bin\bash.exe`
- Docker version: not available; `docker` command is not in PATH
- Python version: system Python `3.11.9`; uv-managed Python `3.12.13` installed during DeerFlow check
- Node version: `v24.14.0`; npm `11.9.0`
- uv version: `0.10.11`
- Missing command-line tools in PowerShell PATH: `docker`, `make`, `nginx`, `pnpm`
- Model provider(s): none configured

## Results

| Service | Version/commit | Command | URL/port | Result | Notes |
| --- | --- | --- | --- | --- | --- |
| Zeropark Gateway | local scaffold | `python -m uvicorn zeropark_gateway.main:app --host 127.0.0.1 --port 18080` | `http://127.0.0.1:18080` | PASS | `/health=ok`, `/services=9`, `/route` for slides returned `presenton,deer-flow` |
| DeerFlow | `1651d1f1f57b8c43148ab8433bef0d4caf0d13e9` | `uv run --project external/deer-flow/backend --python 3.12 python external/deer-flow/scripts/doctor.py` | planned `http://localhost:2026` | PARTIAL | Backend deps installed under uv-managed Python `3.12.13`; doctor ran. Runtime blocked by missing `nginx`, missing `.env`, missing `frontend/.env`, missing `config.yaml`, and no model config. |
| Dify | `0239b81cca52575585739b660234d6d7d05accde` | `cd external/dify/docker; docker compose up -d` | planned `http://localhost/install` | BLOCKED | Official self-host quick start requires Docker Compose; `docker` is not installed. Source mode also requires Python `~=3.12.0` and pnpm-based web setup. |
| Presenton | `8e1581378740208899c689e1c799fce11e455a8c` | `uv run --project external/presenton/servers/fastapi --python 3.11 ...` | planned `http://localhost:5000` | PARTIAL | FastAPI deps installed; app imported with Windows-safe `APP_DATA_DIRECTORY`; `TestClient('/openapi.json')` returned `200`; `/api/v1/ppt/presentation/generate` route exists. Full PPTX generation blocked until Docker/Electron runtime and LLM config are set. |
| Crawl4AI | `cdf2ead7ed4b78594d06b87bae930a819c685825` | `uv run --project external/crawl4ai --python 3.11 crawl4ai-doctor`; example crawl script | local browser | PASS | Installed with `UV_LINK_MODE=copy` and Python `3.11`; installed Playwright Chromium; doctor passed; `https://example.com` crawled successfully to markdown. |
| Browser-use | `6701a44a58353d5981f3dde6d9da563e8b27858b` | `browser-use --session zeropark-smoke open https://example.com`; `browser-use state`; `browser-use close` | local browser | PASS | Import passed; CLI help passed; doctor passed 3/5. Local browser automation opened `https://example.com`, read state/title/elements, and closed. Missing optional `cloudflared`, `profile-use`, and cloud API key. |
| SearXNG | `f3fab143be3069bbcdcec9169bcf6ee030437a61` | `.\scripts\fetch-oss.ps1 -Repos searxng`; planned Docker run | planned `http://localhost:8888` | BLOCKED | Docker is unavailable. Direct Windows checkout also fails because upstream includes colon-suffixed socket template paths such as `searxng.conf:socket`; partial checkout was removed. Use Docker/WSL/Linux for SearXNG. |

## Blocking Issues

- Docker Desktop or Docker Engine is not installed or not in PATH. This blocks Dify, SearXNG container mode, and the recommended Presenton Docker path.
- DeerFlow local runtime still needs `nginx`, `.env`, `frontend/.env`, `config.yaml`, and at least one model provider.
- Dify web/source setup expects pnpm; `pnpm` is not currently in PowerShell PATH.
- SearXNG cannot be checked out normally on Windows due upstream filenames containing `:`. Use Docker, WSL, or Linux.
- Presenton full deck generation needs a configured LLM provider and either Docker or Electron/Next.js runtime setup.

## Follow-Up Fixes

- Install Docker Desktop, then rerun Dify and SearXNG smoke tests.
- Enable pnpm through Corepack or install pnpm explicitly before Dify source-mode work.
- For DeerFlow, run setup in a supported shell/runtime after installing nginx or use Docker mode. Minimum follow-up: create `.env`, `frontend/.env`, and `config.yaml` with a real model provider.
- For Presenton, choose Docker or Electron path, configure an LLM provider, then call `/api/v1/ppt/presentation/generate` and verify a PPTX file.
- Keep `UV_LINK_MODE=copy` for this workspace on Windows to avoid hardlink issues in cloud-synced directories.
- Keep `PYTHONIOENCODING=utf-8` for upstream CLIs on Windows to avoid cp949 Unicode output failures.
