# 인사이트 프롬프트 맵 (슬라이드 → 프롬프트)

각 슬라이드의 `{{... Insight/Message/Highlight ...}}` 플레이스홀더가 **어떤 프롬프트로**
채워지는지 정리한 참조 문서. 실제로 LLM 에 가는 문자열은 `python tools/dump_prompts.py` 로
`docs/prompts_dump.md` 에 그대로 덤프할 수 있다(생성 호출 없음).

관련 파일
- 규칙 문구: [geo_report/prompts/rules.py](../geo_report/prompts/rules.py)
- 프롬프트 조립: [geo_report/prompts/builders.py](../geo_report/prompts/builders.py)
- 국가 헤드라인 예시: [geo_report/prompts/headline_examples.py](../geo_report/prompts/headline_examples.py)
- 슬라이드→섹션·슬롯 라우팅: [geo_report/config/slide_map.py](../geo_report/config/slide_map.py)
- 오케스트레이션(어떤 context/length/후처리): [geo_report/insights.py](../geo_report/insights.py) `collect_jobs`
- 과거 메시지 few-shot: [geo_report/governing.py](../geo_report/governing.py)

---

## 1. 프롬프트 조립 골격 (모든 슬라이드 공통)

`insights.collect_jobs` 가 슬라이드별로 파라미터(job)를 모으고,
`_generate` 가 [builders.py](../geo_report/prompts/builders.py) 로 두 문자열을 만든다:

```
system_prompt = SYSTEM_BASE + GOVERNING_CONSTRAINTS + [섹션/슬롯 규칙(rule)]
user_prompt   = 슬라이드 제목
              + topic_guide(주제 한정)  또는  headline_guide(국가 헤드라인)
              + SUMMARY_GUIDE(요약 슬라이드만)
              + [실제 수치 데이터 = context]   ← 슬라이드 그룹마다 다름(아래 표)
              + examples_block(거버닝 few-shot)
              + vocab_block(강조 후보)
              + LEN_RULES[length]
              + 출력형식(JSON: text/highlight/emphasis)
```

- `SYSTEM_BASE` = 역할 한 줄, `GOVERNING_CONSTRAINTS` = 전 섹션 공통 제약(MSG Guide 5개 규칙).
- 캐시: `system + user` 의 sha256 키로 `data/insight_cache.json` 에 저장 → 동일 프롬프트는 재호출 없음.

## 2. 슬라이드 → 프롬프트 매핑

섹션은 `insight_section(idx)` 로 결정 ([slide_map.py](../geo_report/config/slide_map.py)):
`idx≤4`=Summary, `idx 5~12`=Performance Breakdown, `idx≥13`=Status by 13 Countries.

| 페이지(idx) | 섹션 | rule | context(수치/근거) 출처 | length | 특수 처리 |
|---|---|---|---|---|---|
| **3** (idx2) Monthly Summary | Summary | 슬롯별: 상단 `SLIDE3_TOP_RULE` / 하단 `SLIDE3_BP_RULE` | **완성된 7~27 상세 요약** `_slide3_context_from_detail(kind)`(슬롯→상세장표) ※ fallback `_slide3_context` | medium | 6 슬롯 라우팅(`SLIDE3_SLOTS`) |
| **4** (idx3) Monthly Highlight | Summary | `SLIDE4_RULE`(덮어씀) | **완성된 7~27 상세 요약** `_summary_topic_context_from_detail(topic)` ※ fallback `_topic_context`+`_report_summary_context` | medium | 🚦신호등(하락→체크 빨강) |
| **5** (idx4) Appendix | Summary | `SECTION_RULES["Summary"]` | **완성된 7~27 상세 요약**(위와 동일) | medium | 🚦신호등 |
| **7–13** (idx6–12) | Performance Breakdown | `SECTION_RULES["Performance Breakdown"]` | `_kpi_context(slide)` — **슬라이드에 채워진 KPI 표/값을 긁어서** 사용 | short(셀)/long(박스) | 핵심구절 **남색 강조** |
| **15–27** (idx14–26) | Status by 13 Countries | `SECTION_RULES["Status by 13 Countries"]` | `_country_context(co)` — 해당국 vs Global 채널 + MX Owned | short(셀)/long(박스) | 1번째 = **국가 헤드라인** |
| 1·2·6·14 | — | — | — | — | 표지·섹션 구분 슬라이드(`{{}}` 없음 → 생성 안 함) |

### 인사이트 생성 순서 — 2-pass (detail-first)

`fill_insights` 는 두 번에 나눠 생성한다(값·집계·KPI·차트는 이 단계 이전에 이미 확정·불변):
1. **Pass 1 — 상세(7~27)** 인사이트 먼저 생성·적용 → 상세 슬라이드 '완성'.
2. **re-grounding** — 각 요약(3~5) job 의 context 를 `_reground_summary_job` 으로 교체:
   집계 수치 → **완성된 7~27 상세 슬라이드 요약**(제목 + KPI 값 + 생성된 인사이트 + 강조).
   상세가 비면 기존 집계 context 로 fallback. 집계 수치는 '보조 참고용'으로 뒤에 덧붙는다.
3. **Pass 2 — 요약(3~5)** 인사이트 생성·적용.

> 핵심: 이 변경은 요약 인사이트의 **data source 가 아니라 narrative source** 만 바꾼 것.
> 3~5 가 "집계값을 다시 설명"하는 대신 "상세 슬라이드에서 이미 보여준 결과를 경영 요약형으로 압축"한다.
> 숫자/KPI/차트/집계는 그대로다.

### 슬라이드 3 의 6개 슬롯 ([slide_map.py `SLIDE3_SLOTS`](../geo_report/config/slide_map.py))

| 플레이스홀더 | 주제 | context kind | 슬롯유형(rule) |
|---|---|---|---|
| Highlight Message 1 | Brand Visibility | bv | top |
| Highlight Message 2 | MX Reference Visibility | rv | top |
| Highlight Message 3 | Brand Sentiment | sentiment | top |
| Insight Message 1 | MX Owned 자산 | owned | bp |
| Insight Message 2 | MX External 자산 | external | bp |
| Insight Message 3 | Co.A 경쟁 비교 | coa | bp |

## 3. context(수치 데이터) 빌더별 내용

| 빌더 | 입력 | 내용 |
|---|---|---|
| `_slide3_context(a, ctx, kind)` | 집계 | 슬롯(bv/rv/sentiment/owned/external/coa)별 전용 지표 줄 |
| `_topic_context(a, ctx, topic)` | 집계 | 주제 지표의 당월/전월 수치(MoM) |
| `_report_summary_context(a, ctx)` | 집계 | 리포트 전체 핵심 KPI + BV 기준 Global 比 상·하위국 |
| `_country_context(a, ctx, co)` | 집계 | 해당국 vs Global 외부채널 비교 + MX Owned 성과 |
| `_kpi_context(slide)` | **렌더된 슬라이드** | 그 슬라이드에 이미 채워진 KPI 표/텍스트 값 수집 |
| `_slide3_context_from_detail(prs, kind)` | **렌더된 상세** | 슬3 슬롯 → 관련 상세장표(`_DETAIL_FOR_SLOT`) 요약 |
| `_summary_topic_context_from_detail(prs, topic)` | **렌더된 상세** | 슬4·5 주제 → 관련 성과장표(`_detail_idxs_for_topic`) 요약 |
| `_slide_digest(slide, n)` | **렌더된 슬라이드** | 한 슬라이드 → 제목+KPI줄+인사이트 n개 블록(위 2개의 부품) |

> 정리: **3·4·5 = 렌더된 7~27 요약**(narrative), **7~13 = 렌더된 자기 슬라이드 KPI**,
> **국가 15~27 = 집계 기반 vs Global**. 집계 기반 빌더(`_topic_context`/`_report_summary_context`/
> `_slide3_context`)는 3~5 의 **fallback** 으로만 남는다.

## 4. "어디를 고치면 무엇이 바뀌나"

| 바꾸고 싶은 것 | 파일 |
|---|---|
| 역할·공통 제약·섹션/슬롯/길이 규칙 문구 | [rules.py](../geo_report/prompts/rules.py) |
| 프롬프트 조립 순서·블록 | [builders.py](../geo_report/prompts/builders.py) |
| 국가 헤드라인 예시(형식) | [headline_examples.py](../geo_report/prompts/headline_examples.py) |
| 슬라이드→섹션, 슬롯 라우팅 | [slide_map.py](../geo_report/config/slide_map.py) |
| 슬라이드별 context 종류·length·신호등·남색 | [insights.py `collect_jobs`](../geo_report/insights.py) |
| **few-shot 예시(내가 직접)** | [prompts/fewshot.py](../geo_report/prompts/fewshot.py) |
| few-shot 예시(과거 MSG Text·fallback) | [governing.py](../geo_report/governing.py) |

### few-shot 예시 주입 ([prompts/fewshot.py](../geo_report/prompts/fewshot.py))

우선순위(첫 '비어있지 않은' 소스 채택), 섹션마다 중간 소스가 다름:
- **요약(3·4·5)**: `BY_SLIDE` > `BY_SECTION` > 거버닝. 슬3 은 `BY_SLIDE[3]={"top":..,"bp":..}`
  (상단 Highlight / 하단 BP), 슬4·5 는 묶음(`S45_EXAMPLES`).
- **성과(7~13)**: `BY_SLIDE` > **`BY_METRIC`**(Brand Visibility/Sentiment Share/Reference Share/
  Reference Visibility) > `BY_SECTION` > 거버닝.
- **국가(15~27)**: `BY_SLIDE` > **`BY_COUNTRY`**(국가코드 US/UK/…) > `BY_SECTION` > 거버닝.

전부 비우면 거버닝 그대로(현재 동작과 동일).

## 5. 프롬프트 덤프 도구

```
python tools/dump_prompts.py                 # docs/prompts_dump.md 로 저장
python tools/dump_prompts.py 다른경로.md
```

LLM 호출 없이, production 과 **동일한** 조립 경로(`insights.collect_jobs` +
`prompts.system_prompt/user_prompt`)로 슬라이드별 system/user 프롬프트를 그대로 출력한다.
성과(7~13) 슬라이드의 `_kpi_context` 가 실제 채워진 값을 읽도록, 먼저
`build_report.fill_slides` 로 슬라이드를 채운 뒤 프롬프트를 재현한다.
