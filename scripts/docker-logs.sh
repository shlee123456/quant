#!/bin/bash
#
# Docker 컨테이너 로그 확인 스크립트
#

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Trading Bot - Docker 로그 확인${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")/.."

# 로그 옵션
FOLLOW=""
TAIL="100"

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW="--follow"
            shift
            ;;
        -n|--tail)
            TAIL="$2"
            shift 2
            ;;
        *)
            echo -e "${YELLOW}사용법:${NC}"
            echo -e "  ./scripts/docker-logs.sh [options]"
            echo
            echo -e "${YELLOW}옵션:${NC}"
            echo -e "  ${GREEN}-f, --follow${NC}     실시간 로그 추적"
            echo -e "  ${GREEN}-n, --tail N${NC}     최근 N줄 표시 (기본: 100)"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}로그를 확인합니다...${NC}"
echo

if [ -n "$FOLLOW" ]; then
    echo -e "${YELLOW}실시간 로그 추적 중... (Ctrl+C로 종료)${NC}"
    docker-compose logs --tail=$TAIL $FOLLOW
else
    docker-compose logs --tail=$TAIL
fi
