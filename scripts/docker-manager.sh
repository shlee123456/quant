#!/bin/bash
# Docker 컨테이너 관리 스크립트

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 로그 디렉토리 생성
mkdir -p .context/terminal

# 로그 파일 경로
LOG_FILE=".context/terminal/docker_$(date +%s).log"

# 로그 함수
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# 사용법
usage() {
    cat << EOF
Docker 컨테이너 관리 스크립트

사용법:
    $0 [command]

명령어:
    build       - Docker 이미지 빌드
    start       - 모든 컨테이너 시작 (대시보드 + 스케줄러)
    stop        - 모든 컨테이너 중지
    restart     - 모든 컨테이너 재시작
    logs        - 컨테이너 로그 확인
    status      - 컨테이너 상태 확인
    clean       - 중지된 컨테이너 및 unused 이미지 제거

    start-dashboard   - 대시보드만 시작
    start-scheduler   - 스케줄러만 시작
    stop-dashboard    - 대시보드만 중지
    stop-scheduler    - 스케줄러만 중지

    logs-dashboard    - 대시보드 로그 확인
    logs-scheduler    - 스케줄러 로그 확인

예시:
    $0 build          # 이미지 빌드
    $0 start          # 모든 서비스 시작
    $0 logs-scheduler # 스케줄러 로그 확인

EOF
}

# 빌드
build() {
    log "Docker 이미지 빌드 중..."
    docker-compose build 2>&1 | tee -a "$LOG_FILE"
    log "✓ 빌드 완료"
}

# 시작
start() {
    log "모든 컨테이너 시작 중..."
    docker-compose up -d 2>&1 | tee -a "$LOG_FILE"
    log "✓ 컨테이너 시작 완료"
    log "대시보드: http://localhost:8501"
    log "스케줄러: docker logs -f trading-bot-scheduler"
}

start_dashboard() {
    log "대시보드 컨테이너 시작 중..."
    docker-compose up -d trading-bot-dashboard 2>&1 | tee -a "$LOG_FILE"
    log "✓ 대시보드 시작 완료: http://localhost:8501"
}

start_scheduler() {
    log "스케줄러 컨테이너 시작 중..."
    docker-compose up -d trading-bot-scheduler 2>&1 | tee -a "$LOG_FILE"
    log "✓ 스케줄러 시작 완료"
}

# 중지
stop() {
    log "모든 컨테이너 중지 중..."
    docker-compose down 2>&1 | tee -a "$LOG_FILE"
    log "✓ 컨테이너 중지 완료"
}

stop_dashboard() {
    log "대시보드 컨테이너 중지 중..."
    docker-compose stop trading-bot-dashboard 2>&1 | tee -a "$LOG_FILE"
    log "✓ 대시보드 중지 완료"
}

stop_scheduler() {
    log "스케줄러 컨테이너 중지 중..."
    docker-compose stop trading-bot-scheduler 2>&1 | tee -a "$LOG_FILE"
    log "✓ 스케줄러 중지 완료"
}

# 재시작
restart() {
    log "모든 컨테이너 재시작 중..."
    docker-compose restart 2>&1 | tee -a "$LOG_FILE"
    log "✓ 컨테이너 재시작 완료"
}

# 로그 확인
logs() {
    log "컨테이너 로그 확인 (Ctrl+C로 종료)..."
    docker-compose logs -f 2>&1 | tee -a "$LOG_FILE"
}

logs_dashboard() {
    log "대시보드 로그 확인 (Ctrl+C로 종료)..."
    docker-compose logs -f trading-bot-dashboard 2>&1 | tee -a "$LOG_FILE"
}

logs_scheduler() {
    log "스케줄러 로그 확인 (Ctrl+C로 종료)..."
    docker-compose logs -f trading-bot-scheduler 2>&1 | tee -a "$LOG_FILE"
}

# 상태 확인
status() {
    log "컨테이너 상태:"
    docker-compose ps 2>&1 | tee -a "$LOG_FILE"

    echo ""
    log "리소스 사용량:"
    docker stats --no-stream trading-bot-dashboard trading-bot-scheduler 2>&1 | tee -a "$LOG_FILE" || true
}

# 정리
clean() {
    warning "중지된 컨테이너 및 unused 이미지를 제거합니다."
    read -p "계속하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "정리 중..."
        docker-compose down 2>&1 | tee -a "$LOG_FILE"
        docker system prune -f 2>&1 | tee -a "$LOG_FILE"
        log "✓ 정리 완료"
    else
        log "취소되었습니다."
    fi
}

# 메인 로직
case "${1:-}" in
    build)
        build
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    clean)
        clean
        ;;
    start-dashboard)
        start_dashboard
        ;;
    start-scheduler)
        start_scheduler
        ;;
    stop-dashboard)
        stop_dashboard
        ;;
    stop-scheduler)
        stop_scheduler
        ;;
    logs-dashboard)
        logs_dashboard
        ;;
    logs-scheduler)
        logs_scheduler
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        error "알 수 없는 명령어: ${1:-}"
        echo ""
        usage
        exit 1
        ;;
esac

log "로그 저장 위치: $LOG_FILE"
