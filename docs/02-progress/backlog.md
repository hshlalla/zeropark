---
doc_type: backlog
project_id: zeropark_v2
status: active
updated_at: 2026-06-16
---

# Zeropark 기능 백로그 (dify/deerflow 갭 + 운영 갭)

우선순위: P1(고객 체감/시연 직결) → P2(운영 품질) → P3(고도화).
각 항목은 "왜 → 설계 → 손댈 파일 → 완료 기준" 순서로 기술한다.

> **진행 현황 (2026-06-12):** P1·P2·P3 항목 전부 구현 완료. 라이브 검증 통과.
> 아래는 각 항목의 원래 설계 명세이며 기록용으로 유지한다.
>
> - **P1** (5/5): 대화 요약 압축, 대화 변수/폼, 딥리서치 계획 편집 UI, 모델 파라미터 UI+에이전트 편집, chat+RAG 하이브리드
> - **P2** (5/5): 피드백 수집, 잡 사용량 미터링, 워크플로 저장/import-export, RAG PDF/DOCX 파싱+vacuum, CP 사용량 시계열+offline 알림
> - **P3** (5/5): 팟캐스트 TTS 엔진, 프롬프트 향상기, 이미지/페이지 엔진, 브라우저 도메인 allowlist, GraphRAG(MCP 1차 연동: `mcp_servers.json.example`)
>
> 후속 완료(2026-06-15):
> - **워크플로 앱 발행**: 에디터 'Publish' 버튼 → App(mode=workflow, params.workflow_id) 생성,
>   `POST /api/v1/workflow/saved/{id}/run`으로 실행. 라이브 검증 통과.
> - **이미지/TTS 실 API E2E**: 실제 OpenAI 호출로 png(1.3MB)·팟캐스트 mp3(10턴, 960KB) 생성 확인.
>   팟캐스트 대본 파싱을 OpenAI JSON 모드 + object 스키마 + 라인 폴백으로 견고화.
>
> 잔여 후보(미착수): GraphRAG 네이티브 엔진화(현재 MCP 경유 1차 연동으로 충분).
>
> 보안/운영 (2026-06-16):
> - **인증 하드닝**: SECRET_KEY production 강제(미설정 시 부팅 거부), `User.token_version` 기반
>   토큰 revocation + DB is_active/role 검증, access 8h + refresh 토큰(/auth/refresh,
>   /auth/logout-all), 프론트 authFetch 자동 refresh. role 변경 시 기존 세션 즉시 무효.
> - **DB 확장성 결정 — 단일 서버 운영 채택**: 고객사당 게이트웨이 1인스턴스 전제.
>   SQLite + WAL(busy_timeout/synchronous=NORMAL) 적용 → 동시 쓰기 80건 lock 에러 0 검증.
>   **Postgres/Redis 전환은 의도적으로 하지 않음** (현 규모에 불필요).
>   멀티 인스턴스 HA가 실제로 필요해지면: `DATABASE_URL=postgresql+asyncpg://...`(코드 변경 0) +
>   UsageTracker/JobManager를 Redis로 외부화. 그 전까진 단일 인스턴스가 더 단순/안전.

---

## P1-1. 대화 요약 압축 (장기 기억)

- **왜**: 현재는 최근 20턴 주입 + LLM 계층의 단순 다이제스트. 긴 상담에서 초반 맥락(고객 요구사항)이 유실된다. dify의 conversation summary 방식.
- **설계**:
  - `chat_sessions`에 `summary` 컬럼 추가.
  - `append_turn()`에서 메시지 수가 임계(예: 30턴) 초과 시 백그라운드로 "기존 summary + 오래된 턴들 → 새 summary" LLM 호출 후 저장.
  - `load_history()`는 `[system: 지금까지 요약…] + 최근 N턴` 형태로 반환.
  - 요약 LLM 호출은 fire-and-forget(asyncio.create_task)로 응답 지연 없게.
- **파일**: `services/gateway/src/zeropark_gateway/conversations.py`, `packages/zeropark-core/src/zeropark_core/models_db.py`
- **완료 기준**: 40턴 대화에서 1턴째 언급한 사실을 질문하면 답변 가능. 요약 생성이 응답 latency에 영향 없음(테스트).

## P1-2. 대화 변수 / 폼 입력 (dify conversation variables)

- **왜**: 에이전트가 시작 시 사용자에게 구조화된 입력(이름, 부서, 대상 제품 등)을 받아 프롬프트에 주입하는 기능. B2B 시나리오(고객지원봇이 사번/제품모델 먼저 수집)의 핵심.
- **설계**:
  - App 모델 `params.variables: [{key, label, type(text/select/number), required, options[]}]` 스키마 정의.
  - ChatWidget: 세션 시작 시 variables가 있으면 폼 렌더 → 값을 세션에 저장(`chat_sessions.variables` JSON 컬럼).
  - 게이트웨이: history 주입 시 system 메시지에 `{{key}}` 치환된 변수 컨텍스트 추가. system_prompt 내 `{{key}}` 템플릿 치환 지원.
- **파일**: `apps.py`(스키마 검증), `conversations.py`(변수 저장/주입), `ChatWidget.tsx`(폼 UI), `Dashboard.tsx`(admin이 에이전트 생성 시 변수 정의 UI)
- **완료 기준**: admin이 변수 2개를 정의한 에이전트 생성 → user가 채팅 진입 시 폼 표시 → 입력값이 system 프롬프트에 반영되어 답변에 사용됨.

## P1-3. 딥리서치 계획 편집 UI (deerflow HITL 화면 연결)

- **왜**: 백엔드 HITL은 완성(plan 생성 → `PAUSED` 반환 → `params.plan` 재제출로 재개)인데 화면이 없어 데모 불가. deerflow의 차별점.
- **설계**:
  - research 모드 에이전트에서 `params.hitl=true`로 실행 → PAUSED 결과의 plan(JSON)을 받아 섹션/검색어 편집 가능한 패널 렌더.
  - "승인 후 실행" 버튼 → 같은 프롬프트 + `params.plan`으로 재제출(스트림) → 섹션별 진행 이벤트(`phase: research`)를 타임라인으로 표시.
- **파일**: `ChatWidget.tsx` 또는 전용 `ResearchPanel.tsx`(신규), `useWidgets.ts`(PAUSED 분기)
- **완료 기준**: 검색 키 설정된 환경에서 계획 수정→재개→인용 포함 보고서까지 화면에서 완주.

## P1-4. 모델 파라미터 UI (에이전트별 모델/온도 설정)

- **왜**: 백엔드는 `params.model` 오버라이드를 이미 지원하는데 화면이 없음. 고객사별 "이 봇은 저렴한 모델, 저 봇은 고성능" 구성이 필수.
- **설계**:
  - Dashboard의 에이전트 생성/편집 모달에 model(텍스트 또는 게이트웨이가 내려주는 추천 목록), temperature, system_prompt 입력 추가.
  - `GET /api/v1/profile`에 사용 가능 모델 목록(env `ZEROPARK_LLM__MODELS` CSV) 노출.
  - 에이전트 편집(PATCH) UI — 현재는 생성/삭제만 있음.
- **파일**: `Dashboard.tsx`(편집 모달), `config.py`(models 목록), `main.py`(profile에 노출)
- **완료 기준**: 에이전트마다 다른 모델로 답변(metrics.model로 검증), 기존 에이전트 수정 가능.

## P1-5. chat+RAG 하이브리드 (지식 기반 대화)

- **왜**: 현재 chat 모드는 순수 대화, rag 모드는 단발 Q&A. "대화하면서 지식도 참조"가 실제 고객 기대치.
- **설계**:
  - `LLMChatEngine`에 옵션 주입: `retriever`(RAGEngine의 vector_store 공유) + `params.collection_ids`.
  - 매 턴: 사용자 질문으로 similarity_search(허용 컬렉션 필터) → 상위 k 청크를 system 컨텍스트로 추가 → 출처 메타를 RunEvent(`type: source`)로 방출.
  - 게이트웨이 RAG 권한 주입(`_secure_rag_params`)을 chat capability에도 적용(collection_ids 있으면).
- **파일**: `chat.py`, `loader.py`(retriever 배선), `main.py`(권한 주입 조건 확대)
- **완료 기준**: 컬렉션 고정한 chat 에이전트가 업로드 문서 내용으로 답하고, 권한 밖 컬렉션 문서는 인용 불가(테스트).

---

## P2-1. annotation / 피드백 수집 (dify)

- **왜**: 운영 중 품질 개선 루프. 사용자가 답변에 👍/👎 + 코멘트, admin이 모아서 검수.
- **설계**:
  - `message_feedback` 테이블(message_id, session_id, user_id, rating, comment).
  - `POST /api/v1/conversations/{sid}/messages/{mid}/feedback`, admin 조회 `GET /api/v1/admin/feedback`.
  - ChatWidget 말풍선에 피드백 버튼, Admin 페이지에 피드백 목록 탭.
- **완료 기준**: user 피드백 → admin 화면에서 세션 컨텍스트와 함께 열람.

## P2-2. 백그라운드 잡 사용량 미터링

- **왜**: `/api/v1/tasks`만 UsageTracker에 집계되고 `/api/v1/jobs`는 누락 — 잡 기반 과금 불가.
- **설계**: `jobs.py` 러너의 done 이벤트에서 `result.metrics.total_tokens` 추출 → `app.state.usage.record()` 호출(JobManager에 tracker 주입).
- **완료 기준**: 잡 완료 후 `/api/v1/usage` 카운터 증가(테스트).

## P2-3. 워크플로 저장/불러오기 + import/export

- **왜**: 에디터에서 만든 워크플로가 휘발됨. `workflows`/`nodes`/`edges` 테이블은 이미 존재(미사용).
- **설계**:
  - `POST/GET/PUT /api/v1/workflows` — React Flow JSON 그대로 저장(기존 Node/Edge 테이블 활용 또는 definition JSON 단일 컬럼으로 단순화 — 후자 권장).
  - 에디터 Save 버튼 연결(현재 장식), 목록에서 불러오기, JSON export/import 버튼.
  - 워크플로를 앱으로 발행: App.params.workflow_id → workflow 모드 실행 시 저장본 로드.
- **완료 기준**: 저장→새로고침→불러오기→실행. export한 JSON을 다른 배포본에 import 가능.

## P2-4. RAG 파일 파싱 확장 + 컬렉션 vacuum

- **왜**: 업로드가 .txt 디코드뿐이라 PDF/DOCX는 깨진 텍스트로 들어감. 또 컬렉션 삭제 시 Qdrant 벡터가 고아로 남음.
- **설계**:
  - `rag_upload`에서 mime별 추출: PDF(pypdf), DOCX(python-docx), 그 외 텍스트 폴백.
  - vacuum: 컬렉션 삭제 시 `client.delete(filter=collection_id)` 즉시 실행(지연 잡 불필요).
- **완료 기준**: PDF 업로드 → 질의 응답 성공. 컬렉션 삭제 후 Qdrant 포인트 수 감소 확인.

## P2-5. Control Plane 고도화: 사용량 시계열 + offline 알림

- **왜**: 현재 마지막 스냅샷만 저장 — 월별 과금/추세 불가, 배포본 죽어도 모름.
- **설계**:
  - `usage_records` 테이블(deployment_id, ts, snapshot) — 하트비트마다 append, 대시보드에 일/월 집계 차트.
  - offline 감지: 주기 체크(또는 조회 시점 계산)로 `last_heartbeat` 초과 배포본에 웹훅/이메일 알림(env로 웹훅 URL).
- **완료 기준**: 하트비트 N회 후 시계열 조회 API에 N행. 하트비트 중단 시 웹훅 발사(테스트는 mock).

---

## P3-1. 팟캐스트/오디오 엔진 (Capability.AUDIO)

- **왜**: modes에 podcast가 노출되지만 엔진 부재(미구성 표시 중). genspark 데모 포인트.
- **설계**: OpenAI TTS(`audio.speech`) 기반 `AudioEngine` — LLM이 대본(2인 대화) 생성 → 화자별 TTS → mp3 합치기(pydub) → artifact(kind=audio). 키 있으면 자동 등록.
- **완료 기준**: podcast 모드로 주제 입력 → mp3 artifact 생성/재생.

## P3-2. 프롬프트 향상기 (dify prompt generator)

- **왜**: admin이 system_prompt를 잘 못 씀. "한 줄 의도 → 구조화된 시스템 프롬프트" 자동 생성.
- **설계**: `POST /api/v1/apps/enhance-prompt` {intent} → LLM이 역할/제약/톤/출력형식 갖춘 프롬프트 반환. 에이전트 편집 모달에 ✨ 버튼.
- **완료 기준**: 의도 입력 → 생성된 프롬프트가 모달에 채워짐.

## P3-3. 이미지/페이지 엔진 (Capability.IMAGE / PAGE)

- **왜**: modes에 노출되나 엔진 부재.
- **설계**: IMAGE — OpenAI Images(gpt-image-1) 래핑, artifact(kind=image). PAGE — LLM이 단일 html 생성 → store 저장 + 정적 서빙 경로(`/artifacts/...`) 노출.
- **완료 기준**: 각 모드 "미구성" 배지 해제, E2E 스모크에 케이스 추가.

## P3-4. 브라우저 에이전트 정책 (도메인 allowlist + 감사)

- **왜**: 고객사 배포에서 에이전트가 임의 사이트 조작은 리스크. 현재 netguard(사설IP 차단)만 있음.
- **설계**: `ZEROPARK_BROWSER_ALLOWED_DOMAINS` CSV — navigate 시 도메인 검사, 위반 시 행동 거부 관찰값 반환. 방문 URL은 이미 sources로 감사 기록됨.
- **완료 기준**: allowlist 밖 도메인 navigate가 차단되고 사유가 결과에 남음(테스트).

## P3-5. GraphRAG (Neo4j) — 기존 Phase 25 예정 항목

- **왜**: 관계형 질의("A부서와 B프로젝트의 연관")는 벡터 검색만으로 약함.
- **설계**: MCP로 Neo4j 연동(우선) → 효과 검증 후 네이티브 엔진화 결정. 별도 설계 문서 필요.
- **완료 기준**: 1차 — MCP 경유 그래프 질의가 super_agent 도구로 동작.

---

## 운영 메모

- 사용량은 프로세스 재시작 시 리셋(P2-5의 시계열로 보완 예정).
- `Workspace`/`Workflow`/`Node`/`Edge` 테이블은 P2-3에서 활용 또는 정리 결정.
- 슬라이드 고객사 마스터 템플릿: `zeropark_engines/templates/{theme}.pptx`에 두면 자동 적용 — 고객 CI 입수 시 즉시 가능(코드 작업 불필요).
