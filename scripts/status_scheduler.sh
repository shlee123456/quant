#!/bin/bash

# Trading Bot Scheduler 상태 확인 스크립트

echo "================================"
echo "Trading Bot Scheduler 상태"
echo "================================"
echo ""

# 프로젝트 디렉토리로 이동
cd "$(dirname "$0")/.."

# 실행 여부 확인
if pgrep -f "python.*scheduler.py" > /dev/null; then
    echo "✅ 스케줄러 실행 중"
    echo ""

    # PID 확인
    if [ -f logs/scheduler.pid ]; then
        PID=$(cat logs/scheduler.pid)
        echo "📊 프로세스 정보:"
        ps aux | grep $PID | grep -v grep
    else
        echo "📊 프로세스 정보:"
        ps aux | grep "python.*scheduler.py" | grep -v grep
    fi

    echo ""
    echo "📅 스케줄:"
    echo "  - 23:30 KST: Paper Trading 시작"
    echo "  - 06:00 KST: Trading 종료 및 리포트"
    echo ""

    # 최근 로그 확인
    if [ -f logs/scheduler.log ]; then
        echo "📝 최근 로그 (마지막 10줄):"
        echo "================================"
        tail -n 10 logs/scheduler.log
    fi
else
    echo "⚠️  스케줄러가 실행 중이 아닙니다."
    echo ""
    echo "시작하려면: ./start_scheduler.sh"
fi

echo ""
echo "================================"
echo "로그 파일:"
echo "  - logs/scheduler.log (스케줄러 로그)"
echo "  - logs/scheduler_output.log (출력 로그)"
echo ""
echo "실시간 로그 확인:"
echo "  tail -f logs/scheduler.log"
