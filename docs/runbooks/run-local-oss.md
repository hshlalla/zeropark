# Local OSS Runbook

This runbook is for proving the OSS foundation before building more product code.

## 1. Fetch Sources

```powershell
.\scripts\fetch-oss.ps1 -Core
```

Core repos are cloned into `external/`:

- `external/deer-flow`
- `external/dify`
- `external/presenton`
- `external/crawl4ai`
- `external/browser-use`

Optional repos:

```powershell
.\scripts\fetch-oss.ps1 -Repos openmanus,searxng,coze-studio,ui-tars-desktop
```

## 2. Run Zeropark Gateway

```powershell
python -m pip install -e services/gateway
uvicorn zeropark_gateway.main:app --host 0.0.0.0 --port 8080
```

Check:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/services
```

## 3. Run SearXNG Quickly

```powershell
Copy-Item .env.example .env
docker compose --profile search up -d searxng
```

Set:

```powershell
$env:SEARXNG_URL = "http://localhost:8888"
```

Test through gateway:

```powershell
Invoke-RestMethod http://localhost:8080/search `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"latest open source AI agent frameworks","limit":5}'
```

## 4. Smoke-Test External Systems

Use each upstream README for exact setup commands after cloning. Record exact commands and results in `docs/runbooks/smoke-test-results.md`.

| Service | Expected local URL | Smoke test |
| --- | --- | --- |
| DeerFlow | `http://localhost:2026` or upstream default | Run one research task and save the result |
| Dify | Upstream Docker Compose default | Create/import one workflow and call it by API |
| Presenton | `http://localhost:5000` or upstream default | Generate one 5-slide PPTX |
| Crawl4AI | Upstream Docker/API default | Crawl one URL to markdown |
| Browser-use | Local Python run | Open a page, extract title, close browser |
| SearXNG | `http://localhost:8888` | Return JSON search results |

## 5. Gateway Environment Mapping

Use `.env` to point the gateway at running services:

```dotenv
SEARXNG_URL=http://localhost:8888
PRESENTON_URL=http://localhost:5000
PRESENTON_USERNAME=admin
PRESENTON_PASSWORD=change-me
DEERFLOW_URL=http://localhost:2026
DEERFLOW_TASK_PATH=
DIFY_URL=http://localhost
DIFY_API_KEY=
CRAWL4AI_URL=http://localhost:11235
CRAWL4AI_CRAWL_PATH=
BROWSER_USE_URL=
```

Blank `*_PATH` values mean "do not proxy yet"; the gateway will return route guidance instead of guessing upstream endpoints.

