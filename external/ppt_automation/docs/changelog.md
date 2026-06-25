6.0.0
- 멀티 에이전트 파이프라인 추가 (geo_report/agents/): LangGraph StateGraph 기반 5단계 자동화
  - TemplateAnalyzerAgent: 새 PPTX 도형 인벤토리 추출 (결정론적)
  - FormulaBuilderAgent: LLM이 도형 → 집계 계산식 매핑 (fill_plan 생성)
  - ValueFillerAgent: fill_plan 실행 → 실제 값 계산 & PPT 삽입
  - ValidatorAgent: 삽입값 vs 기대값 비교, 불일치 리포트
  - CorrectorAgent: 검증 실패 항목을 LLM이 수식 수정 (최대 3회 루프)
- run_agents.py: 멀티 에이전트 파이프라인 CLI 진입점 추가
- requirements.txt: LangChain/LangGraph 의존성 명시
- .venv: Python 가상환경 추가

5.4.0
- 슬7·8 국가 뷰에 권역 그룹(영어권/유럽권/기타) 평균 제공 → '영어권 5개국 평균 -1.0%p' 식 서술 가능

5.3.0
- 슬7·8 인사이트에 크로스 뷰(국가×플랫폼/국가×인텐트/플랫폼×인텐트) 변동 원인 분석 추가

5.2.0
- 슬7·8 인사이트 메시지 고정 뷰: 1=트렌드 / 2=국가 / 3=인텐트 / 4=플랫폼

5.1.0
- 빌드 진입점 통일: build_performance.py 제거, build_report.py 하나로 (--month/--raw-dir/--cache/--no-llm)

5.0.0
- 성과 슬라이드 메시지별 뷰 고정 재설계: 슬7~8=4뷰(트렌드/국가/인텐트/플랫폼)·슬9~13=5뷰(+채널), RV/RS 인텐트·플랫폼 집계 신규, 메시지 슬롯 자동 추가(ensure_insight_slots), 뷰별 프롬프트(VIEW_RULES) 주입

4.2.0
- 성과 슬라이드7~13 인사이트를 메시지 슬롯별 고정 뷰로 생성하도록 collect_jobs 연결 + FIXED_VIEW_RULE 주입 (랜덤 뷰 제거, 슬롯별 뷰 컨텍스트+크로스 분해 주입)

4.1.0
- 인사이트 뷰 빌더 추가: 메시지 슬롯별 고정 분석 뷰(트렌드/국가/인텐트·채널/플랫폼) + 크로스 분석(국가×인텐트/국가×플랫폼/국가×채널). 지표별 차원 자동 선택. (collect_jobs 연결은 다음 단계)

4.0.0
- 거버닝 프롬프트 anti-pattern 추가: 시사점·액션 언급 자제 + MX(Owned)↔External 장표 간 주제 교차 생성 금지

3.0.1
- 슬3 BP(Best Practice) fewshot 예시를 액션형 → 현황·요약형으로 수정(액션 처방 제거)

3.0.0
- 거버닝 메시지에서 '시사점/향후 액션' 생성 지시 제거(Performance Breakdown 룰 + SLIDE3_BP_RULE) — 현황·원인 중심으로

2.0.0
- 요약 슬라이드(03·04·05) 표/KPI 값을 4월 이하는 AX 영역체크 파일 값으로 고정(5월부터 raw, MoM도 4월=AX 기준)

1.2.0
- 슬라이드 03·04·05 인사이트를 성과 상세(7~13) 요약으로 생성하도록 빌드 인사이트 대상에 포함

1.1.0
- 슬라이드 03(Monthly Summary)·04(Highlight)·05(Appendix) 값 자동 채우기를 빌드에 연결

1.0.2
- Governing Message few-shot 방식 변경(각 슬라이드마다 다른 few-shot 적용)

0.0.1
- init 초기 release push

=========================================build_report.py versions 함께 변경할것=============================
