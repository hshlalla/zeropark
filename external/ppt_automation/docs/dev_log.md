# 개발 로그 (Dev Log) — 기능별

MX GEO Monitoring Report 자동화 개발 일지. 날짜순이 아니라 **기능/모듈별**로 묶어 기록한다.
각 항목 끝의 `(updated YYYY-MM-DD)` 는 마지막으로 손댄 날짜(여러 번이면 마지막 날짜).

> 작업 기간: 2026-05-29(1일차 구축) ~ 2026-06-08(5계층 패키지 재편 + 폰트/색상 정비).
> 빌드: `bash run.sh` 또는 `python build_report.py [--llm]` · 입력: `raw_data/*.xlsx`(5종) + `template/` + `governing_message/`.
> 패키지 구조: `config / data / slides / insights / pptx` 5계층 + 루트(`pipeline`·`context`). 상세는 루트 `README.md`.

---

## 1. 아키텍처 / 패키지 구조

- **레이어드 아키텍처 초기 설계**: 템플릿 2종·엑셀 5종 분석 → `geo_report/` 패키지로 구성. (updated 2026-05-29)
- **config.py → `config/` 패키지**: `paths`·`dates`·`slide_map`·`channels`·`llm` 로 분리, `__init__` 에서 re-export(기존 `from . import config` 호환). (updated 2026-06-02)
- **prompts.py → `prompts/` 패키지**: `rules`·`headline_examples`·`builders`, `__init__` re-export. (updated 2026-06-02)
- **전역 날짜 상태 제거 → `ReportContext`(frozen dataclass: cur/prv/countries/global_key)**: `_apply_dates()` 의 전역 mutate 제거, 모든 채우기 함수에 ctx 명시 전달. 산출물 diff 0. (updated 2026-06-05)
- **데이터 차원(국가목록·global_key) ctx 일원화**: 모듈 전역 `COUNTRIES`/`C.GLOBAL`/`C.COUNTRY_ORDER` 제거 → 전부 ctx 에서 읽음(국가 subset·regional 확장 대비). (updated 2026-06-05)
- **build 로직 추출**: `build_report.py` = thin CLI, 실로직은 `geo_report/pipeline.py`(`build`/`fill_slides`/`get_aggregates`). (updated 2026-06-05)
- **파이썬 컨벤션 정리**: `requirements.txt` 신규(런타임 의존성), private→public 승격(`_get_aggregates`→`get_aggregates`, `_plot_area`→`plot_area` — 모듈 밖에서 쓰던 함수). (updated 2026-06-08)
- **5계층 패키지 재편 (파이프라인 단계 = 폴더)**: `infra/`+`renderers/` → **`pptx/`**(저수준), `fillers/summary/country` → **`slides/`**(`performance`←`fillers`), `aggregator/aggregations/loader` → **`data/`**(`calculations`←`aggregations`), `insights/governing/prompts` → **`insights/`** 패키지 통합. 루트엔 `pipeline`·`context`만. import 전수 갱신, 회귀(골든 포함) diff 0. (updated 2026-06-08)
- **런타임 폴더 분리**: 루트 `data/`(캐시+상태 혼재) → **`cache/`**(재생성 캐시, gitignore) + **`state/`**(`trend_history.json`, 추적). 코드/패키지 `data/` 와의 이름 혼동 제거. (updated 2026-06-08)

## 2. 데이터 로딩 · 집계 (`data/loader` · `data/calculations` · `data/aggregator`)

- **로드·정규화·집계 번들**: `loader.load_raw`(엑셀+date 정규화), `aggregator.build`(`calculations` 일괄 실행 → 번들). `calculations`(구 `aggregations`)는 외부 의존 0(순수 pandas). (updated 2026-05-29)
- **Claude 제외 버그**: 4월부터 Claude 데이터가 Total 집계에 섞여 BV 가 75.7% 로 뭉개짐 → `config.EXCLUDE_PLATFORMS=['Claude']` 로 제외 → BV Total **76.8%** 정상화. (updated 2026-05-29)
- **데이터 소스 정정 2-2 → 2-1-1(Reference Share)**: 슬9 차트57·표35/47/45/88·차트36 을 `rs_pct`(2-1-1)로 교체(Media 35.3% 등 AX 일치). (updated 2026-06-01)
- **Apple(Co.A) 집계 신설**: `_sent_apple`/`apple_sent_pos_pct`(Sentiment), `rv_apple`/`apple_rv_pct`(RV). 2-3 엔 Apple 있어 BV Co.A 정상, 2-2/2-4 는 데이터 들어오면 자동 표시. (updated 2026-06-04)
- **현재월 자동 감지**: raw `date` 최신 2개 → `cur_date`/`prv_date` 산출(하드코딩 제거, 매월 자동). (updated 2026-06-04)
- **Co.A 인용건수 집계**: `rc_apple`(2-1-1 Apple-only) + `apple_rc_val`(Owned 건수). 차트106 Co.A 계열용. 현재 raw 2-1-1 은 Samsung-only라 None(실데이터에 Apple 들어오면 자동 계산). (updated 2026-06-08)

## 3. 슬라이드 채우기 — 성과 7~13 (`slides/performance`)

- **BV/Sentiment/AI Citation/Owned 1·2/External 1·2** KPI표·국가표·차트·MoM 오버레이 채움. (updated 2026-05-29)
- **도형 식별 버그**: `표 79`(KPI)와 `모서리 직사각형 79` 번호 겹침 → `find_table`/`find_chart`(타입 구분). (updated 2026-05-29)
- **슬11 KPI 정정**: 표28 이 Dotcom(39.2%)로 집계되던 것 → MX Owned 총합 **46.4%**(`fill_owned_2` 를 `"Owned"`로). (updated 2026-06-02)
- **슬7 BV by Intent MoM 라벨 위치 오할당** 교정(6=Support, 7=Recommendation). (updated 2026-06-04)
- **차트106 `# of Citation` 에 Co.A 계열 추가**: `apple_rc_val`(2-1-1 Apple Owned). MX 와 함께 13개월 트렌드. (updated 2026-06-08)

## 4. 슬라이드 채우기 — 국가 15~27 (`slides/country`)

- **구조 기반 식별**: 도형 번호가 슬라이드마다 달라 `find_chart_by_cat(n,cat0)`·`find_table_by_header` 로 식별. 텍스트 셀은 `set_cell_text`(전체 덮어쓰기). (updated 2026-05-29)
- **잔여 템플릿값(0.0%) 처리**: `_fill_mx_owned_value`(채널차트 위 MX Owned 값) 등으로 39 → 13건 감소. (updated 2026-06-01)
- **vs.Global / vs.Co.A**: 새 줄·12pt·부호색·가운데정렬(`_set_vs_cell`). 값 없으면 `-%p`(검정). vs.Global=해당국−Global. (updated 2026-06-05)
- **BV-vs-Global 차트 복제(KR/JP 누락 보충)**: 템플릿상 차트 없고 '수동 그룹'만 있던 KR/JP → `clone_chart_shape`/`ensure_bv_vs_global_chart` 로 독립 복제, 겹친 그룹 제거. 차트 xlsx/colors/style 을 각각 새 Part 로 복사(PowerPoint '복구' 경고 해결). (updated 2026-06-04)
- **(vs. Global) 차트 %p 오버레이 = 해당국−Global**(당월): `_fill_chart_overlays`/`_vs_global_cols`. (updated 2026-06-04)
- **Dotcom 컬럼 정합성**: 채널차트(89)가 `Dotcom_Only`(21.2%)를 써서 큰차트(104, 35.4%)와 불일치 → `COUNTRY_RV_CHANNEL_COLS` Dotcom 을 `Owned__Dotcom_Support_Total` 로(incl.Support, 13개국 공통). (updated 2026-06-05)
- **RV 차트 0값 라벨 처리**: 완전 0 → `-%`(검정), 0인데 0.0%로 뭉개지면 유효숫자까지 확장. 템플릿 수동 dLbl `-` 제거(`_apply_pct_dash_labels`). (updated 2026-06-05)

### Top Cited Domain (국가 표)
- **AX 친화명 출력**: `DOMAIN_DISPLAY`/`domain_display`(youtube→YouTube, samsung.com→Dotcom …). (updated 2026-06-01)
- **Total 행 = 100.0%**(상위 N 합계 아님), 개별 % 그대로. (updated 2026-06-04)
- **동점 등수**: 경쟁식 순위(`1 + 자기보다 큰 share 수`), 동점이면 `*` 접두(`*18, *18, 20`). 동점 기준은 실제 share 6자리 정밀도. (updated 2026-06-05)
- **Change(순위변동) 컬럼**: ▲N 파랑(0000FF)/▼N 빨강(FF0000)/-·NEW 기본. 현재·이전월 둘 다 경쟁식 등수 기준(`_top_domains_prev`). (updated 2026-06-05)
- **강조 색**: MX Owned 행 셀 배경 `#C1E6FF` 채움만(노란 박스/테두리 제거 — 그중 일부는 템플릿 자체 박스라 템플릿에서 제거). (updated 2026-06-04)
- **폰트 통일**: 데이터 행 전체를 **Samsung SS Body KR Regular 9pt** 로(`io.set_table_font`/`_set_run_font` — latin·ea·cs 타입페이스 모두 지정해 한글 적용). 헤더는 템플릿(Bold 9pt) 유지. (updated 2026-06-08)

## 5. 슬라이드 채우기 — 요약 3·4·5 (`slides/summary`)

- **슬3 Monthly Summary KPI 대시보드**(텍스트박스, 5엑셀, ▲▼+부호색), **슬4 Highlight**, **슬5 Appendix**. MX Gen AI Traffic·Similarweb 제외. (updated 2026-05-29)
- **신호등**: 지표 MoM 방향 자동 부여. 초기 글머리 '●'(녹/적) → 이후 ● 제거하고 **하락 시 초록체크→빨강체크 이미지 교체**(`assets/check_red.png` + `_swap_picture_image`, 템플릿 체크가 PICTURE 라 색변경 불가). (updated 2026-06-04)
- **Insight & Summary(슬4) 두 줄 중복 수정**: 같은 표·topic 셀을 묶어 한 번에 n개 생성 후 분배. (updated 2026-06-04)

## 6. 인사이트 LLM (`insights/engine`)

- **플레이스홀더 → LLM 생성**: `{{…Insight/Message/Highlight}}` 채움. autofit 로 칸 내 수렴. (updated 2026-05-29)
- **슬3 6슬롯 분리**: 상단 Highlight=BV/RV·External/Sentiment, 하단 BP=MX Owned/External/Co.A. 슬롯별 전용 컨텍스트로 중복 제거. (updated 2026-06-01)
- **OpenAI(gpt-4o-mini) → Claude 전환**: `INSIGHT_LLM_MODEL="claude-sonnet-4-6"`, 키는 `.env` 에서 SDK 에만 전달. (updated 2026-06-01)
- **2단 캐싱**: 인사이트 캐시(`cache/insight_cache.json`, 모델+system+user 해시)로 11분 → 14초. (updated 2026-06-02)
- **529/429/5xx 재시도**: `max_retries=6` 지수 백오프(과부하 시 회복 후 재빌드로 자동 채움). (updated 2026-06-04)
- **'(주제명)' 접두사 제거**: `_strip_topic_prefix`(LLM 이 본문 앞에 `(Reference Visibility)` 등 붙이는 것 제거). (updated 2026-06-04)
- **요약(3~5) grounding: 집계 → '완성된 7~27 상세 요약'(2-pass, detail-first)**: ①상세 먼저 생성·적용 → ②요약 context 를 `_reground_summary_job` 으로 교체 → ③요약 생성. 숫자/KPI/차트 불변, narrative source 만 변경. (updated 2026-06-05)
- **`collect_jobs` 추출**: 생성·덤프가 동일 조립 경로 공유. (updated 2026-06-05)

## 7. 프롬프트 시스템 (`insights/prompts` + `insights/governing`)

- **프롬프트 분리**: insights 인라인 문구 → `prompts.py` 로 이동(`SYSTEM_BASE`/`LEN_RULES`/`SUMMARY_GUIDE`/`*_guide`/`*_block`/`system_prompt`/`user_prompt`). 로직과 문구 완전 분리. (updated 2026-06-01)
- **거버닝 = 데이터→텍스트 Few-shot**: MSG Text → `{section,data,text}` 레코드, 주제→Data 유형 매핑(`data_for_topic`)으로 같은 지표 예시 우선. MSG Guide → `GOVERNING_CONSTRAINTS`(①±0.5%p 후순위 ②반복금지 ③원인·해석 ④개조식 종결 ⑤근거 한정). (updated 2026-06-01)
- **문구 단일화**: config 에 흩어진 SECTION_RULES·SLIDE3_*_RULE 등 전부 prompts 로, config 는 wiring 만. (updated 2026-06-01)
- **요약 길이 보정**: `medium`(50~75자) 도입(과축소된 short 25~40자 보정). (updated 2026-06-01)
- **사용자 few-shot 레지스트리 `prompts/fewshot.py`**: `BY_SLIDE`>`BY_METRIC`>`BY_SECTION`>거버닝 우선순위. 비우면 거버닝과 동일(동작 무변경). (updated 2026-06-05)
- **문서**: `docs/prompt_map.md`(슬라이드→프롬프트 매핑) + `tools/dump_prompts.py`(LLM 미호출 실제 프롬프트 덤프 → `docs/prompts_dump.md`). (updated 2026-06-05)

## 8. 강조 시스템 (`pptx/highlight`)

- **A안**: LLM 이 인사이트별 강조 대상을 슬라이드 라벨 후보에서 선택 → 위치 매핑. 표 셀/행/열(`#FFC000`), 차트는 manualLayout(plot 영역) 슬롯만. (updated 2026-05-29)
- **insight↔강조 일치 재설계**: LLM 별도 라벨 대신 인사이트 텍스트(emphasis 우선)가 실제 언급한 대상만 매칭. 정렬 버그(`cell_bbox`/`_col_lefts`/`_row_tops`) 보정 — top-anchored 누적이 정답. (updated 2026-06-02)
- **색상 규칙**: Top Domain MX Owned→파랑 채움(`#C1E6FF`), Local/Regional→노랑(이후 노란박스 제거). (updated 2026-06-02)
- **강조 최소화**: 차트 슬라이드당 1개, 데이터 표당 1개(열>행), KPI 값/MoM 오버레이·도메인표 제외. (updated 2026-06-02)
- **Global/국가 제외 + 별칭 매칭**: 국가 슬라이드는 'Global' 카테고리 차트 제외, 성과 슬라이드 표는 국가 행/열 제외(`_COUNTRY_CODES`). 차트 카테고리 긴이름↔짧은이름 `_CAT_ALIAS` 매칭. (updated 2026-06-04)
- **헤더/범례 회피**: 표 열 강조 row2 부터(헤더 제외), 차트 강조 top 을 plot 영역 기준(상단 범례 회피). (updated 2026-06-04)

## 9. 서식 · 색상 (`pptx/formatters` · `pptx/io`)

- **포맷터**: `76.8%`/`+0.9%p`/`25.9K`/`x0.85`, **적응형 소수**(0.0 으로 뭉개지면 유효숫자까지 확장). (updated 2026-05-29)
- **MoM 색상**: `_colorize_mom` — `±X.X%p` 양수 `#0000FF`/음수 `#FF0000`. 'MoM' 라벨은 검정 유지하고 화살표+값만 색칠(`_write_mom_runs`). (updated 2026-06-01)
- **셀 글자색 인자**: `set_cell_text(color=)` 신설(Change 순위변동 색 등). (updated 2026-06-04)
- **표 셀 = 플레이스홀더 토큰 치환**(%·%p·K·x), 텍스트 셀은 전체 덮어쓰기. (updated 2026-05-29)
- **배수(xN) 색상**: `_colorize_mom`+`_token_color` 확장 — 배수가 **1 초과면 파랑 / 1 이하면 빨강**(슬9 표45 x배 열, 슬3 요약 박스 일관). (updated 2026-06-08)
- **표 폰트 일괄 지정**: `set_table_font`/`_set_run_font` 추가(latin·ea·cs 타입페이스 모두 → 한글 폰트 적용). (updated 2026-06-08)

## 10. 트렌드 롤링 (`pptx/trend_store` · `pptx/markers`)

- **13개월 롤링 윈도우 + 영속 누적**: `trend_months(date,n)` + `TrendStore`(`state/trend_history.json`). CUR 만 바꾸면 윈도우 자동 롤(7개월 미니트렌드/13개월 풀트렌드 공용). (updated 2026-06-01)
- **마커·음영 이동**: `reposition_subs_markers` 가 '13 Subs' 구분선·음영을 현재 윈도우 26.Jan 슬롯으로. 월 카테고리(트렌드) 차트만 처리(`_is_trend_chart`, 채널 막대차트 오인 방지). (updated 2026-06-04)
- **음영 회귀 수정**: `_is_shade` 가 밝은 배경 패널(D3D8FD 등)까지 옮기던 것 → 진한 음영(8C9AFB)만(밝은 색 min RGB≥0xC0 제외). (updated 2026-06-05)
- **센티먼트 트렌드 공백**: `replace_chart(blank_none=True)` — 값 없는 월(25.09 이전)은 0 대신 공백 → 라인 시작점 정상. (updated 2026-06-04)
- **영역체크(AX seed) 의존 제거**: 과거값을 `state/trend_history.json` 에서만 읽음. `pptx/history.py`(TrendHistory)·`AREA_CHECK_TEMPLATE`·`AX_ANCHOR_DATE`·hist 배선 전부 제거. 시드값은 이미 json 에 누적돼 있어 무손실(빌드 검증: json 키 11개 완비). AX 영역체크 .pptx 도 repo 에서 제거. (updated 2026-06-08)

## 11. 빌드 · 캐싱 (`pipeline`)

- **출력 타임스탬프**: `output_path(ts)` `YYYYMMDD_HHMMSS`(덮어쓰기 방지). (updated 2026-05-29)
- **집계 캐시**(`cache/aggregates_cache.pkl`): raw mtime/size+제외설정 동일 시 엑셀 로드·집계 skip. 인사이트 캐시와 합쳐 1차 339초 → 2차 14초. (updated 2026-06-02)
- **한방 빌드 스크립트 `run.sh`**: 의존성 설치 + `build_report.py` 실행. 옵션 `--no-llm`/`--out`/`SKIP_DEPS=1`, pip 버전알림 끔. (updated 2026-06-08)

## 12. 품질 · 테스트 · 운영

- **죽은 코드 정리(-211줄, 동작 무변경)**: pyflakes·vulture 로 미사용 식별 후 제거(highlight 헬퍼 11개 등). (updated 2026-06-05)
- **값 회귀 테스트 안전망** `tools/regression/`(구 tests/): formatters/ranking 순수 테스트 + KPI 골든(characterization, `RUN_GOLDEN=1` 시만). LLM 인사이트는 비결정적이라 제외. (updated 2026-06-05)
- **GitLab push**: `single-agent`→이후 `refactor` 브랜치(원격 master=멀티에이전트 작업 보존). SSH 키 등록. (updated 2026-06-08)
- **`.gitignore`**: `.env`·`cache/`·`output/`·`raw_data/*.xlsx`(~90MB)·`__pycache__` 제외. 소스·`state/trend_history.json`·`template/base` 는 추적. (updated 2026-06-08)

---

## 알려진 한계 / TODO
- **외부 데이터 미구현**(플레이스홀더 유지): MX Gen AI Traffic(Adobe)·Gen AI Platform Traffic(Similarweb).
- **수기 주석 보류**(5엑셀 집계 범위 밖): 슬12 직사각형40(영어권 Reddit %p), 슬21(ES) TextBox131(인텐트 BV%).
- **미매핑 오버레이 3건**: 슬9 직사각형91, 슬20(FR) 200, 슬27(JP) 210 — 차트 bbox 경계 밖이라 보류(패딩 조정 시 정상 11개국 깨질 위험).
- **Co.A 인용/RV 대기**: 2-1-1·2-2 가 현재 Samsung-only → Co.A 값은 실데이터에 Apple 들어오면 자동 표시(코드는 준비됨).
- raw 가 테스트 데이터라 일부 값은 AX 실데이터와 다름(계산식은 동일).
