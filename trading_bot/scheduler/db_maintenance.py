"""
Database maintenance operations.

Handles:
- Downsampling completed session snapshots
- Pruning old data
- VACUUM
- Weekly backups
"""

import logging
from datetime import datetime

import pytz

import trading_bot.scheduler.scheduler_state as state

logger = logging.getLogger(__name__)


def db_maintenance():
    """
    일간 DB 유지보수 잡 (매일 06:05 KST, 장 마감 직후)
    - 다운샘플링 -> 30일 지난 데이터 삭제 -> VACUUM
    - 주 1회 백업은 일요일에만 실행
    """
    logger.info("=" * 60)
    logger.info("일간 DB 유지보수 시작...")
    logger.info("=" * 60)

    try:
        # 0. 유지보수 전 DB 통계
        stats_before = state.global_db.get_db_stats()
        logger.info(f"유지보수 전 DB 통계: {stats_before['tables']}, 크기: {stats_before['file_size_mb']}MB")

        # 1. 다운샘플링 (완료된 세션의 스냅샷 1시간 간격으로 축소)
        downsample_result = state.global_db.downsample_completed_sessions(hours_interval=1)
        logger.info(
            f"✓ 다운샘플링 완료: 스냅샷 {downsample_result['snapshots_removed']}개, "
            f"시그널 {downsample_result['signals_removed']}개 삭제"
        )

        # 2. 오래된 데이터 정리 (30일)
        deleted = state.global_db.prune_old_data(days_to_keep=30)
        logger.info(f"✓ 데이터 정리 완료: {deleted}")

        # 3. VACUUM
        state.global_db.vacuum()
        logger.info("✓ VACUUM 완료")

        # 4. 주 1회 백업 (일요일만)
        backup_path = None
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst)
        if now_kst.weekday() == 6:  # 일요일
            backup_path = state.global_db.backup()
            logger.info(f"✓ 주간 백업 완료: {backup_path}")

        # 유지보수 후 DB 통계
        stats_after = state.global_db.get_db_stats()
        logger.info(f"유지보수 후 DB 통계: {stats_after['tables']}, 크기: {stats_after['file_size_mb']}MB")

        # Slack 알림
        slack_msg = (
            f"*일간 DB 유지보수 완료*\n\n"
            f"다운샘플링: 스냅샷 {downsample_result['snapshots_removed']}개, "
            f"시그널 {downsample_result['signals_removed']}개 삭제\n"
            f"정리: 스냅샷 {deleted.get('snapshots', 0)}개, "
            f"시그널 {deleted.get('signals', 0)}개 삭제\n"
            f"DB 크기: {stats_before['file_size_mb']}MB → {stats_after['file_size_mb']}MB"
        )
        if backup_path:
            slack_msg += f"\n백업: {backup_path}"

        state.notifier.send_slack(slack_msg, color='good')

    except Exception as e:
        logger.error(f"DB 유지보수 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"DB 유지보수 실패: {e}", context="일간 유지보수")
