---
doc_type: api_spec
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# API 명세 (Zeropark Gateway)

게이트웨이는 코어/엔진에 위임하는 얇은 계층입니다. 응답은 core의 정규화 모델(TaskResult 등)을 따릅니다.

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/health` | 상태 + 등록된 네이티브 엔진/capability |
| GET | `/providers` | 런타임 엔진 메타(id/name/capabilities/reference) |
| GET | `/catalog` | OSS 설계 참고 목록(라이선스·차용가능 여부) |
| GET | `/modes` | mode→capability 파이프라인 |
| POST | `/route` | mode 계획(실행 X): capability별 선택 엔진 + missing |
| POST | `/tasks` | mode primary capability 실행 → TaskResult |
| POST | `/search` `/crawl` `/slides` | capability 직접 실행(편의) |

## POST /tasks

```json
// 요청
{ "mode": "slides", "prompt": "회사 소개",
  "params": { "title": "Overview", "outline": [ { "title": "Intro", "bullets": ["..."] } ] } }
// 응답 (TaskResult)
{ "task_id": "task_...", "status": "succeeded", "capability": "slides",
  "provider_id": "pptx-slides",
  "artifacts": [ { "id": "deck_...", "kind": "deck", "uri": "artifacts/task_....pptx" } ] }
```

## POST /crawl

```json
{ "url": "https://example.com" }
// → TaskResult: artifacts[0].kind="page", inline=markdown, sources[0].url=...
```

## 에러 매핑

| 상황 | 코드 |
|---|---|
| capability 제공 엔진 없음 | 503 |
| 엔진 미설정(ProviderNotConfigured) | 503 |
| 외부 리소스 fetch 오류 | 502 |
| 알 수 없는 mode | 400 |
