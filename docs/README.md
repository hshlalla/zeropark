# Zeropark 개발 문서

OSS를 설계 참고만 하여 기능을 네이티브로 재구현하는 단일 AI 워크스페이스 프레임워크의 문서 폴더.
문서는 짧고 구조적으로 유지하고, 변경 시 관련 문서를 함께 갱신한다(`../AGENTS.md`).

## 폴더 구조

| 경로 | 성격 | 핵심 문서 |
|---|---|---|
| `project.yml` | 프로젝트 메타 | 프로젝트 식별·진행·문서 경로 |
| `01-planning/` | 계획/명세 | product-requirements, development-spec, api-spec, **capability-roadmap**, decision-log |
| `01-planning/architecture/` | 아키텍처 | architecture, system-flow, **dependency-isolation** |
| `02-progress/` | 진행 | progress, blockers, notes/, tasks/ |
| `03-quality/` | 품질 | test-plan |
| `04-operations/` | 운영 | deploy-guide, release-notes |
| `05-governance/` | 거버넌스 | version-control, developer-guide, llm-usage-policy |
| `oss-source-map.md` | OSS | 참고 OSS ↔ capability 매핑 |
| `runbooks/` | 런북 | 로컬 실행, 스모크 결과 |

## 먼저 읽을 문서

1. `01-planning/product-requirements.md` — 무엇을 만드는가
2. `01-planning/architecture/architecture.md` + `dependency-isolation.md` — 어떻게(네이티브·단일 리포)
3. `01-planning/capability-roadmap.md` — 무엇이 남았는가(갭·계획)
4. `02-progress/progress.md` — 지금 어디까지

## 핵심 원칙

엔진을 API로 호출하거나 서비스로 띄우지 않는다. OSS는 참고만, 기능은 네이티브 구현. Dify/SearXNG 소스는 차용 금지.
