#!/bin/bash
#
# Docker 컨테이너 중지 스크립트
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Trading Bot - Docker 컨테이너 중지${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")/.."

# 중지 옵션
REMOVE=""
if [ "$1" == "--remove" ] || [ "$1" == "-r" ]; then
    REMOVE="--volumes"
    echo -e "${YELLOW}컨테이너와 볼륨을 모두 제거합니다...${NC}"
else
    echo -e "${YELLOW}컨테이너를 중지합니다...${NC}"
fi

docker-compose down $REMOVE

if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}✅ 컨테이너 중지 완료!${NC}"

    if [ -n "$REMOVE" ]; then
        echo
        echo -e "${YELLOW}⚠️  볼륨이 제거되었습니다.${NC}"
        echo -e "   데이터가 초기화되었습니다."
    else
        echo
        echo -e "${YELLOW}데이터는 보존되었습니다.${NC}"
        echo -e "  data/, logs/ 디렉토리의 내용은 그대로 유지됩니다."
        echo
        echo -e "${YELLOW}볼륨까지 제거하려면:${NC}"
        echo -e "  ${GREEN}./scripts/docker-stop.sh --remove${NC}"
    fi
else
    echo
    echo -e "${RED}❌ 컨테이너 중지 실패!${NC}"
    exit 1
fi
