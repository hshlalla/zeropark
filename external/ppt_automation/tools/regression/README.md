# regression — 값(숫자) 회귀 안전망  ⚠️ 지우지 말 것

리포트에 들어가는 **숫자/집계/표시 포맷이 바뀌면 실패**하도록 잠그는 회귀 검사.
**코드를 수정할 때 "숫자 안 깨졌나"를 자동으로 보증**하는 안전장치다(그래서 'tests' 가 아니라
'regression' — 지우면 안 됨). LLM 인사이트 텍스트는 비결정적이라 **대상이 아니다** — 오직 값.

표준 라이브러리 `unittest` 만 사용(추가 의존성 없음).

## 실행 (저장소 루트에서)

```bash
python -m unittest discover -s tools/regression -t .        # 빠른 검사만(<1초). 골든은 기본 skip
python -m unittest discover -s tools/regression -t . -v     # 자세히
RUN_GOLDEN=1 python -m unittest discover -s tools/regression -t .   # 느린 골든 회귀(수 분)
```

(Windows PowerShell: `$env:RUN_GOLDEN=1; python -m unittest discover -s tools/regression -t .`)

루트에서 실행해야 `geo_report` 가 import 된다.

## 구성

| 파일 | 종류 | 데이터 의존 | 내용 |
|---|---|---|---|
| `test_formatters.py` | 순수 단위 | 없음 | 집계값→표시문자열(`fmt_pct/fmt_mom/fmt_kval/fmt_ratio/mom/frac`) 규칙 고정 |
| `test_ranking.py` | 순수 단위 | 없음(합성 df) | 도메인 **경쟁식 순위**(`_top_domains_prev`) 동점/합산/필터 |
| `test_kpi_golden.py` | characterization | `data/*.xlsx` + `RUN_GOLDEN=1` | raw 에서 **재계산**해 대표 KPI 값을 정답지에 고정. 기본 skip(느림) |

## 골든 테스트(test_kpi_golden) 메모

- **캐시를 우회**해 raw 엑셀에서 집계를 다시 계산한다 → 집계 로직이 바뀌어 값이
  달라지면 즉시 실패. 느리다(수 분, iterrows 100k행) → `RUN_GOLDEN=1` 일 때만 실행.
- 값을 의도적으로 바꿨다면(데이터 갱신 등) 이 파일의 기대값을 함께 갱신한다.
- 고정된 대표값: 기준월(26-04/26-03·자동감지), Global BV 76.8%/RV 46.4%/Sentiment 95.5%/
  RS Owned 12.5%·External 87.5%/Owned 인용 84,104, 국가값(US 80.4%·KR 83.4%·JP RV 47.2%) 등.

## 범위 밖(의도적으로 테스트 안 함)

- LLM 인사이트 문구(비결정적, temperature 0.4)
- 템플릿 도형 좌표/번호 매칭(별도 validation 레이어 과제)
