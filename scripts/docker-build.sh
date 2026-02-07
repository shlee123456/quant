#!/bin/bash
#
# Docker 이미지 빌드 스크립트
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Trading Bot - Docker 이미지 빌드${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")/.."

# 빌드 옵션
NO_CACHE=""
if [ "$1" == "--no-cache" ]; then
    NO_CACHE="--no-cache"
    echo -e "${YELLOW}캐시 없이 빌드합니다...${NC}"
fi

# Docker BuildKit 활성화 (빌드 성능 향상)
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo -e "${YELLOW}Docker 이미지를 빌드합니다...${NC}"
docker-compose build $NO_CACHE

if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}✅ Docker 이미지 빌드 완료!${NC}"
    echo
    echo -e "이미지 정보:"
    docker images trading-bot:latest
    echo
    echo -e "${YELLOW}다음 단계:${NC}"
    echo -e "  실행: ${GREEN}./scripts/docker-run.sh${NC}"
    echo -e "  또는: ${GREEN}docker-compose up -d${NC}"
else
    echo
    echo -e "${RED}❌ Docker 이미지 빌드 실패!${NC}"
    exit 1
fi
