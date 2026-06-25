# Calculator Skills

## Skill 1: 완전성 보장 (★ 최우선)

요청된 모든 KPI 키가 results dict에 포함되어야 한다.

```python
# 계산 후 누락 키 확인
missing = [k for k in required_keys if results.get(k) is None]
# 누락이 있으면 명시적으로 None 할당 (조용한 누락 금지)
for k in missing:
    results[k] = None
```

**허용 기준: 모든 요청 키가 results에 존재 (값이 None이어도 키는 있어야 함)**

---

## Skill 2: 오류 격리 (개별 KPI 실패가 전체를 중단시키지 않도록)

```python
try:
    denom = df["denominator"].sum()
    results["bv_samsung_global_cur"] = float(df["galaxy_mention"].sum()) / denom * 100 if denom != 0 else None
except Exception:
    results["bv_samsung_global_cur"] = None
```

---

## Skill 3: DataFrame 재사용 (효율)

같은 df_key + date 조합은 한 번만 로드해 재사용한다.

```python
# 비효율 (금지)
cur = pd.read_parquet(os.path.join(data_dir, "bv.parquet"))
cur = cur[cur["date"] == cur_date]
for key in bv_keys:
    ...  # 매번 reload

# 효율 (권장)
bv = pd.read_parquet(os.path.join(data_dir, "bv.parquet"))
bv["date"] = pd.to_datetime(bv["date"]).dt.strftime("%Y-%m-%d")
bv_cur = bv[bv["date"] == cur_date]
bv_prv = bv[bv["date"] == prv_date]
```

---

## Skill 4: MoM/Ratio 파생 패턴

`_cur` 계산과 동일한 필터로 `_prv`를 계산하고 차이/비율을 구한다.

```python
def _bv_samsung(df, country=None):
    d = df[df["company"] == "Samsung"]
    if country:
        d = d[d["country"] == country]
    denom = d["denominator"].sum()
    return float(d["galaxy_mention"].sum()) / denom * 100 if denom != 0 else None

# cur / mom / ratio를 한 번에 처리
cur_val = _bv_samsung(bv_cur, country="US")
prv_val = _bv_samsung(bv_prv, country="US")
results["bv_samsung_us_cur"]   = cur_val
results["bv_samsung_us_mom"]   = cur_val - prv_val if cur_val is not None and prv_val is not None else None
results["bv_samsung_us_ratio"] = cur_val / prv_val if cur_val is not None and prv_val is not None and prv_val != 0 else None
```

---

## Skill 5: Coverage Report (계산 완료 후 출력)

```python
required = len(required_keys)
calculated = sum(1 for k in required_keys if results.get(k) is not None)
missing = [k for k in required_keys if results.get(k) is None]
# 예시 출력: required=248, calculated=245, missing=['key1', ...]
```

---

## Never

- 계산 불가 KPI를 조용히 누락시키지 말 것 — `None`이라도 results에 포함
- 같은 KPI family에서 다른 필터/컬럼을 사용하지 말 것 (family 일관성)
- `bv_mx_*` 키에 bv.parquet 사용 금지 — 반드시 rv.parquet
- `_ratio` KPI에서 prv_val == 0 방지 처리 누락 금지
