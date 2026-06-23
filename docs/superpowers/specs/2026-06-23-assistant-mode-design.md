# Assistant 모드 (만능 채팅) — 설계 문서

**작성일:** 2026-06-23
**상태:** 승인됨, 구현 대기

## 1. 배경 & 문제

현재 Zeropark의 에이전트(`App`)는 **`mode` 필드를 하나만** 갖는다
([models_db.py:80](../../../packages/zeropark-core/src/zeropark_core/models_db.py)).
요청이 오면 `Router`가 그 capability에 맞는 **엔진 하나**를 골라 실행하므로,
"chat 에이전트"로 대화하던 사용자가 같은 대화 안에서 이미지 생성이나 슬라이드
제작으로 넘어갈 수 없다. 여러 도구를 섞는 유일한 엔진인 `SuperAgentEngine`은
검색/크롤/파이썬/MCP만 도구로 갖고 있고(slides·image·sheets 미노출),
planner→researcher→reporter 리서치 전용 루프라 일상 대화에 부적합하다.

**목표:** 관리자가 에이전트를 만들 때 **필요한 도구를 골라 묶을 수 있게** 한다.
챗만 필요한 사람에겐 챗만, 도구가 필요한 사람에겐 도구까지 엮어서 제공한다.
사용자는 한 대화창에서 모드 전환 없이 "이미지 만들어줘 / 슬라이드로 정리해줘"라고
하면 AI가 알아서 해당 도구를 호출한다.

## 2. 채택한 접근

**새 `AssistantEngine` (대화형 도구 루프).** 검토한 대안:

- **A. 새 AssistantEngine** ✅ 채택 — 경계가 깨끗하고(미니멀 chat · 리서치
  super_agent · 만능 assistant 셋이 각자 역할), 라우터 재사용으로 도구 확장이
  범용적이며, 기존 단일-모드 에이전트는 영향받지 않음.
- B. SuperAgentEngine 확장 — 리서치 루프와 대화 용도를 한 클래스에 욱여넣어
  책임이 흐려짐. 기각.
- C. LLMChatEngine을 도구 가능하게 — "도구 없음·최소 지연" 설계를 깨고 모든 chat
  에이전트 동작이 바뀔 위험. 기각.

**workflow 기능은 이번 범위에서 제외** — workflow(비주얼 DAG)는 결정적·반복
파이프라인용으로 assistant와 보완 관계이며, 별도 기능으로 그대로 유지한다.
("저장된 workflow를 assistant 도구로 통합"은 향후 과제로 남김.)

## 3. 아키텍처

기존 3계층(capability → mode → engine)을 그대로 따른다. 새 조각은 넷:

1. **새 capability** `ASSISTANT = "assistant"`
   ([capabilities.py](../../../packages/zeropark-core/src/zeropark_core/capabilities.py))
2. **새 mode** `assistant` ModePlan (primary=ASSISTANT, pipeline=(ASSISTANT,))
   ([router.py](../../../packages/zeropark-core/src/zeropark_core/router.py))
3. **새 engine** `AssistantEngine` — 대화형 도구 루프 (신규 파일
   `packages/zeropark-engines/src/zeropark_engines/assistant.py`)
4. **App 모델에 `tools` 컬럼 추가** — 에이전트별 도구 목록

## 4. AssistantEngine 내부 동작

`SuperAgentEngine`의 도구 루프를 빌려오되, 리서치 3단계를 버리고 **대화형 단일
루프**로 만든다:

```
사용자 메시지 + history(params.history)
   ↓
[LLM 호출 — 허용된 도구 스펙 첨부]
   ↓
도구 호출 있음? ──아니오──→ 텍스트 답변 반환 (= 일반 챗과 동일)
   │ 예
   ↓
각 도구 실행 → 라우터로 서브태스크 dispatch
   → 생성 아티팩트(이미지/PPTX)를 RunEvent로 UI에 즉시 emit
   → LLM에는 짧은 요약 텍스트 반환 ("slides 생성됨: deck.pptx")
   ↓
루프 (max_iterations 캡) → 최종 답변
```

**도구 = 라우터를 감싼 범용 어댑터.** capability → 도구 이름 매핑:

| 도구 이름 | Capability | 설명 |
|---|---|---|
| `generate_image` | IMAGE | 이미지 생성 |
| `make_slides` | SLIDES | PPTX 슬라이드 생성 |
| `make_sheet` | SHEETS | 엑셀 표 생성 |
| `research` | RESEARCH | 웹검색·크롤 기반 리서치 |
| `search_knowledge` | RAG | 업로드된 지식베이스 질의 |

각 도구가 호출되면 해당 `Capability`로 `TaskRequest`를 만들어 라우터가 고른
엔진에 넘긴다. **새 엔진이 생기면 이 매핑 테이블에 한 줄만 추가**하면 도구가 는다.

**엔진 의존성:** `AssistantEngine`은 생성 시 **registry + preferences 참조**를
받아 내부에서 `Router(registry, preferences)`로 capability→엔진을 호출 시점마다
선택한다 (super_agent가 search_engine을 직접 받던 것보다 범용적). loader는
registry를 채운 뒤 마지막에 AssistantEngine을 등록하며 그 registry 참조를 넘긴다.

**히스토리:** chat 엔진과 동일하게 `params.history`
([{role, content}, ...])를 받아 대화 맥락을 유지한다.

**스트리밍:** super_agent와 동일하게 `status` / `log` / `artifact` / `done`
RunEvent를 yield하여 UI가 Thought/Action/Observation 타임라인과 생성물을 렌더링한다.

## 5. 에이전트별 도구 선택 & 데이터 흐름

**App 모델** ([models_db.py:69](../../../packages/zeropark-core/src/zeropark_core/models_db.py))에 컬럼 추가:

```python
tools = Column(String, nullable=True)  # JSON: ["image","slides","sheets","research","rag"]
```

- **챗만 필요한 에이전트** → mode=`assistant`, `tools=[]` → 순수 대화.
- **도구 묶은 에이전트** → mode=`assistant`, `tools=["image","slides"]` 등.

**흐름:**

```
관리자가 에이전트 생성 (mode=assistant, tools 체크)
   ↓ DB의 App.tools에 저장
사용자가 그 에이전트로 대화 → 게이트웨이 /api/v1/tasks/stream
   ↓ App.tools를 task.params["tools"]에 주입
AssistantEngine: params["tools"]로 도구 스펙을 필터링
   → 허용된 capability만 LLM에 노출
   ↓
도구 호출 → 라우터 → 엔진 → 아티팩트 SSE로 스트리밍
```

**권한·안전장치:**

- `tools`에 있어도 **해당 배포에 엔진이 없으면**(registry 미등록) 자동 제외 —
  깨진 도구를 LLM에 노출하지 않음.
- RAG 도구는 기존 `allowed_collection_ids` 권한 클리핑을 그대로 통과 (역할 기반
  접근 유지).
- `tools` 미지정(기존 데이터)이면 기본값 = 빈 목록 → 순수 챗으로 안전하게 동작.

## 6. 에러 처리

- **도구 실행 실패** → 예외를 잡아 LLM에 `"Tool error: ..."` 텍스트로 반환.
  루프가 죽지 않고 AI가 설명하거나 대안을 시도 (super_agent
  [기존 패턴](../../../packages/zeropark-engines/src/zeropark_engines/super_agent.py)).
- **엔진 미등록** → 도구 스펙에서 조용히 제외.
- **max_iterations 초과** → 지금까지 결과로 최종 답변 생성 (무한루프 방지).
- **LLM이 도구 0개 호출** → 일반 챗과 동일 경로 → 순수 대화 에이전트도 같은
  엔진으로 동작.

## 7. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `packages/zeropark-core/src/zeropark_core/capabilities.py` | `ASSISTANT` capability 추가 |
| `packages/zeropark-core/src/zeropark_core/router.py` | `assistant` ModePlan 추가 |
| `packages/zeropark-engines/src/zeropark_engines/assistant.py` (신규) | `AssistantEngine` |
| `packages/zeropark-engines/src/zeropark_engines/loader.py` | AssistantEngine 등록 (registry 참조 주입) |
| `packages/zeropark-core/src/zeropark_core/models_db.py` | `App.tools` 컬럼 |
| `services/gateway/src/zeropark_gateway/main.py` | App.tools → task.params 주입 |
| 프론트(관리자 UI) | 에이전트 생성 시 도구 체크박스 |

## 8. 테스트 전략 (TDD)

기존 [test_super_agent.py](../../../packages/zeropark-engines/tests/test_super_agent.py) 스타일을 따른다.

1. **도구 호출 → 아티팩트** — 가짜 LLM(도구 호출 강제) + 스텁 image 엔진을 가진
   가짜 registry → 아티팩트 emit + LLM에 요약 피드백 검증.
2. **허용 도구 필터링** — `params["tools"]=["image"]`일 때 slides 도구가 스펙에
   없음을 검증.
3. **순수 챗 폴백** — `tools=[]`일 때 도구 없이 텍스트만 반환.
4. **라우터 모드 등록** — `router.plan("assistant")`가 ASSISTANT를 primary로 반환.
5. **미등록 엔진 제외** — registry에 slides 엔진이 없으면 도구 목록에서 빠짐.

## 9. 범위 밖 (YAGNI / 향후)

- 저장된 workflow를 assistant 도구로 호출 (`run_workflow`).
- 도구 호출 비용/토큰 한도 per-에이전트 제어.
- browse/audio/page 도구 노출 (어댑터에 한 줄 추가로 언제든 확장 가능).
