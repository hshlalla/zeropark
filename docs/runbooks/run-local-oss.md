# Local Run Runbook (Native)

> 과거 이 문서는 외부 OSS 서비스(SearXNG, Presenton, Dify 등)를 직접 띄워 게이트웨이가
> 프록시하던 시절의 절차였다. **현재 모든 엔진은 네이티브 구현**이므로 외부 서비스를
> 띄울 필요가 없다. `external/`의 OSS 체크아웃은 설계 참고용일 뿐, 실행/임포트하지 않는다.

## 1. (선택) 참고용 OSS 소스 받기

```powershell
.\scripts\fetch-oss.ps1 -Core   # external/ 에 클론 — 코드 읽기 용도만
```

## 2. 환경 설정

```powershell
Copy-Item .env.example .env
```

`.env`의 핵심 항목:

```dotenv
# LLM (research/slides/agents 활성화 조건)
ZEROPARK_LLM__PROVIDER=openai        # 또는 anthropic
ZEROPARK_LLM__API_KEY=sk-...
ZEROPARK_LLM__MODEL=gpt-4o

# 검색 (search/research 활성화 조건) — commodity API, SearXNG 아님
ZEROPARK_SEARCH__BASE_URL=https://api.search.brave.com/res/v1/web/search
ZEROPARK_SEARCH__API_KEY=...

# 고객사 프로파일 (선택)
ZEROPARK_BRANDING__PRODUCT_NAME=Zeropark
ZEROPARK_FEATURES={}
```

## 3. 게이트웨이 실행

```powershell
python -m pip install -e packages/zeropark-core -e packages/zeropark-engines -e services/gateway
uvicorn zeropark_gateway.main:app --host 0.0.0.0 --port 8080
```

확인:

```powershell
Invoke-RestMethod http://localhost:8080/health         # 등록된 네이티브 엔진 목록
Invoke-RestMethod http://localhost:8080/api/v1/profile # 브랜딩 + 활성 capability
Invoke-RestMethod http://localhost:8080/api/v1/usage   # 사용량 카운터
```

설정 없이도 crawl/slides/sheets는 동작한다. LLM 키를 넣으면 super_agent/research/rag가,
검색 키까지 넣으면 deep-research가 추가 등록된다 (`/health`에서 확인).

## 4. 전체 스택 (Docker Compose)

```powershell
docker-compose up -d --build   # Web 80, API 8080, Qdrant 6333, Redis 6379
```

Docker가 있으면 python 노드/에이전트의 코드 실행이 자동으로 Docker 샌드박스를 쓴다.
Docker 없이 로컬 개발만 할 때는 `ZEROPARK_ALLOW_UNSAFE_SANDBOX=1`(프로덕션 금지).

## 5. Control Plane (자사 인프라 전용)

```powershell
python -m pip install -e services/control-plane
$env:ZEROPARK_CP_ADMIN_TOKEN = "dev-admin-token"
uvicorn zeropark_control.main:app --port 8090
# 브라우저: http://localhost:8090 → 배포 등록 후 발급된 license_key를
# 배포본 .env의 ZEROPARK_CONTROL_PLANE__* 에 설정하면 하트비트 시작
```

## 6. 스모크 테스트

```powershell
python -m pytest packages/zeropark-core packages/zeropark-engines services/gateway/tests services/control-plane/tests -q
```

수동 스모크 (슬라이드 — 설정 불필요):

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/tasks -Method Post -ContentType "application/json" `
  -Body '{"mode":"slides","prompt":"Company overview","params":{"title":"Overview","theme":"corporate","outline":[{"title":"Intro","bullets":["Hello"]}]}}'
```

결과는 `docs/runbooks/smoke-test-results.md`에 기록한다.
