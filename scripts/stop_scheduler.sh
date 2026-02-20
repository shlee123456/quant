#!/bin/bash

# Trading Bot Scheduler 중지 스크립트

echo "================================"
echo "Trading Bot Scheduler 중지"
echo "================================"
echo ""

# 프로젝트 디렉토리로 이동
cd "$(dirname "$0")/.."

# PID 파일 확인
if [ -f logs/scheduler.pid ]; then
    PID=$(cat logs/scheduler.pid)

    # 프로세스 존재 확인
    if ps -p $PID > /dev/null 2>&1; then
        echo "⛔ 스케줄러 중지 중... (PID: $PID)"
        kill $PID

        # 종료 대기 (최대 10초)
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                echo "✅ 스케줄러가 정상적으로 중지되었습니다."
                rm logs/scheduler.pid
                exit 0
            fi
            sleep 1
        done

        # 강제 종료
        echo "⚠️  정상 종료 실패. 강제 종료 중..."
        kill -9 $PID
        rm logs/scheduler.pid
        echo "✅ 강제 종료 완료"
    else
        echo "⚠️  PID 파일은 존재하지만 프로세스가 실행 중이 아닙니다."
        rm logs/scheduler.pid
    fi
else
    # PID 파일 없음 - 수동으로 프로세스 찾기
    if pgrep -f "python.*scheduler.py" > /dev/null; then
        echo "⚠️  PID 파일은 없지만 스케줄러가 실행 중입니다."
        echo ""
        echo "실행 중인 프로세스:"
        ps aux | grep "python.*scheduler.py" | grep -v grep
        echo ""

        # 사용자에게 확인
        read -p "이 프로세스를 종료하시겠습니까? (y/N): " confirm
        if [[ $confirm == [yY] ]]; then
            pkill -f "python.*scheduler.py"
            echo "✅ 스케줄러 종료 완료"
        else
            echo "취소되었습니다."
        fi
    else
        echo "ℹ️  실행 중인 스케줄러가 없습니다."
    fi
fi
