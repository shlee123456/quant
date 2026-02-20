#!/usr/bin/env python3
"""
리포트 파일을 Slack에 업로드하는 스크립트
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from trading_bot.notifications import NotificationService
from trading_bot.database import TradingDatabase

# .env 파일 로드
load_dotenv()

def main():
    # 세션 ID 지정 (명령줄 인자 또는 기본값)
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        # 세션 ID가 없으면 최신 세션 사용
        db = TradingDatabase()
        sessions = db.get_all_sessions()
        if not sessions:
            print("❌ 저장된 세션이 없습니다.")
            return
        session_id = sessions[0]['session_id']
        print(f"ℹ️  최신 세션 사용: {session_id}")

    # 데이터베이스에서 세션 요약 조회
    db = TradingDatabase()
    session_summary = db.get_session_summary(session_id)

    if not session_summary:
        print(f"❌ 세션을 찾을 수 없습니다: {session_id}")
        return

    # 날짜 폴더 확인 (ISO 형식 처리)
    start_time = session_summary.get('start_time', '')
    if 'T' in start_time:
        date_str = start_time.split('T')[0]
    else:
        date_str = start_time.split()[0] if start_time else ''

    # 리포트 파일 경로 (날짜 폴더 우선, 없으면 루트 reports/)
    report_dir = Path("reports")
    date_report_dir = report_dir / date_str if date_str else report_dir

    # 날짜 폴더에서 먼저 확인, 없으면 루트에서 확인
    safe_session_id = session_id.replace(':', '_').replace(' ', '_')
    report_files = [
        str(date_report_dir / f"{safe_session_id}_summary.csv"),
        str(date_report_dir / f"{safe_session_id}_trades.csv"),
        str(date_report_dir / f"{safe_session_id}_snapshots.csv"),
        str(date_report_dir / f"{safe_session_id}_report.json"),
    ]

    # 날짜 폴더에 없으면 루트 폴더에서 확인
    if not any(Path(f).exists() for f in report_files):
        report_files = [
            str(report_dir / f"{safe_session_id}_summary.csv"),
            str(report_dir / f"{safe_session_id}_trades.csv"),
            str(report_dir / f"{safe_session_id}_snapshots.csv"),
            str(report_dir / f"{safe_session_id}_report.json"),
        ]

    # 존재하는 파일만 필터링
    existing_files = [f for f in report_files if Path(f).exists()]

    if not existing_files:
        print(f"❌ 리포트 파일을 찾을 수 없습니다: {session_id}")
        print(f"   확인한 경로:")
        print(f"   - {date_report_dir}")
        print(f"   - {report_dir}")
        return

    print(f"\n📊 세션 정보:")
    print(f"  ID: {session_id}")
    print(f"  전략: {session_summary.get('strategy_name', 'N/A')}")
    print(f"  수익률: {session_summary.get('total_return', 0):.2f}%")
    print(f"  상태: {session_summary.get('status', 'N/A')}")

    print(f"\n📤 Slack으로 업로드할 파일 ({len(existing_files)}개):")
    for f in existing_files:
        size = Path(f).stat().st_size
        print(f"  - {Path(f).name} ({size:,} bytes)")

    # NotificationService 초기화
    notifier = NotificationService(
        slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
        slack_channel=os.getenv('SLACK_CHANNEL'),
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL')
    )

    # 거래 수 계산
    trades = db.get_session_trades(session_id)
    session_summary['num_trades'] = len(trades)

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
