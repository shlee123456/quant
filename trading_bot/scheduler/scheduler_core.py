"""
APScheduler setup, job registration, heartbeat, watchdog, and CLI handlers.

Handles:
- Signal handler for graceful shutdown
- Heartbeat job (status + command polling)
- Watchdog job (dead thread detection + anomaly detection)
- CLI management commands (--status, --stop, --cleanup, --stop-all)
- Environment validation
"""

import os
import sys
import logging
from datetime import datetime

import trading_bot.scheduler.scheduler_state as state
from trading_bot.scheduler.session_manager import stop_paper_trading, _stop_single_session

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """종료 신호를 우아하게 처리"""
    logger.info("\n\n⚠ 종료 신호 수신")
    with state.traders_lock:
        has_active = len(state.active_traders) > 0
    if has_active:
        logger.info("활성 트레이딩 세션 중지 중...")
        try:
            stop_paper_trading()
        except Exception as e:
            logger.error(f"✗ 세션 중지 중 에러 (무시): {e}", exc_info=True)
    state.scheduler_health.update('stopping')
    logger.info("스케줄러 중지됨")
    sys.exit(0)


def heartbeat():
    """
    하트비트 잡 (60초 간격)
    - 상태 파일 갱신
    - 제어 명령 폴링 및 처리
    """
    try:
        # 현재 활성 세션 정보 수집
        with state.traders_lock:
            session_info = []
            for label, trader in state.active_traders.items():
                thread = state.trader_threads.get(label)
                session_info.append({
                    'label': label,
                    'alive': thread.is_alive() if thread else False,
                    'started_at': trader.session_id or 'unknown',
                })

            current_state = 'trading' if state.active_traders else 'idle'

        state.scheduler_health.update(current_state, {
            'active_sessions': session_info,
            'preset_count': len(state.preset_configs),
        })

        # 에러 카운트 리셋 (활성 세션이 정상일 때)
        if current_state == 'trading':
            state.notifier.reset_error_count()

        # 제어 명령 폴링
        try:
            commands = state.global_db.get_pending_commands()
            for cmd in commands:
                cmd_type = cmd['command']
                target = cmd.get('target_label')
                logger.info(f"제어 명령 수신: {cmd_type} (대상: {target or 'N/A'})")

                if cmd_type == 'stop_session' and target:
                    _stop_single_session(target)
                elif cmd_type == 'cleanup_zombies':
                    recovered = state.global_db.recover_zombie_sessions()
                    logger.info(f"좀비 세션 정리 완료: {recovered}개")
                elif cmd_type == 'status_dump':
                    with state.traders_lock:
                        labels = list(state.active_traders.keys())
                    logger.info(f"활성 세션 목록: {labels}")

                state.global_db.mark_command_processed(cmd['id'])
        except Exception as e:
            logger.error(f"제어 명령 처리 실패: {e}")

    except Exception as e:
        logger.error(f"하트비트 실패: {e}")


def watchdog():
    """
    워치독 잡 (2분 간격)
    - 죽은 스레드 감지 및 정리
    - 이상 감지 (AnomalyDetector)
    """
    try:
        dead_labels = []

        with state.traders_lock:
            for label, thread in list(state.trader_threads.items()):
                if not thread.is_alive():
                    dead_labels.append(label)

        # 죽은 스레드 정리
        for label in dead_labels:
            logger.error(f"워치독: 죽은 스레드 감지 [{label}]")
            with state.traders_lock:
                trader = state.active_traders.pop(label, None)
                state.trader_threads.pop(label, None)

            # DB 세션 상태 업데이트
            if trader and trader.session_id and trader.db:
                try:
                    trader.db.update_session(trader.session_id, {
                        'status': 'interrupted',
                        'end_time': datetime.now().isoformat(),
                    })
                except Exception as e:
                    logger.error(f"세션 상태 업데이트 실패 [{label}]: {e}")

            state.notifier.notify_error(
                f"트레이딩 스레드 비정상 종료: {label}",
                context="워치독 감지"
            )

        # 상태 파일 갱신
        if dead_labels:
            state.scheduler_health.update('trading' if state.active_traders else 'idle')

        # 이상 감지
        with state.traders_lock:
            traders_snapshot = dict(state.active_traders)

        alerts = state.anomaly_detector.check_all(traders_snapshot, state.global_db.db_path)
        for alert in alerts:
            logger.warning(f"이상 감지: {alert}")
            state.notifier.send_slack(f"*운영 이상 감지*\n\n{alert}", color='warning')

    except Exception as e:
        logger.error(f"워치독 실패: {e}")


def _handle_status():
    """--status: 상태 파일 + DB 세션 조회 -> 테이블 출력"""
    # 상태 파일 읽기
    status = state.scheduler_health.read()
    print("\n=== 스케줄러 상태 ===")
    if status:
        print(f"  상태: {status.get('state', 'unknown')}")
        print(f"  마지막 업데이트: {status.get('timestamp', 'N/A')}")
        print(f"  PID: {status.get('pid', 'N/A')}")
        details = status.get('details', {})
        sessions = details.get('active_sessions', [])
        if sessions:
            print(f"\n  활성 세션 ({len(sessions)}개):")
            for s in sessions:
                alive = '✓' if s.get('alive') else '✗'
                print(f"    [{alive}] {s.get('label', 'unknown')}")
    else:
        print("  상태 파일 없음 (스케줄러 미실행)")

    # DB 활성 세션 조회
    db_sessions = state.global_db.get_all_sessions(status_filter='active')
    print(f"\n=== DB 활성 세션 ({len(db_sessions)}개) ===")
    for s in db_sessions:
        print(f"  {s['session_id']}: {s.get('display_name') or s['strategy_name']} (시작: {s['start_time']})")

    # 세션 상태 카운트
    counts = state.global_db.get_session_status_counts()
    print(f"\n=== 세션 상태 요약 ===")
    for status_name, count in counts.items():
        print(f"  {status_name}: {count}개")
    print()


def _handle_stop(target_label: str):
    """--stop: DB에 stop_session 명령 삽입"""
    cmd_id = state.global_db.insert_command('stop_session', target_label)
    print(f"✓ 세션 중지 명령 전송 완료 (ID: {cmd_id})")
    print(f"  대상: {target_label}")
    print(f"  스케줄러가 다음 하트비트(최대 60초)에서 처리합니다")


def _handle_stop_all():
    """--stop-all: 모든 활성 세션에 stop 명령 삽입"""
    db_sessions = state.global_db.get_all_sessions(status_filter='active')
    if not db_sessions:
        print("⚠ 활성 세션 없음")
        return

    for s in db_sessions:
        label = s.get('display_name') or s['session_id']
        cmd_id = state.global_db.insert_command('stop_session', label)
        print(f"✓ 중지 명령 전송: {label} (ID: {cmd_id})")

    print(f"\n총 {len(db_sessions)}개 세션 중지 명령 전송 완료")
    print("스케줄러가 다음 하트비트(최대 60초)에서 처리합니다")


def _handle_cleanup():
    """--cleanup: 좀비 세션 즉시 정리"""
    recovered = state.global_db.recover_zombie_sessions()
    print(f"✓ 좀비 세션 정리 완료: {recovered}개")


def _validate_environment():
    """
    스케줄러 시작 전 환경 변수 검증.
    필수 변수 누락 시 에러 로그 출력 후 프로세스 종료.
    선택 변수 누락 시 경고 로그만 출력.
    """
    # 필수 환경 변수 (KIS 브로커)
    required_vars = ['KIS_APPKEY', 'KIS_APPSECRET', 'KIS_ACCOUNT']
    missing_required = [v for v in required_vars if not os.getenv(v, '').strip()]

    if missing_required:
        for var in missing_required:
            logger.error(f"필수 환경 변수 미설정: {var}")
        logger.error(f"필수 환경 변수가 누락되었습니다: {', '.join(missing_required)}")
        logger.error(".env 파일을 확인하세요")
        sys.exit(1)

    # 선택 환경 변수 (알림 서비스)
    optional_vars = ['SLACK_WEBHOOK_URL', 'SLACK_BOT_TOKEN', 'SMTP_SERVER']
    for var in optional_vars:
        if not os.getenv(var, '').strip():
            logger.warning(f"선택 환경 변수 미설정: {var} (해당 알림 기능 비활성화)")
