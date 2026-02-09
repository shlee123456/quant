"""
Test Script for Slack File Upload Feature

이 스크립트는 NotificationService의 Slack 파일 업로드 기능을 테스트합니다.

실행 전 준비사항:
1. Slack Bot Token 발급:
   - https://api.slack.com/apps 접속
   - 앱 선택 (또는 새로 생성)
   - "OAuth & Permissions" 메뉴
   - Scopes에 files:write, chat:write 추가
   - "Install to Workspace" 클릭
   - Bot User OAuth Token 복사 (xoxb-로 시작)

2. .env 파일에 다음 환경변수 설정:
   SLACK_BOT_TOKEN=xoxb-your-bot-token-here
   SLACK_CHANNEL=#trading-alerts

실행:
    python examples/test_slack_file_upload.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trading_bot.notifications import NotificationService
from dotenv import load_dotenv


def test_single_file_upload():
    """단일 파일 업로드 테스트"""
    print("\n" + "="*60)
    print("테스트 1: 단일 파일 업로드")
    print("="*60)

    # Load environment variables
    load_dotenv()

    # Check if bot token is configured
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    if not bot_token or bot_token == 'your_slack_bot_token_here':
        print("❌ SLACK_BOT_TOKEN이 설정되지 않았습니다.")
        print("   .env 파일에서 SLACK_BOT_TOKEN을 설정하세요.")
        return False

    # Initialize notification service
    notifier = NotificationService()

    # Find a test report file
    reports_dir = project_root / 'reports' / 'test'
    report_files = list(reports_dir.glob('*.json'))

    if not report_files:
        print("❌ 테스트용 리포트 파일을 찾을 수 없습니다.")
        print("   reports/test/ 디렉토리에 리포트 파일이 있는지 확인하세요.")
        return False

    test_file = str(report_files[0])
    print(f"\n📁 테스트 파일: {test_file}")

    # Upload file
    success = notifier.upload_file_to_slack(
        file_path=test_file,
        initial_comment="🧪 테스트: 단일 파일 업로드",
        title="Test Trading Report"
    )

    if success:
        print("✅ 단일 파일 업로드 성공!")
        return True
    else:
        print("❌ 단일 파일 업로드 실패")
        return False


def test_multiple_files_upload():
    """여러 파일 동시 업로드 테스트"""
    print("\n" + "="*60)
    print("테스트 2: 여러 파일 동시 업로드")
    print("="*60)

    # Load environment variables
    load_dotenv()

    # Initialize notification service
    notifier = NotificationService()

    # Find test report files
    reports_dir = project_root / 'reports' / 'test'

    # Get one set of reports (summary, snapshots, report)
    json_files = list(reports_dir.glob('*_report.json'))
    if not json_files:
        print("❌ 테스트용 리포트 파일을 찾을 수 없습니다.")
        return False

    # Get base name (without extension and suffix)
    base_name = str(json_files[0].name).replace('_report.json', '')

    report_files = [
        str(reports_dir / f"{base_name}_summary.csv"),
        str(reports_dir / f"{base_name}_snapshots.csv"),
        str(reports_dir / f"{base_name}_report.json")
    ]

    # Filter existing files
    report_files = [f for f in report_files if Path(f).exists()]

    print(f"\n📁 업로드할 파일 ({len(report_files)}개):")
    for f in report_files:
        print(f"   - {Path(f).name}")

    # Upload files with summary
    session_summary = {
        'strategy_name': 'RSI_14_30_70',
        'total_return': 2.5,
        'sharpe_ratio': 1.45,
        'max_drawdown': -3.2,
        'win_rate': 65.0,
        'num_trades': 12
    }

    success = notifier.upload_reports_to_slack(
        report_files=report_files,
        session_summary=session_summary
    )

    if success:
        print("✅ 여러 파일 업로드 성공!")
        return True
    else:
        print("❌ 여러 파일 업로드 실패")
        return False


def test_daily_report_with_files():
    """일일 리포트 + 파일 업로드 통합 테스트"""
    print("\n" + "="*60)
    print("테스트 3: 일일 리포트 + 파일 업로드")
    print("="*60)

    # Load environment variables
    load_dotenv()

    # Initialize notification service
    notifier = NotificationService()

    # Find test report files
    reports_dir = project_root / 'reports' / 'test'
    json_files = list(reports_dir.glob('*_report.json'))
    if not json_files:
        print("❌ 테스트용 리포트 파일을 찾을 수 없습니다.")
        return False

    base_name = str(json_files[0].name).replace('_report.json', '')
    report_files = [
        str(reports_dir / f"{base_name}_summary.csv"),
        str(reports_dir / f"{base_name}_snapshots.csv"),
        str(reports_dir / f"{base_name}_report.json")
    ]
    report_files = [f for f in report_files if Path(f).exists()]

    # Session summary
    session_summary = {
        'strategy_name': 'RSI_14_30_70',
        'total_return': 2.5,
        'sharpe_ratio': 1.45,
        'max_drawdown': -3.2,
        'win_rate': 65.0,
        'num_trades': 12
    }

    print(f"\n📊 세션 요약:")
    print(f"   전략: {session_summary['strategy_name']}")
    print(f"   수익률: {session_summary['total_return']:+.2f}%")
    print(f"   샤프: {session_summary['sharpe_ratio']:.2f}")
    print(f"   낙폭: {session_summary['max_drawdown']:.2f}%")
    print(f"   승률: {session_summary['win_rate']:.1f}%")

    print(f"\n📁 리포트 파일 ({len(report_files)}개):")
    for f in report_files:
        print(f"   - {Path(f).name}")

    # Send notification with files
    success = notifier.notify_daily_report_with_files(
        session_summary=session_summary,
        report_files=report_files
    )

    if success:
        print("✅ 일일 리포트 + 파일 업로드 성공!")
        return True
    else:
        print("❌ 일일 리포트 + 파일 업로드 실패")
        return False


def main():
    """메인 테스트 실행"""
    print("\n" + "="*60)
    print("Slack 파일 업로드 기능 테스트")
    print("="*60)
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check environment
    load_dotenv()
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    channel = os.getenv('SLACK_CHANNEL', '#trading-alerts')

    print(f"\n환경 설정:")
    print(f"   Bot Token: {'✓ 설정됨' if bot_token and bot_token != 'your_slack_bot_token_here' else '✗ 미설정'}")
    print(f"   Channel: {channel}")

    if not bot_token or bot_token == 'your_slack_bot_token_here':
        print("\n❌ SLACK_BOT_TOKEN이 설정되지 않았습니다.")
        print("\n다음 단계를 따라 설정하세요:")
        print("1. https://api.slack.com/apps 접속")
        print("2. 앱 선택 (또는 새로 생성)")
        print("3. 'OAuth & Permissions' 메뉴")
        print("4. Scopes에 'files:write', 'chat:write' 추가")
        print("5. 'Install to Workspace' 클릭")
        print("6. Bot User OAuth Token 복사 (xoxb-로 시작)")
        print("7. .env 파일에 SLACK_BOT_TOKEN=<복사한 토큰> 추가")
        return

    # Run tests
    results = []

    # Test 1: Single file upload
    results.append(("단일 파일 업로드", test_single_file_upload()))

    # Test 2: Multiple files upload
    results.append(("여러 파일 업로드", test_multiple_files_upload()))

    # Test 3: Daily report with files
    results.append(("일일 리포트 + 파일", test_daily_report_with_files()))

    # Summary
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)

    for test_name, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{status} - {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)

    print(f"\n총 {total_tests}개 테스트 중 {passed_tests}개 통과")

    if passed_tests == total_tests:
        print("\n🎉 모든 테스트 통과!")
    else:
        print(f"\n⚠️  {total_tests - passed_tests}개 테스트 실패")


if __name__ == '__main__':
    main()
