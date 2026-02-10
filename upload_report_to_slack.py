#!/usr/bin/env python3
"""
리포트 파일을 Slack에 업로드하는 스크립트
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from trading_bot.notifications import NotificationService

# .env 파일 로드
load_dotenv()

def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else "RSI_14_30_70_20260209_233001"

    # 리포트 파일 경로
    report_dir = Path("reports")
    report_files = [
        str(report_dir / f"{session_id}_summary.csv"),
        str(report_dir / f"{session_id}_trades.csv"),
        str(report_dir / f"{session_id}_snapshots.csv"),
        str(report_dir / f"{session_id}_report.json"),
    ]

    # 존재하는 파일만 필터링
    existing_files = [f for f in report_files if Path(f).exists()]

    print(f"📤 Slack으로 업로드할 파일 ({len(existing_files)}개):")
    for f in existing_files:
        size = Path(f).stat().st_size
        print(f"  - {Path(f).name} ({size:,} bytes)")

    # NotificationService 초기화
    notifier = NotificationService(
        slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
        slack_channel=os.getenv('SLACK_CHANNEL'),
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL')
    )

    # 세션 요약 데이터
    session_summary = {
        'strategy_name': 'RSI_14_30_70',
        'total_return': 0.55,
        'sharpe_ratio': 0.81,
        'max_drawdown': 0.38,
        'win_rate': 0.0,
        'num_trades': 1
    }

    # 업로드
    success = notifier.notify_daily_report_with_files(
        session_summary=session_summary,
        report_files=existing_files
    )

    if success:
        print("\n✅ Slack 업로드 완료!")
    else:
        print("\n❌ Slack 업로드 실패 (Bot Token 또는 Channel ID 확인 필요)")

if __name__ == '__main__':
    main()
