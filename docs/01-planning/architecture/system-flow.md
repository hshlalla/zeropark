---
doc_type: system_flow
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# 데이터 흐름 (Zeropark — 네이티브)

## 1. 프롬프트 → 산출물 (외부 호출 없음)

```mermaid
sequenceDiagram
  participant U as 사용자
  participant GW as Gateway
  participant R as Router (core)
  participant Reg as Registry (core)
  participant E as NativeEngine (in-process)
  participant L as 라이브러리 (httpx/pptx/…)

  U->>GW: POST /tasks {prompt, mode}
  GW->>R: plan(mode) → primary capability
  R->>Reg: for_capability(capability)
  Reg-->>R: 후보 엔진
  R->>R: 선호도/핀으로 1개 선택
  GW->>E: engine.execute(TaskRequest)
  E->>L: 라이브러리로 직접 수행 (네트워크는 대상 리소스에만)
  L-->>E: 결과
  E->>E: 정규화 (TaskResult/Artifact/SourceRef)
  E-->>GW: TaskResult
  GW-->>U: 정규화 JSON (+ 아티팩트 파일)
```

> 엔진 간 HTTP 호출이 없다. 네트워크는 crawl 대상 URL이나 LLM/검색 API 같은 "외부 리소스"에만 발생.

## 2. mode → capability 파이프라인

현재 `DEFAULT_MODES`: super_agent, research, slides, sheets, dashboard, browser, workflow.
파이프라인 중 등록된 엔진이 없는 capability는 에러가 아니라 `missing`으로 보고(부분 기능 배포 허용).
예) 현재 research 모드 → crawl만 등록되어 있으면 search·research는 missing.

## 3. capability → engine 선택

```mermaid
flowchart TD
  A["capability 요청"] --> B{"provider_id 핀?"}
  B -- 예 --> P1[해당 엔진]
  B -- 아니오 --> C{"capability_preferences?"}
  C -- 예 --> P2[선호 1순위]
  C -- 아니오 --> P3[등록 순서상 첫 엔진]
```

## 4. 설정 주입 (클라이언트별 배포)

```mermaid
flowchart LR
  ENV[".env / ZEROPARK_* env"] --> CFG["ZeroparkSettings"]
  CFG --> LOADER["engines.build_registry(output_dir, search)"]
  LOADER --> REG["ProviderRegistry"]
  REG --> ROUTER["Router(preferences)"]
```

기본 설치는 crawl·slides가 무설정으로 동작. search는 백엔드 설정 시 등록. LLM 설정 시 research/agent 활성(계획).
