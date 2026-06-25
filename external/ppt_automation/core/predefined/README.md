# core/predefined/

**템플릿/데이터와 무관한 범용 엔진·도구.** 손으로 한 번 정의해두면 어떤 템플릿이
들어와도 그대로 재사용된다. 템플릿 특화 지식이 들어가면 안 된다(0 도메인 참조 유지).

| 파일 | 역할 |
|------|------|
| `pptx_scanner.py`      | PPT 스캔/읽기/쓰기 (JSON 캐시) |
| `excel_reader.py`      | 원시 Excel 로드·스키마 추출 |
| `formula_engine.py`    | KeySpec 해석·실행 (scale/period는 주입받는 파라미터) |
| `formula_validator.py` | 후보 공식 계산·채점 (scale은 candidate가 지정) |
| `shared_memory.py`     | 누적 학습 공유메모리(SQLite) |

> **판별 기준**: scale·단위·표시문자열·컬럼명을 *하드코딩*하면 특화(`agent_generated`),
> *파라미터로 주입*받으면 범용. 예) `formula_engine`은 `spec.scale`을 곱할 뿐 값을 모름 → 범용.
> `formatters`(`%`,`K`,`%p` 하드코딩)·`formula_synthesizer`(fmt→scale 매핑 하드코딩)는 특화.
>
> 템플릿 특화 로직과 에이전트 런타임 산출물은 `core/agent_generated/` 에 있다.
