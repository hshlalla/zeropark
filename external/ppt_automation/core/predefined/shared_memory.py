"""shared_memory.py — 에이전트 공유 메모리 레이어 (SQLite, 의존성 없음).

목적: 에이전트가 매번 새로 추론해 같은 실수를 반복하지 않게 한다.
- metric_catalog    : 검증된 공식 + confidence/evidence (재사용)
- shape_registry    : 도형 역할/연결 metric (Reader 재스캔 절감)
- formula_attempts  : 시도한 후보·결과 (실패 후보 재시도 방지)
- validation_events : 검증 실패 이력 (root_cause/다음 담당)
- agent_messages    : 에이전트 간 요약 메시지 (artifact 참조)

DB 위치: generated/memory.db (런마다 유지 → 다음 달 실행 시 학습 재사용)
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from agents.utils import GENERATED_DIR

_DEFAULT_DB = os.path.join(GENERATED_DIR, "memory.db")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SharedMemory:
    def __init__(self, db_path: str = _DEFAULT_DB):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS metric_catalog(
                    metric_id TEXT PRIMARY KEY,
                    metric_family TEXT, formula TEXT,
                    confidence REAL, evidence TEXT, last_validated_at TEXT);

                CREATE TABLE IF NOT EXISTS shape_registry(
                    slide_idx INTEGER, shape_id INTEGER,
                    shape_type TEXT, role TEXT, linked_metric_id TEXT,
                    PRIMARY KEY(slide_idx, shape_id));

                CREATE TABLE IF NOT EXISTS formula_attempts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT, candidate_formula TEXT,
                    computed_value REAL, expected_value REAL, error REAL,
                    status TEXT, reason TEXT, ts TEXT);

                CREATE TABLE IF NOT EXISTS validation_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT, expected TEXT, actual TEXT,
                    root_cause TEXT, next_agent TEXT, ts TEXT);

                CREATE TABLE IF NOT EXISTS agent_messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT, to_agent TEXT,
                    summary TEXT, artifact_refs TEXT, ts TEXT);

                CREATE INDEX IF NOT EXISTS ix_attempts_key ON formula_attempts(key);
                CREATE INDEX IF NOT EXISTS ix_valid_key ON validation_events(key);
                """
            )

    # ── metric_catalog ────────────────────────────────────────────────
    def upsert_metric(self, metric_id, metric_family, formula, confidence, evidence=""):
        with self._conn() as c:
            c.execute(
                """INSERT INTO metric_catalog(metric_id, metric_family, formula, confidence, evidence, last_validated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(metric_id) DO UPDATE SET
                     metric_family=excluded.metric_family, formula=excluded.formula,
                     confidence=excluded.confidence, evidence=excluded.evidence,
                     last_validated_at=excluded.last_validated_at""",
                (metric_id, metric_family, json.dumps(formula, ensure_ascii=False)
                 if not isinstance(formula, str) else formula,
                 float(confidence), evidence, _now()),
            )

    def upsert_metrics_bulk(self, rows: list[tuple]):
        """rows = [(metric_id, family, formula(dict|str), confidence, evidence), ...] — 1트랜잭션."""
        if not rows:
            return
        ts = _now()
        data = [(mid, fam,
                 json.dumps(f, ensure_ascii=False) if not isinstance(f, str) else f,
                 float(conf), ev, ts)
                for (mid, fam, f, conf, ev) in rows]
        with self._conn() as c:
            c.executemany(
                """INSERT INTO metric_catalog(metric_id, metric_family, formula, confidence, evidence, last_validated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(metric_id) DO UPDATE SET
                     metric_family=excluded.metric_family, formula=excluded.formula,
                     confidence=excluded.confidence, evidence=excluded.evidence,
                     last_validated_at=excluded.last_validated_at""", data)

    def log_attempts_bulk(self, rows: list[tuple]):
        """rows = [(key, candidate(dict|str), computed, expected, error, status, reason), ...]."""
        if not rows:
            return
        ts = _now()
        data = [(k,
                 json.dumps(cf, ensure_ascii=False) if not isinstance(cf, str) else cf,
                 _none_float(cv), _none_float(ev), _none_float(er), st, rs, ts)
                for (k, cf, cv, ev, er, st, rs) in rows]
        with self._conn() as c:
            c.executemany(
                """INSERT INTO formula_attempts(key, candidate_formula, computed_value, expected_value, error, status, reason, ts)
                   VALUES(?,?,?,?,?,?,?,?)""", data)

    def get_metric(self, metric_id) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM metric_catalog WHERE metric_id=?", (metric_id,)).fetchone()
            return dict(r) if r else None

    def validated_formula(self, metric_id, min_conf=0.8) -> dict | None:
        """이미 검증된(고신뢰) 공식이 있으면 반환 → 재합성 생략."""
        m = self.get_metric(metric_id)
        if m and m["confidence"] >= min_conf and m["formula"]:
            try:
                return json.loads(m["formula"])
            except Exception:
                return None
        return None

    # ── shape_registry ────────────────────────────────────────────────
    def register_shape(self, slide_idx, shape_id, shape_type, role, linked_metric_id=""):
        with self._conn() as c:
            c.execute(
                """INSERT INTO shape_registry(slide_idx, shape_id, shape_type, role, linked_metric_id)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(slide_idx, shape_id) DO UPDATE SET
                     shape_type=excluded.shape_type, role=excluded.role,
                     linked_metric_id=excluded.linked_metric_id""",
                (slide_idx, shape_id, shape_type, role, linked_metric_id),
            )

    def register_shapes_bulk(self, rows: list[tuple]):
        """rows = [(slide_idx, shape_id, shape_type, role, linked_metric_id), ...]."""
        rows = [r for r in rows if r[1] is not None]   # shape_id 없는 건 제외
        if not rows:
            return
        with self._conn() as c:
            c.executemany(
                """INSERT INTO shape_registry(slide_idx, shape_id, shape_type, role, linked_metric_id)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(slide_idx, shape_id) DO UPDATE SET
                     shape_type=excluded.shape_type, role=excluded.role,
                     linked_metric_id=excluded.linked_metric_id""", rows)

    # ── formula_attempts ──────────────────────────────────────────────
    def log_attempt(self, key, candidate_formula, computed_value, expected_value, error, status, reason=""):
        with self._conn() as c:
            c.execute(
                """INSERT INTO formula_attempts(key, candidate_formula, computed_value, expected_value, error, status, reason, ts)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (key, json.dumps(candidate_formula, ensure_ascii=False)
                 if not isinstance(candidate_formula, str) else candidate_formula,
                 _none_float(computed_value), _none_float(expected_value), _none_float(error),
                 status, reason, _now()),
            )

    def rejected_signatures(self, key) -> set:
        """이전에 reject된 후보 시그니처(분자|분모|scale) — 재시도 방지용."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT candidate_formula FROM formula_attempts WHERE key=? AND status='rejected'",
                (key,)).fetchall()
        out = set()
        for r in rows:
            try:
                d = json.loads(r["candidate_formula"])
                out.add(f"{d.get('num')}|{d.get('denom')}|{d.get('scale')}")
            except Exception:
                pass
        return out

    # ── validation_events ─────────────────────────────────────────────
    def log_validation(self, key, expected, actual, root_cause, next_agent):
        with self._conn() as c:
            c.execute(
                """INSERT INTO validation_events(key, expected, actual, root_cause, next_agent, ts)
                   VALUES(?,?,?,?,?,?)""",
                (key, str(expected), str(actual), root_cause, next_agent, _now()),
            )

    def log_validations_bulk(self, rows: list[tuple]):
        """rows = [(key, expected, actual, root_cause, next_agent), ...]."""
        if not rows:
            return
        ts = _now()
        data = [(k, str(e), str(a), rc, na, ts) for (k, e, a, rc, na) in rows]
        with self._conn() as c:
            c.executemany(
                """INSERT INTO validation_events(key, expected, actual, root_cause, next_agent, ts)
                   VALUES(?,?,?,?,?,?)""", data)

    # ── agent_messages ────────────────────────────────────────────────
    def log_message(self, from_agent, to_agent, summary, artifact_refs=None):
        with self._conn() as c:
            c.execute(
                """INSERT INTO agent_messages(from_agent, to_agent, summary, artifact_refs, ts)
                   VALUES(?,?,?,?,?)""",
                (from_agent, to_agent, summary,
                 json.dumps(artifact_refs or [], ensure_ascii=False), _now()),
            )

    def stats(self) -> dict:
        with self._conn() as c:
            def n(t):
                return c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            return {t: n(t) for t in
                    ("metric_catalog", "shape_registry", "formula_attempts",
                     "validation_events", "agent_messages")}


def _none_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# 싱글톤 (파이프라인 내 공유)
_mem: SharedMemory | None = None


def get_memory() -> SharedMemory:
    global _mem
    if _mem is None:
        _mem = SharedMemory()
    return _mem
