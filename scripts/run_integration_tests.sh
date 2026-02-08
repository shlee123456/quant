#!/bin/bash

###############################################################################
# 통합 테스트 스크립트
#
# 백테스팅, 최적화, 전략 비교, 대시보드 로드 테스트를 자동으로 실행합니다.
# 각 테스트 결과는 .context/terminal/에 로그로 저장됩니다.
###############################################################################

set -e  # Exit on error

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Create log directory
TIMESTAMP=$(date +%s)
LOG_DIR=".context/terminal"
mkdir -p "$LOG_DIR"

# Log file for summary
SUMMARY_LOG="$LOG_DIR/integration_test_summary_${TIMESTAMP}.log"

echo "=========================================================================="
echo "  Crypto Trading Bot - 통합 테스트 실행"
echo "=========================================================================="
echo "시작 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "로그 디렉토리: $LOG_DIR"
echo ""

# Function to run a test and log results
run_test() {
    local test_name="$1"
    local test_command="$2"
    local log_file="$3"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))

    echo -e "${BLUE}[테스트 $TESTS_TOTAL]${NC} $test_name"
    echo "명령어: $test_command"
    echo "로그: $log_file"

    if eval "$test_command" 2>&1 | tee "$log_file"; then
        echo -e "${GREEN}✓ 성공${NC}"
        echo ""
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo "[PASS] $test_name" >> "$SUMMARY_LOG"
        return 0
    else
        echo -e "${RED}✗ 실패${NC}"
        echo ""
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "[FAIL] $test_name" >> "$SUMMARY_LOG"
        return 1
    fi
}

echo "=========================================================================="
echo "  1. 백테스팅 테스트"
echo "=========================================================================="
run_test \
    "백테스팅 예제 실행" \
    "python examples/run_backtest_example.py" \
    "$LOG_DIR/integration_backtest_${TIMESTAMP}.log" || true

echo "=========================================================================="
echo "  2. 전략 최적화 테스트"
echo "=========================================================================="
run_test \
    "전략 최적화 실행" \
    "python examples/strategy_optimization.py" \
    "$LOG_DIR/integration_optimization_${TIMESTAMP}.log" || true

echo "=========================================================================="
echo "  3. 전략 비교 테스트"
echo "=========================================================================="
run_test \
    "전략 비교 실행" \
    "python examples/strategy_comparison.py" \
    "$LOG_DIR/integration_comparison_${TIMESTAMP}.log" || true

echo "=========================================================================="
echo "  4. 대시보드 로드 테스트"
echo "=========================================================================="
run_test \
    "대시보드 기능 테스트" \
    "python examples/test_dashboard.py" \
    "$LOG_DIR/integration_dashboard_${TIMESTAMP}.log" || true

echo "=========================================================================="
echo "  5. QuickStart 테스트"
echo "=========================================================================="
run_test \
    "QuickStart 스크립트 실행" \
    "python examples/quickstart.py" \
    "$LOG_DIR/integration_quickstart_${TIMESTAMP}.log" || true

echo "=========================================================================="
echo "  테스트 결과 요약"
echo "=========================================================================="
echo ""
echo -e "전체 테스트 수: ${BLUE}$TESTS_TOTAL${NC}"
echo -e "성공: ${GREEN}$TESTS_PASSED${NC}"
echo -e "실패: ${RED}$TESTS_FAILED${NC}"
echo ""

# Print summary from log
if [ -f "$SUMMARY_LOG" ]; then
    echo "상세 결과:"
    echo "--------------------------------------------------------------------------"
    cat "$SUMMARY_LOG"
    echo "--------------------------------------------------------------------------"
fi

echo ""
echo "종료 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "전체 요약 로그: $SUMMARY_LOG"
echo ""

# Exit with error if any test failed
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}일부 테스트가 실패했습니다.${NC}"
    echo "실패한 테스트의 로그를 확인하세요: $LOG_DIR"
    exit 1
else
    echo -e "${GREEN}모든 테스트가 성공했습니다! 🎉${NC}"
    exit 0
fi
