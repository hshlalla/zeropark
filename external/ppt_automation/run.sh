#!/bin/bash
# run.sh — MX GEO Monitoring Report 한방 실행
#
# 사용법:
#   ./run.sh                                   # 기본 (자동 감지)
#   ./run.sh --month 2026-04                   # 특정 월
#   ./run.sh --regenerate                      # 코드 강제 재생성
#   ./run.sh --answer-key answer_key/정답.pptx # 정답지 직접 지정
#
# 환경변수:
#   SKIP_DEPS=1   의존성 설치 건너뜀

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. 가상환경 ──────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "· 가상환경 생성 중..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# ── 2. 의존성 ─────────────────────────────────────────────────────────────────
if [ "${SKIP_DEPS}" != "1" ]; then
    pip install -q --disable-pip-version-check -r requirements.txt
fi

# ── 3. 실행 ──────────────────────────────────────────────────────────────────
echo "· 에이전트 파이프라인 시작..."
python build_report.py "$@"
