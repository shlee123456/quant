#!/bin/bash
#
# 일일 시장 분석 파이프라인 (올인원)
#
# 시장분석(Docker) → 노션 작성(호스트) → Pine Script + Slack(호스트)
#
# Usage:
#   ./scripts/run_daily_pipeline.sh
#   ./scripts/run_daily_pipeline.sh --skip-notion
#   ./scripts/run_daily_pipeline.sh --skip-pine
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 옵션 파싱
SKIP_NOTION=false
SKIP_PINE=false
for arg in "$@"; do
    case "$arg" in
        --skip-notion) SKIP_NOTION=true ;;
        --skip-pine)   SKIP_PINE=true ;;
        --help|-h)
            echo "Usage: $0 [--skip-notion] [--skip-pine]"
            echo "  --skip-notion  노션 작성 스킵"
            echo "  --skip-pine    Pine Script 스킵"
            exit 0
            ;;
    esac
done

TODAY=$(date +%Y-%m-%d)
LOG_FILE="logs/daily_pipeline_${TODAY}.log"
mkdir -p logs

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" | tee -a "$LOG_FILE"; }

log "INFO" "=========================================="
log "INFO" "일일 파이프라인 시작 ($TODAY)"
log "INFO" "=========================================="

ANALYSIS_OK=false
NOTION_OK=false
PINE_OK=false

# ── Step 1: 시장 분석 (Docker) ─────────────────────────────────────

log "INFO" "Step 1: 시장 분석 (Docker)"

docker compose build --quiet 2>>"$LOG_FILE"

if docker compose run --rm trading-bot-scheduler \
    python scripts/run_market_analysis.py --skip-notion \
    2>&1 | tee -a "$LOG_FILE"; then
    ANALYSIS_OK=true
    log "INFO" "Step 1: 시장 분석 완료"
else
    log "ERROR" "Step 1: 시장 분석 실패. 파이프라인 중단."
    exit 1
fi

# JSON 파일 확인
JSON_FILE=$(ls -t data/market_analysis/${TODAY}*.json 2>/dev/null | head -1)
if [ -z "$JSON_FILE" ]; then
    log "ERROR" "JSON 파일을 찾을 수 없습니다: data/market_analysis/${TODAY}*.json"
    exit 1
fi
log "INFO" "JSON: $JSON_FILE"

# ── Step 2: 노션 작성 (호스트) ─────────────────────────────────────

if [ "$SKIP_NOTION" = true ]; then
    log "INFO" "Step 2: 노션 작성 스킵 (--skip-notion)"
else
    log "INFO" "Step 2: 노션 작성"

    set +e  # 일시적으로 errexit 해제 (exit code 구분 필요)
    python scripts/notion_writer.py 2>&1 | tee -a "$LOG_FILE"
    NOTION_EXIT=${PIPESTATUS[0]}  # python 프로세스의 exit code (tee가 아닌)
    set -e

    if [ "$NOTION_EXIT" -eq 0 ]; then
        NOTION_OK=true
        log "INFO" "Step 2: 노션 작성 완료"
    elif [ "$NOTION_EXIT" -eq 2 ]; then
        log "WARN" "Step 2: 노션 작성 스킵 (이미 완료 또는 JSON 없음)"
    else
        log "ERROR" "Step 2: 노션 작성 실패 (exit code=$NOTION_EXIT)"
    fi
fi

# ── Step 3: Pine Script + Slack (호스트) ───────────────────────────

if [ "$SKIP_PINE" = true ]; then
    log "INFO" "Step 3: Pine Script 스킵 (--skip-pine)"
else
    log "INFO" "Step 3: Pine Script + Slack"

    if python scripts/generate_pine_script.py --date "$TODAY" --slack \
        2>&1 | tee -a "$LOG_FILE"; then
        PINE_OK=true
        log "INFO" "Step 3: Pine Script 완료"
    else
        log "ERROR" "Step 3: Pine Script 실패"
    fi
fi

# ── 결과 요약 ──────────────────────────────────────────────────────

log "INFO" "=========================================="
log "INFO" "파이프라인 결과"
log "INFO" "  시장분석: $( [ "$ANALYSIS_OK" = true ] && echo '✅' || echo '❌' )"
if [ "$SKIP_NOTION" = true ]; then
    log "INFO" "  노션작성: ⏭️  스킵"
elif [ "${NOTION_EXIT:-1}" -eq 2 ]; then
    log "WARN" "  노션작성: ⚠️  스킵 (이미 완료 또는 JSON 없음)"
else
    log "INFO" "  노션작성: $( [ "$NOTION_OK" = true ] && echo '✅' || echo '❌' )"
fi
if [ "$SKIP_PINE" = true ]; then
    log "INFO" "  Pine+Slack: ⏭️  스킵"
else
    log "INFO" "  Pine+Slack: $( [ "$PINE_OK" = true ] && echo '✅' || echo '❌' )"
fi
log "INFO" "=========================================="
