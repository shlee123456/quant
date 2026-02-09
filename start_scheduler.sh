#!/bin/bash

# Trading Bot Scheduler 시작 스크립트

echo "================================"
echo "Trading Bot Scheduler 시작"
echo "================================"
echo ""

# 프로젝트 디렉토리로 이동
cd "$(dirname "$0")"

# 이미 실행 중인지 확인
if pgrep -f "python.*scheduler.py" > /dev/null; then
    echo "⚠️  스케줄러가 이미 실행 중입니다!"
    echo ""
    echo "실행 중인 프로세스:"
    ps aux | grep "python.*scheduler.py" | grep -v grep
    echo ""
    echo "중지하려면: ./stop_scheduler.sh"
    exit 1
fi

# logs 디렉토리 생성
mkdir -p logs

# 백그라운드로 실행
echo "🚀 스케줄러 시작 중..."
nohup python scheduler.py > logs/scheduler_output.log 2>&1 &

# PID 저장
PID=$!
echo $PID > logs/scheduler.pid

sleep 2

# 실행 확인
if ps -p $PID > /dev/null; then
    echo "✅ 스케줄러가 성공적으로 시작되었습니다!"
    echo ""
    echo "📊 정보:"
    echo "  - PID: $PID"
    echo "  - 로그: logs/scheduler.log"
    echo "  - 출력: logs/scheduler_output.log"
    echo ""
    echo "📅 스케줄:"
    echo "  - 23:00 KST: 전략 최적화"
    echo "  - 23:30 KST: Paper Trading 시작"
    echo "  - 06:00 KST: Trading 종료 및 리포트"
    echo ""
    echo "🔍 로그 실시간 확인:"
    echo "  tail -f logs/scheduler.log"
    echo ""
    echo "⛔ 중지 방법:"
    echo "  ./stop_scheduler.sh"
    echo "  또는: kill $PID"
else
    echo "❌ 스케줄러 시작 실패!"
    echo "로그를 확인하세요: cat logs/scheduler_output.log"
    exit 1
fi
