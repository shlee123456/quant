#!/bin/bash

echo "================================"
echo "스케줄러 실행 환경 체크"
echo "================================"
echo ""

# 1. Python 버전 확인
echo "1. Python 버전:"
python --version
echo ""

# 2. 필수 패키지 확인
echo "2. 필수 패키지 설치 확인:"
python -c "import apscheduler; print('  ✓ APScheduler:', apscheduler.__version__)" 2>/dev/null || echo "  ✗ APScheduler 미설치"
python -c "import dotenv; print('  ✓ python-dotenv 설치됨')" 2>/dev/null || echo "  ✗ python-dotenv 미설치"
python -c "import slack_sdk; print('  ✓ slack-sdk 설치됨')" 2>/dev/null || echo "  ✗ slack-sdk 미설치"
echo ""

# 3. .env 파일 확인
echo "3. 환경 변수 파일:"
if [ -f .env ]; then
    echo "  ✓ .env 파일 존재"
    
    # 주요 환경 변수 확인
    echo ""
    echo "4. 주요 환경 변수 확인:"
    grep -q "^KIS_APPKEY=" .env && echo "  ✓ KIS_APPKEY 설정됨" || echo "  ✗ KIS_APPKEY 미설정"
    grep -q "^KIS_APPSECRET=" .env && echo "  ✓ KIS_APPSECRET 설정됨" || echo "  ✗ KIS_APPSECRET 미설정"
    grep -q "^SLACK_WEBHOOK_URL=" .env && echo "  ✓ SLACK_WEBHOOK_URL 설정됨" || echo "  ✗ SLACK_WEBHOOK_URL 미설정"
    grep -q "^SLACK_BOT_TOKEN=" .env && echo "  ✓ SLACK_BOT_TOKEN 설정됨" || echo "  ✗ SLACK_BOT_TOKEN 미설정"
    grep -q "^SLACK_CHANNEL=" .env && echo "  ✓ SLACK_CHANNEL 설정됨" || echo "  ✗ SLACK_CHANNEL 미설정"
else
    echo "  ✗ .env 파일 없음 (.env.example을 복사하여 .env 생성 필요)"
fi
echo ""

# 4. logs 디렉토리 확인
echo "5. 로그 디렉토리:"
if [ -d logs ]; then
    echo "  ✓ logs/ 디렉토리 존재"
else
    echo "  ⚠ logs/ 디렉토리 없음 (자동 생성됨)"
fi
echo ""

# 5. scheduler.py 확인
echo "6. 스케줄러 파일:"
if [ -f scheduler.py ]; then
    echo "  ✓ scheduler.py 파일 존재"
else
    echo "  ✗ scheduler.py 파일 없음"
fi
echo ""

echo "================================"
echo "준비 완료 여부:"
echo "================================"
if [ -f .env ] && [ -f scheduler.py ]; then
    echo "✅ 스케줄러 실행 준비 완료!"
    echo ""
    echo "시작 명령어:"
    echo "  python scheduler.py"
else
    echo "❌ 설정이 필요합니다."
    echo ""
    echo "다음 단계를 완료하세요:"
    [ ! -f .env ] && echo "  1. .env 파일 생성 (cp .env.example .env)"
    [ ! -f scheduler.py ] && echo "  2. scheduler.py 파일 확인"
fi
echo ""
