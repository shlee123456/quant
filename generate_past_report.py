#!/usr/bin/env python3
"""
과거 세션 리포트 생성 스크립트
"""
import sys
from trading_bot.database import TradingDatabase
from trading_bot.reports import ReportGenerator

def main():
    # 데이터베이스 초기화
    db = TradingDatabase()

    # 최근 세션 조회
    sessions = db.get_all_sessions()

    if not sessions:
        print("❌ 저장된 세션이 없습니다.")
        return

    print(f"\n📊 저장된 세션 목록 (최근 5개):")
    print("="*80)
    for i, session in enumerate(sessions[:5], 1):
        print(f"{i}. {session['session_id']}")
        print(f"   전략: {session['strategy_name']}")
        print(f"   기간: {session['start_time']} ~ {session.get('end_time', 'N/A')}")
        print(f"   수익률: {session.get('total_return', 0):.2f}%")
        print(f"   상태: {session['status']}")
        print("-"*80)

    # 세션 ID 지정 (가장 최근 세션)
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        session_id = sessions[0]['session_id']

    print(f"\n📝 리포트 생성 중: {session_id}")

    # 리포트 생성
    report_gen = ReportGenerator(db)

    try:
        report_files = report_gen.generate_session_report(
            session_id=session_id,
            output_dir='reports/',
            formats=['csv', 'json']
        )

        print("\n✅ 리포트 생성 완료:")
        for format_name, file_path in report_files.items():
            print(f"  {format_name.upper()}: {file_path}")

        return report_files

    except Exception as e:
        print(f"\n❌ 리포트 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    main()
