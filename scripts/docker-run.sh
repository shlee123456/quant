#!/bin/bash
#
# Docker 컨테이너 실행 스크립트
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Trading Bot - Docker 컨테이너 실행${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")/.."

# .env 파일 확인
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env 파일이 없습니다!${NC}"
    echo
    echo -e "${YELLOW}다음 단계를 수행하세요:${NC}"
    echo -e "  1. cp .env.example .env"
    echo -e "  2. .env 파일을 편집하여 API 키를 입력하세요"
    exit 1
fi

# 디렉토리 생성
mkdir -p data logs config

# 실행 모드 선택
MODE=${1:-dashboard}

case $MODE in
    dashboard)
        echo -e "${YELLOW}Dashboard 모드로 실행합니다...${NC}"
        echo -e "${BLUE}접속 URL: http://localhost:8501${NC}"
        docker-compose up -d
        ;;

    backtester)
        echo -e "${YELLOW}Backtester 모드로 실행합니다...${NC}"
        docker-compose run --rm trading-bot python examples/run_backtest_example.py
        ;;

    optimizer)
        echo -e "${YELLOW}Optimizer 모드로 실행합니다...${NC}"
        docker-compose run --rm trading-bot python examples/optimize_strategy.py
        ;;

    shell)
        echo -e "${YELLOW}Interactive Shell 모드로 실행합니다...${NC}"
        docker-compose run --rm trading-bot bash
        ;;

    *)
        echo -e "${RED}알 수 없는 모드: $MODE${NC}"
        echo
        echo -e "${YELLOW}사용법:${NC}"
        echo -e "  ./scripts/docker-run.sh [mode]"
        echo
        echo -e "${YELLOW}사용 가능한 모드:${NC}"
        echo -e "  ${GREEN}dashboard${NC}   - Streamlit 대시보드 (기본)"
        echo -e "  ${GREEN}backtester${NC}  - 백테스트 실행"
        echo -e "  ${GREEN}optimizer${NC}   - 전략 최적화"
        echo -e "  ${GREEN}shell${NC}       - 컨테이너 쉘 접속"
        exit 1
        ;;
esac

if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}✅ 컨테이너 실행 완료!${NC}"

    if [ "$MODE" == "dashboard" ]; then
        echo
        echo -e "${YELLOW}대시보드 확인:${NC}"
        echo -e "  URL: ${BLUE}http://localhost:8501${NC}"
        echo
        echo -e "${YELLOW}로그 확인:${NC}"
        echo -e "  ${GREEN}./scripts/docker-logs.sh${NC}"
        echo
        echo -e "${YELLOW}중지:${NC}"
        echo -e "  ${GREEN}./scripts/docker-stop.sh${NC}"
    fi
else
    echo
    echo -e "${RED}❌ 컨테이너 실행 실패!${NC}"
    exit 1
fi
