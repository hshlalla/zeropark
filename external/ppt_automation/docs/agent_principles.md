# 모든 LLM 에이전트 공통 원칙

## 1. 눈대중 금지 / 도구 강제 (★★ 최우선 — 모든 LLM 에이전트)
이 원칙은 `agents/utils.TOOL_ENFORCEMENT_GUARDRAIL`로 **모든 LLM 에이전트 system 프롬프트에 자동 주입**된다(`load_contract`).

### 금지 (하면 실패)
- 숫자 **근사 추측** ("대략", "약 80%")
- **컬럼명 상상** (스키마에 없는 컬럼 사용)
- PPT에서 **보이지 않는 문맥 추정**
- **계산 없이 값 확정**

### 필수 (반드시 이 도구·근거 사용)
- **pptx_scanner 결과** 사용 (PPT 구조/값)
- **data_coverage 확인** (데이터·컬럼 존재)
- **formula_engine으로 계산**
- **answer_key와 오차 비교**
- **evidence 기록**

검증·계산되지 않은 값은 출력하지 말고 **unresolved + 사유**로 남긴다.

### 적용
| 에이전트 | 도구 강제 |
|----------|-----------|
| Reader | pptx_scanner 결과만 근거 (문맥 상상 금지) |
| Formula Synthesizer | 후보만 생성, 값 직접 생성 금지 |
| Formula Validator | raw_data로 **반드시 계산** |
| Formula Critic | 계산 결과·evidence 기반 판단 |
| Calculator | KeySpec을 **결정론 엔진으로 실행** |
| Insight Writer | 채워진 **실제 KPI 값만** 인용 |

## 2. 구조화 출력 (내부 사고 전부 출력 금지)
Thought→Plan→Action을 거치되 `analysis_summary` / `plan` / `action_result`만 남긴다.
(참고: planner-contract.md)

## 3. 선택적 정보 공개
각 역할에 필요한 정보만 전달한다. (참고: agent_io_contracts.md)
- Calculator: KeySpec만 (PPT 문맥 ✗)
- Critic: 후보 + 계산결과 + evidence

## 4. 실패는 구조화해서 넘긴다 (FailureReport)
Verifier는 실패를 `FailureReport`로 구조화한다:
```json
{
  "key": "bv_samsung_us_mom",
  "expected": "+1.2%p", "actual": "+2.7%p",
  "suspected_causes": ["wrong numerator", "wrong filter", "wrong period"],
  "next_action": "regenerate_formula_candidates"
}
```
Planner는 이걸 받아 **실패한 key만** 더 넓은 후보로 재합성한다.
