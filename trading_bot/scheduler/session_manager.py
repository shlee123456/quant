"""
Paper trading session start/stop/report management.

Handles:
- Starting single and multi-preset trading sessions
- Stopping sessions and generating reports
- Trading day detection (weekends, US holidays)
- Market analysis after close
"""

import os
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

import pytz

from trading_bot.paper_trader import PaperTrader
from trading_bot.database import TradingDatabase, generate_display_name
from trading_bot.reports import ReportGenerator
from trading_bot.us_holidays import is_us_market_holiday

from trading_bot.brokers import KoreaInvestmentBroker

# 한국 시장 공휴일 (optional - 모듈 미존재 시 주말만 체크)
try:
    from trading_bot.kr_holidays import is_kr_market_holiday
    _has_kr_holidays = True
except ImportError:
    _has_kr_holidays = False

import trading_bot.scheduler.scheduler_state as state

logger = logging.getLogger(__name__)

# Re-export live trader availability from state
_has_live_trader = state._has_live_trader


def _create_kis_broker() -> Optional[KoreaInvestmentBroker]:
    """KIS 브로커를 환경 변수에서 직접 초기화합니다."""
    appkey = os.getenv('KIS_APPKEY', '').strip()
    appsecret = os.getenv('KIS_APPSECRET', '').strip()
    account = os.getenv('KIS_ACCOUNT', '').strip()

    if not appkey or not appsecret or not account:
        logger.warning("KIS API 환경 변수 미설정 - 브로커 초기화 불가")
        return None

    user_id = os.getenv('KIS_USER_ID', account).strip()
    mock_str = os.getenv('KIS_MOCK', 'true').strip().lower()
    mock = mock_str in ('true', '1', 'yes', 'on')

    try:
        broker = KoreaInvestmentBroker(
            appkey=appkey, appsecret=appsecret,
            account=account, user_id=user_id, mock=mock
        )
        logger.info(f"KIS 브로커 초기화 성공 (mock={mock})")
        return broker
    except Exception as e:
        logger.error(f"KIS 브로커 초기화 실패: {e}")
        return None


def _is_trading_day() -> bool:
    """
    오늘이 미국 주식시장 거래일인지 확인합니다.
    KST 23:30에 호출되므로, 미국 동부시간(EST/EDT) 기준 날짜를 사용합니다.

    Returns:
        거래일이면 True, 공휴일/주말이면 False
    """
    us_eastern = pytz.timezone('US/Eastern')
    us_now = datetime.now(us_eastern)
    us_date = us_now.date()

    # 주말 체크
    if us_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        logger.info(f"주말입니다 (미국 동부: {us_date}, {us_date.strftime('%A')}) - 트레이딩 건너뜀")
        return False

    # 공휴일 체크
    if is_us_market_holiday(us_date):
        logger.info(f"미국 시장 공휴일입니다 (미국 동부: {us_date}) - 트레이딩 건너뜀")
        return False

    return True


def _is_kr_trading_day() -> bool:
    """
    오늘이 한국 주식시장 거래일인지 확인합니다.
    KST 15:50에 호출되므로, KST 기준 오늘 날짜를 사용합니다.

    Returns:
        거래일이면 True, 공휴일/주말이면 False
    """
    kst = pytz.timezone('Asia/Seoul')
    kr_now = datetime.now(kst)
    kr_date = kr_now.date()

    # 주말 체크
    if kr_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        logger.info(f"주말입니다 (KST: {kr_date}, {kr_date.strftime('%A')}) - 한국 시장 분석 건너뜀")
        return False

    # 공휴일 체크 (kr_holidays 모듈 존재 시)
    if _has_kr_holidays:
        if is_kr_market_holiday(kr_date):
            logger.info(f"한국 시장 공휴일입니다 (KST: {kr_date}) - 한국 시장 분석 건너뜀")
            return False

    return True


def _run_trader_thread(label: str, trader: PaperTrader):
    """
    daemon thread에서 실행되는 트레이딩 루프

    Args:
        label: 세션 라벨
        trader: PaperTrader 인스턴스
    """
    log_prefix = f"[{label}]"
    try:
        trader.run_realtime(interval_seconds=60, timeframe='1h')
    except Exception as e:
        logger.error(f"{log_prefix} ✗ 트레이딩 루프 오류: {e}", exc_info=True)
    finally:
        logger.info(f"{log_prefix} 트레이딩 루프 종료됨")


def _start_single_session(label: str, config: Optional[Dict]):
    """
    단일 트레이딩 세션을 daemon thread로 시작하는 헬퍼

    Args:
        label: 세션 라벨 (로그 접두어로 사용)
        config: 프리셋 설정 dict 또는 None (기본 설정 사용)
    """
    log_prefix = f"[{label}]"

    # 최대 세션 수 제한 검사
    if state.ctx.max_sessions > 0:
        with state.traders_lock:
            current_count = len(state.active_traders)
        if current_count >= state.ctx.max_sessions:
            logger.warning(f"{log_prefix} ⚠ 최대 세션 수 초과 ({current_count}/{state.ctx.max_sessions}) - 세션 시작 거부")
            return

    try:
        # 브로커 초기화 (공유 브로커가 있으면 재사용)
        if state.ctx.global_broker is not None:
            broker = state.ctx.global_broker
            logger.info(f"{log_prefix} 공유 브로커 재사용")
        else:
            broker = _create_kis_broker()
        if not broker:
            logger.error(f"{log_prefix} ✗ KIS 브로커 초기화 실패 - 세션을 시작할 수 없습니다")
            state.notifier.notify_error(f"KIS 브로커 초기화 실패", context=f"세션 시작: {label}")
            return

        # 데이터베이스 초기화
        db = TradingDatabase()

        # 기본 설정 (Top 10 US Market Cap)
        strategy_name = "RSI+MACD Combo Strategy"
        strategy_params = None
        symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT']
        initial_capital = 10000.0
        position_size = 0.1  # 10종목 x 10% = 100%
        stop_loss_pct = 0.03
        take_profit_pct = 0.05
        enable_stop_loss = True
        enable_take_profit = True
        limit_orders = []

        # 프리셋에서 설정 적용
        if config:
            strategy_name = config.get('strategy', strategy_name)
            strategy_params = config.get('strategy_params')
            symbols = config.get('symbols', symbols)
            initial_capital = config.get('initial_capital', initial_capital)
            position_size = config.get('position_size', position_size)
            stop_loss_pct = config.get('stop_loss_pct', stop_loss_pct)
            take_profit_pct = config.get('take_profit_pct', take_profit_pct)
            enable_stop_loss = config.get('enable_stop_loss', enable_stop_loss)
            enable_take_profit = config.get('enable_take_profit', enable_take_profit)
            limit_orders = config.get('limit_orders', [])
            logger.info(f"{log_prefix} 프리셋 설정 적용됨: {config.get('_preset_name', label)}")
            if limit_orders:
                logger.info(f"{log_prefix} 지정가 주문 {len(limit_orders)}건 설정됨")

        # 전략 클래스 결정
        strategy_class = state.STRATEGY_CLASS_MAP.get(strategy_name, state.STRATEGY_CLASS_MAP['RSI+MACD Combo Strategy'])

        # 전략 생성 (프리셋 파라미터 > 기본값)
        if config and strategy_params:
            logger.info(f"{log_prefix} 프리셋 파라미터 사용: {strategy_params}")
            strategy = strategy_class(**strategy_params)
        else:
            logger.info(f"{log_prefix} 기본 파라미터 사용 (프리셋 없음) - {strategy_name}")
            strategy = strategy_class()

        logger.info(f"{log_prefix} 전략: {strategy.name}")
        logger.info(f"{log_prefix} 종목: {', '.join(symbols)}")

        # display_name 생성
        display_name = generate_display_name(
            strategy_name=strategy.name,
            symbols=symbols,
            preset_name=label if config else None
        )

        # Adaptive strategy manager (프리셋에 adaptive_regime_switching=true 시)
        adaptive_manager = None
        if config and config.get('adaptive_regime_switching') and state.global_regime_detector:
            try:
                from trading_bot.adaptive_strategy_manager import AdaptiveStrategyManager
                _adapter = None
                if config.get('adaptive_parameters'):
                    from trading_bot.parameter_adapter import ParameterAdapter
                    _adapter = ParameterAdapter(
                        base_strategy_params=strategy_params or strategy.get_params(),
                        base_stop_loss_pct=stop_loss_pct,
                        base_take_profit_pct=take_profit_pct,
                    )
                adaptive_manager = AdaptiveStrategyManager(
                    strategy_class_map=state.STRATEGY_CLASS_MAP,
                    regime_detector=state.global_regime_detector,
                    initial_strategy=strategy,
                    regime_strategy_map=config.get('regime_strategy_map') or None,
                    default_params=config.get('default_params_per_strategy') or {},
                    parameter_adapter=_adapter,
                )
                logger.info(f"{log_prefix} 적응형 전략 관리자 활성화 (파라미터 적응: {config.get('adaptive_parameters', False)})")
            except Exception as e:
                logger.warning(f"{log_prefix} 적응형 전략 관리자 초기화 실패: {e}")

        # 페이퍼 트레이더 생성 (레짐 감지 + LLM 통합)
        trader = PaperTrader(
            strategy=strategy,
            symbols=symbols,
            broker=broker,
            initial_capital=initial_capital,
            position_size=position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
            db=db,
            display_name=display_name,
            regime_detector=state.global_regime_detector,
            llm_client=state.global_llm_client,
            limit_orders=limit_orders if limit_orders else None,
            adaptive_manager=adaptive_manager,
        )

        # Attach notifier to trader for stop loss/take profit notifications
        trader.notifier = state.notifier

        logger.info(f"{log_prefix} ✓ 페이퍼 트레이더 초기화 완료")
        logger.info(f"{log_prefix}   초기 자본: ${trader.initial_capital:,.2f}")
        logger.info(f"{log_prefix}   포지션 크기: {trader.position_size:.0%}")
        logger.info(f"{log_prefix}   손절매: {trader.stop_loss_pct:.0%} ({'활성' if trader.enable_stop_loss else '비활성'})")
        logger.info(f"{log_prefix}   익절매: {trader.take_profit_pct:.0%} ({'활성' if trader.enable_take_profit else '비활성'})")

        # 세션 시작 알림 전송
        state.notifier.notify_session_start({
            'strategy_name': display_name,
            'symbols': symbols,
            'initial_capital': trader.initial_capital
        })

        # daemon thread로 실시간 트레이딩 시작
        def run_trading():
            _run_trader_thread(label, trader)

        thread = threading.Thread(target=run_trading, name=f"trader-{label}", daemon=True)

        # active_traders와 trader_threads를 단일 락 블록에서 등록
        with state.traders_lock:
            state.active_traders[label] = trader
            state.trader_threads[label] = thread
        thread.start()

        logger.info(f"{log_prefix} 실시간 트레이딩 루프 시작 (60초 간격, 1시간봉)...")

    except Exception as e:
        logger.error(f"{log_prefix} ✗ 페이퍼 트레이딩 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"페이퍼 트레이딩 실패: {e}", context=f"세션: {label}")
        with state.traders_lock:
            state.active_traders.pop(label, None)
            state.trader_threads.pop(label, None)


def start_paper_trading():
    """
    장 시작 작업: 페이퍼 트레이딩 세션 시작
    장 시작 시각 (23:30 KST) 실행

    preset_configs에 등록된 프리셋 수만큼 세션을 동시 시작합니다.
    프리셋이 없으면 기본 설정 1개 세션을 시작합니다.
    """
    logger.info("=" * 60)
    logger.info("페이퍼 트레이딩 세션 시작...")
    logger.info("=" * 60)

    state.scheduler_health.update('trading')

    if state.preset_configs:
        logger.info(f"총 {len(state.preset_configs)}개 프리셋 세션 시작")

        # 멀티 프리셋: 공유 브로커를 한 번만 생성하여 RateLimiter를 공유
        if len(state.preset_configs) > 1 and state.ctx.global_broker is None:
            shared = _create_kis_broker()
            if shared:
                state.ctx.global_broker = shared
                logger.info("멀티 프리셋용 공유 브로커 초기화 완료")

        for cfg in state.preset_configs:
            label = cfg.get('_preset_name', 'unknown')
            _start_single_session(label, cfg)
    else:
        # 프리셋 없이 기본 설정 1개 세션
        _start_single_session("기본", None)

    with state.traders_lock:
        logger.info(f"✓ 활성 세션 수: {len(state.active_traders)}")


def _stop_single_session(label: str):
    """
    단일 트레이딩 세션 중지 및 리포트 생성 헬퍼

    Args:
        label: 세션 라벨
    """
    log_prefix = f"[{label}]"

    with state.traders_lock:
        trader = state.active_traders.pop(label, None)
        thread = state.trader_threads.pop(label, None)

    if trader is None:
        logger.warning(f"{log_prefix} ⚠ 중지할 세션 없음")
        return

    try:
        # 트레이딩 루프에 종료 시그널 전송
        trader.is_running = False
        trader._stop_event.set()

        # 트레이딩 루프가 실제로 종료될 때까지 대기 (최대 120초)
        logger.info(f"{log_prefix} 트레이딩 루프 종료 대기 중...")
        if thread and thread.is_alive():
            thread.join(timeout=120)
            if thread.is_alive():
                logger.warning(f"{log_prefix} ⚠ 트레이딩 스레드가 120초 내에 종료되지 않음 - 강제 종료 진행")
            else:
                logger.info(f"{log_prefix} ✓ 트레이딩 스레드 정상 종료")
        else:
            # thread가 없거나 이미 종료된 경우 _loop_exited 이벤트로 대기
            exited = trader._loop_exited.wait(timeout=120)
            if exited:
                logger.info(f"{log_prefix} ✓ 트레이딩 루프 정상 종료")
            else:
                logger.warning(f"{log_prefix} ⚠ 트레이딩 루프가 120초 내에 종료되지 않음 - 강제 종료 진행")

        # 세션 종료 및 DB 업데이트
        trader.stop()

        # 세션 요약 조회
        if trader.session_id and trader.db:
            summary = trader.db.get_session_summary(trader.session_id)

            if summary:
                logger.info(f"{log_prefix} ✓ 세션 중지 성공")
                logger.info(f"{log_prefix}   세션 ID: {trader.session_id}")
                logger.info(f"{log_prefix}   최종 자본: ${summary['final_capital']:,.2f}" if summary['final_capital'] is not None else f"{log_prefix}   최종 자본: N/A")
                logger.info(f"{log_prefix}   총 수익률: {summary['total_return']:.2f}%" if summary['total_return'] is not None else f"{log_prefix}   총 수익률: N/A")
                logger.info(f"{log_prefix}   샤프 비율: {summary['sharpe_ratio']:.2f}" if summary['sharpe_ratio'] is not None else f"{log_prefix}   샤프 비율: N/A (데이터 부족)")
                logger.info(f"{log_prefix}   최대 낙폭: {summary['max_drawdown']:.2f}%" if summary['max_drawdown'] is not None else f"{log_prefix}   최대 낙폭: N/A (데이터 부족)")
                logger.info(f"{log_prefix}   승률: {summary['win_rate']:.2f}%" if summary['win_rate'] is not None else f"{log_prefix}   승률: N/A (매도 거래 없음)")

                # 거래 횟수 조회
                trades = trader.db.get_session_trades(trader.session_id)
                logger.info(f"{log_prefix}   총 거래: {len(trades)}회")

                # 리포트 생성 및 Slack 업로드
                try:
                    report_gen = ReportGenerator(trader.db)
                    report_files = report_gen.generate_session_report(
                        trader.session_id,
                        output_dir='reports/',
                        formats=['csv', 'json']
                    )

                    logger.info(f"{log_prefix} ✓ 리포트 생성 완료:")
                    for format_name, file_path in report_files.items():
                        logger.info(f"{log_prefix}   {format_name.upper()}: {file_path}")

                    # 리포트 파일을 Slack에 업로드
                    file_paths = list(report_files.values())

                    logger.info(f"{log_prefix} 📤 Slack으로 리포트 파일 업로드 중... ({len(file_paths)}개)")

                    # 세션 요약과 함께 파일 업로드
                    upload_success = state.notifier.notify_daily_report_with_files(
                        session_summary={
                            'strategy_name': summary.get('display_name') or f"{label} - {summary.get('strategy_name', 'Unknown')}",
                            'total_return': summary['total_return'] if summary['total_return'] is not None else 0.0,
                            'sharpe_ratio': summary['sharpe_ratio'] if summary['sharpe_ratio'] is not None else 0.0,
                            'max_drawdown': summary['max_drawdown'] if summary['max_drawdown'] is not None else 0.0,
                            'win_rate': summary['win_rate'] if summary['win_rate'] is not None else 0.0,
                            'num_trades': len(trades)
                        },
                        report_files=file_paths
                    )

                    if upload_success:
                        logger.info(f"{log_prefix} ✓ Slack 리포트 업로드 완료")
                    else:
                        logger.warning(f"{log_prefix} ⚠ Slack 리포트 업로드 실패 (Bot Token/Channel 확인 필요)")

                except Exception as e:
                    logger.error(f"{log_prefix} ✗ 리포트 생성 실패: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"{log_prefix} ✗ 트레이딩 세션 중지 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"트레이딩 세션 중지 실패: {e}", context=f"장 마감: {label}")


def stop_paper_trading():
    """
    장 마감 작업: 모든 페이퍼 트레이딩 세션 중지 및 리포트 생성
    장 마감 시각 (06:00 KST) 실행
    """
    logger.info("=" * 60)
    logger.info("모든 페이퍼 트레이딩 세션 중지 중...")
    logger.info("=" * 60)

    state.scheduler_health.update('stopping')

    with state.traders_lock:
        labels = list(state.active_traders.keys())

    if not labels:
        logger.warning("⚠ 중지할 활성 트레이딩 세션 없음")
        return

    logger.info(f"총 {len(labels)}개 세션 중지 시작")

    for label in labels:
        _stop_single_session(label)

    logger.info(f"✓ 전체 {len(labels)}개 세션 중지 완료")


def run_market_analysis():
    """
    장 마감 후 시장 분석: MarketAnalyzer로 데이터 수집 + JSON 저장
    06:10 KST 실행. 노션 작성은 호스트의 scripts/notion_writer.py (cron)에서 처리.
    """
    logger.info("=" * 60)
    logger.info("시장 분석 시작...")
    logger.info("=" * 60)

    if not _is_trading_day():
        return

    if not state._has_market_analyzer:
        logger.warning("MarketAnalyzer 모듈 미설치 - 시장 분석 건너뜀")
        return

    # 환경 변수에서 설정 읽기
    enabled = os.getenv('MARKET_ANALYSIS_ENABLED', 'true').strip().lower()
    if enabled not in ('true', '1', 'yes'):
        logger.info("MARKET_ANALYSIS_ENABLED=false - 시장 분석 비활성화됨")
        return

    symbols_str = os.getenv(
        'MARKET_ANALYSIS_SYMBOLS',
        'AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT'
    )
    symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]

    try:
        # 브로커 초기화
        broker = _create_kis_broker()
        if not broker:
            logger.error("KIS 브로커 초기화 실패 - 시장 분석 불가")
            state.notifier.notify_error("KIS 브로커 초기화 실패", context="시장 분석")
            return

        # MarketAnalyzer로 데이터 수집
        analyzer = state.MarketAnalyzer()
        logger.info(f"분석 대상 종목: {', '.join(symbols)}")
        result = analyzer.analyze(symbols, broker)

        # 매크로 시장 환경 분석 (yfinance 기반)
        try:
            macro_result = analyzer.analyze_macro()
            if macro_result:
                result['macro'] = macro_result
                logger.info(
                    f"매크로 분석 완료: "
                    f"지수 {len(macro_result.get('indices', {}))}개, "
                    f"섹터 {len(macro_result.get('sectors', {}))}개"
                )
            else:
                logger.info("매크로 분석 건너뜀 (yfinance 미설치 또는 데이터 없음)")
        except Exception as e:
            logger.warning(f"매크로 분석 실패 (개별 종목 분석은 정상): {e}")

        # 5-Layer Market Intelligence (v2)
        try:
            from trading_bot.market_intelligence import MarketIntelligence
            mi = MarketIntelligence()
            intel_report = mi.analyze(
                stock_symbols=symbols,
                stocks_data=result.get('stocks', {}),
                news_data=result.get('news'),
                fear_greed_data=result.get('fear_greed_index'),
                pcr_data=result.get('pcr'),
            )
            result['intelligence'] = intel_report
            logger.info(
                f"5-Layer Intelligence: "
                f"score={intel_report['overall']['score']}, "
                f"signal={intel_report['overall']['signal']}"
            )
        except ImportError:
            logger.info("MarketIntelligence not available - skipping")
        except Exception as e:
            logger.warning(f"Market Intelligence failed (analysis continues): {e}")

        # 시그널 성과 추적 (v2)
        if os.getenv('SIGNAL_TRACKING_ENABLED', 'true').lower() == 'true':
            try:
                from trading_bot.signal_tracker import SignalTracker
                tracker = SignalTracker()
                count = tracker.log_daily_signals(result)
                logger.info(f"시그널 기록: {count}건")
                updated = tracker.update_pending_outcomes()
                logger.info(f"과거 시그널 성과 측정: {updated}건 업데이트")
                tracker.calculate_accuracy_stats(
                    result.get('date', datetime.now().strftime('%Y-%m-%d'))
                )
            except Exception as e:
                logger.warning(f"시그널 추적 실패 (분석 계속): {e}")

        # JSON 저장
        json_path = analyzer.save_json(result)
        logger.info(f"분석 결과 저장: {json_path}")

        # Pine Script 자동 생성
        try:
            from scripts.generate_pine_script import generate_pine_scripts
            pine_files = generate_pine_scripts(Path(json_path), slack=bool(state.notifier.slack_bot_token))
            if pine_files:
                logger.info(f"Pine Script 생성 완료: {[str(f) for f in pine_files]}")
        except Exception as e:
            logger.warning(f"Pine Script 생성 실패 (무시): {e}")

        # Slack 알림
        macro_status = "포함" if 'macro' in result else "미포함"
        state.notifier.send_slack(
            f"*시장 분석 데이터 수집 완료*\n\n"
            f"분석 종목: {', '.join(symbols)}\n"
            f"매크로 분석: {macro_status}\n"
            f"결과 파일: {json_path}\n"
            f"노션 작성은 호스트 cron에서 처리됩니다",
            color='good'
        )

    except Exception as e:
        logger.error(f"시장 분석 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"시장 분석 실패: {e}", context="시장 분석")


def run_kr_market_analysis():
    """
    한국 장 마감 후 시장 분석: KRMarketAnalyzer로 데이터 수집 + JSON 저장.
    15:50 KST 실행 (장 마감 20분 후).
    """
    logger.info("=" * 60)
    logger.info("한국 시장 분석 시작...")
    logger.info("=" * 60)

    if not _is_kr_trading_day():
        return

    if not state._has_kr_market_analyzer:
        logger.warning("KRMarketAnalyzer 모듈 미설치 - 한국 시장 분석 건너뜀")
        return

    # 환경 변수에서 설정 읽기
    enabled = os.getenv('KR_SCHEDULER_ENABLED', 'false').strip().lower()
    if enabled not in ('true', '1', 'yes'):
        logger.info("KR_SCHEDULER_ENABLED=false - 한국 시장 분석 비활성화됨")
        return

    symbols_str = os.getenv(
        'KR_MARKET_ANALYSIS_SYMBOLS',
        '005930,000660,005380,035420,035720,006400,373220,005490,105560,207940'
    )
    symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]

    try:
        # 브로커 초기화
        broker = _create_kis_broker()
        if not broker:
            logger.error("KIS 브로커 초기화 실패 - 한국 시장 분석 불가")
            state.notifier.notify_error("KIS 브로커 초기화 실패", context="한국 시장 분석")
            return

        # KRMarketAnalyzer로 데이터 수집
        analyzer = state.KRMarketAnalyzer()
        logger.info(f"한국 시장 분석 대상 종목: {', '.join(symbols)}")
        result = analyzer.analyze(symbols, broker)

        # JSON 저장 ({date}_kr.json)
        json_path = analyzer.save_json(result)
        logger.info(f"한국 시장 분석 결과 저장: {json_path}")

        # Slack 알림
        state.notifier.send_slack(
            f"*한국 시장 분석 데이터 수집 완료*\n\n"
            f"분석 종목: {', '.join(symbols)}\n"
            f"결과 파일: {json_path}\n"
            f"노션 작성은 호스트 cron에서 처리됩니다",
            color='good'
        )

    except Exception as e:
        logger.error(f"한국 시장 분석 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"한국 시장 분석 실패: {e}", context="한국 시장 분석")


def run_weekly_optimization():
    """주간 전략 최적화 (일요일 00:00 KST).

    AUTO_OPTIMIZATION_ENABLED=true 시 활성화.
    모든 프리셋을 대상으로 walk-forward 최적화 실행 후
    개선된 파라미터를 프리셋에 자동 반영.
    """
    if os.getenv('AUTO_OPTIMIZATION_ENABLED', 'false').strip().lower() not in ('true', '1'):
        return

    logger.info("=" * 60)
    logger.info("주간 전략 자동 최적화 시작...")
    logger.info("=" * 60)

    try:
        from trading_bot.auto_optimizer import AutoOptimizer
        from trading_bot.optimizer import StrategyOptimizer

        # 브로커 초기화
        if state.ctx.global_broker is not None:
            broker = state.ctx.global_broker
        else:
            broker = _create_kis_broker()
        if not broker:
            logger.error("주간 최적화: 브로커 초기화 실패")
            return

        optimizer = StrategyOptimizer()
        auto_opt = AutoOptimizer(
            optimizer=optimizer,
            preset_manager=state.preset_manager,
            strategy_class_map=state.STRATEGY_CLASS_MAP,
        )

        # 모든 프리셋 이름 수집
        target_presets = [p['name'] for p in state.preset_manager.list_presets()]
        if not target_presets:
            logger.info("주간 최적화: 프리셋 없음, 건너뜀")
            return

        result = auto_opt.run(broker=broker, target_presets=target_presets)

        # DB 기록
        if state.ctx.global_db and result.get('runs'):
            for run in result['runs']:
                state.ctx.global_db.log_optimization_run(run)

        logger.info(f"주간 최적화 완료: {result.get('summary', '')}")
        state.notifier.send_slack(
            f"*주간 전략 최적화 완료*\n{result.get('summary', '결과 없음')}",
            color='good'
        )

    except Exception as e:
        logger.error(f"주간 최적화 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"주간 최적화 실패: {e}", context="주간 최적화")


# ============================================================
# Live Trading Session Management
# ============================================================


def _run_live_trader_thread(label: str, trader):
    """
    daemon thread에서 실행되는 라이브 트레이딩 루프

    Args:
        label: 세션 라벨
        trader: LiveTrader 인스턴스
    """
    log_prefix = f"[live:{label}]"
    try:
        trader.run_realtime(interval_seconds=60, timeframe='1h')
    except Exception as e:
        logger.error(f"{log_prefix} 라이브 트레이딩 루프 오류: {e}", exc_info=True)
    finally:
        logger.info(f"{log_prefix} 라이브 트레이딩 루프 종료됨")


def _start_single_live_session(label: str, config: Optional[Dict]):
    """
    단일 라이브 트레이딩 세션을 daemon thread로 시작하는 헬퍼.
    _start_single_session()의 라이브 버전.

    Args:
        label: 세션 라벨
        config: 프리셋 설정 dict 또는 None
    """
    log_prefix = f"[live:{label}]"

    if not _has_live_trader:
        logger.error(f"{log_prefix} LiveTrader 모듈 미설치 - 라이브 세션 시작 불가")
        return

    # LIVE_TRADING_MODE 검증 (dry_run 또는 live만 허용)
    live_mode = os.getenv('LIVE_TRADING_MODE', 'dry_run').strip().lower()
    if live_mode not in ('dry_run', 'live'):
        logger.warning(f"{log_prefix} LIVE_TRADING_MODE='{live_mode}' 유효하지 않음 -> 'dry_run'으로 기본값 사용")
        live_mode = 'dry_run'

    try:
        # 브로커 초기화 (공유 브로커가 있으면 재사용)
        if state.ctx.global_broker is not None:
            broker = state.ctx.global_broker
            logger.info(f"{log_prefix} 공유 브로커 재사용")
        else:
            broker = _create_kis_broker()
        if not broker:
            logger.error(f"{log_prefix} KIS 브로커 초기화 실패 - 라이브 세션을 시작할 수 없습니다")
            state.notifier.notify_error("KIS 브로커 초기화 실패", context=f"라이브 세션 시작: {label}")
            return

        # 데이터베이스 초기화
        db = TradingDatabase()

        # 기본 설정 (Top 10 US Market Cap)
        strategy_name = "RSI+MACD Combo Strategy"
        strategy_params = None
        symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT']
        initial_capital = 10000.0
        position_size = 0.1
        stop_loss_pct = 0.03
        take_profit_pct = 0.05
        enable_stop_loss = True
        enable_take_profit = True

        # 프리셋에서 설정 적용
        if config:
            strategy_name = config.get('strategy', strategy_name)
            strategy_params = config.get('strategy_params')
            symbols = config.get('symbols', symbols)
            initial_capital = config.get('initial_capital', initial_capital)
            position_size = config.get('position_size', position_size)
            stop_loss_pct = config.get('stop_loss_pct', stop_loss_pct)
            take_profit_pct = config.get('take_profit_pct', take_profit_pct)
            enable_stop_loss = config.get('enable_stop_loss', enable_stop_loss)
            enable_take_profit = config.get('enable_take_profit', enable_take_profit)
            logger.info(f"{log_prefix} 프리셋 설정 적용됨: {config.get('_preset_name', label)}")

        # 전략 클래스 결정
        strategy_class = state.STRATEGY_CLASS_MAP.get(strategy_name, state.STRATEGY_CLASS_MAP['RSI+MACD Combo Strategy'])

        # 전략 생성 (프리셋 파라미터 > 기본값)
        if config and strategy_params:
            logger.info(f"{log_prefix} 프리셋 파라미터 사용: {strategy_params}")
            strategy = strategy_class(**strategy_params)
        else:
            logger.info(f"{log_prefix} 기본 파라미터 사용 (프리셋 없음) - {strategy_name}")
            strategy = strategy_class()

        logger.info(f"{log_prefix} 전략: {strategy.name}")
        logger.info(f"{log_prefix} 종목: {', '.join(symbols)}")

        # display_name 생성
        display_name = generate_display_name(
            strategy_name=strategy.name,
            symbols=symbols,
            preset_name=label if config else None
        )

        # 환경 변수에서 라이브 트레이딩 설정 로드
        max_daily_loss_pct = float(os.getenv('LIVE_TRADING_MAX_DAILY_LOSS_PCT', '0.05'))
        max_daily_trades = int(os.getenv('LIVE_TRADING_MAX_DAILY_TRADES', '50'))
        max_position_count = int(os.getenv('LIVE_TRADING_MAX_POSITION_COUNT', '10'))

        # Adaptive strategy manager (프리셋에 adaptive_regime_switching=true 시)
        adaptive_manager = None
        if config and config.get('adaptive_regime_switching') and state.global_regime_detector:
            try:
                from trading_bot.adaptive_strategy_manager import AdaptiveStrategyManager
                _adapter = None
                if config.get('adaptive_parameters'):
                    from trading_bot.parameter_adapter import ParameterAdapter
                    _adapter = ParameterAdapter(
                        base_strategy_params=strategy_params or strategy.get_params(),
                        base_stop_loss_pct=stop_loss_pct,
                        base_take_profit_pct=take_profit_pct,
                    )
                adaptive_manager = AdaptiveStrategyManager(
                    strategy_class_map=state.STRATEGY_CLASS_MAP,
                    regime_detector=state.global_regime_detector,
                    initial_strategy=strategy,
                    regime_strategy_map=config.get('regime_strategy_map') or None,
                    default_params=config.get('default_params_per_strategy') or {},
                    parameter_adapter=_adapter,
                )
                logger.info(f"{log_prefix} 적응형 전략 관리자 활성화 (파라미터 적응: {config.get('adaptive_parameters', False)})")
            except Exception as e:
                logger.warning(f"{log_prefix} 적응형 전략 관리자 초기화 실패: {e}")

        # LiveTrader 생성
        LiveTrader = state.LiveTrader
        trader = LiveTrader(
            strategy=strategy,
            symbols=symbols,
            broker=broker,
            initial_capital=initial_capital,
            position_size=position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
            db=db,
            display_name=display_name,
            regime_detector=state.global_regime_detector,
            llm_client=state.global_llm_client,
            notifier=state.notifier,
            mode=live_mode,
            max_daily_loss_pct=max_daily_loss_pct,
            max_daily_trades=max_daily_trades,
            max_position_count=max_position_count,
            adaptive_manager=adaptive_manager,
        )

        logger.info(f"{log_prefix} LiveTrader 초기화 완료 (mode={live_mode})")
        logger.info(f"{log_prefix}   초기 자본: ${initial_capital:,.2f}")
        logger.info(f"{log_prefix}   포지션 크기: {position_size:.0%}")
        logger.info(f"{log_prefix}   손절매: {stop_loss_pct:.0%} ({'활성' if enable_stop_loss else '비활성'})")
        logger.info(f"{log_prefix}   익절매: {take_profit_pct:.0%} ({'활성' if enable_take_profit else '비활성'})")
        logger.info(f"{log_prefix}   일일 손실 한도: {max_daily_loss_pct:.0%}")

        # 세션 시작 알림
        state.notifier.notify_session_start({
            'strategy_name': f"[LIVE:{live_mode}] {display_name}",
            'symbols': symbols,
            'initial_capital': initial_capital
        })

        # daemon thread로 라이브 트레이딩 시작
        def run_trading():
            _run_live_trader_thread(label, trader)

        thread = threading.Thread(target=run_trading, name=f"live-trader-{label}", daemon=True)

        with state.traders_lock:
            state.ctx.active_live_traders[label] = trader
            state.ctx.live_trader_threads[label] = thread
        thread.start()

        logger.info(f"{log_prefix} 라이브 트레이딩 루프 시작 (60초 간격, 1시간봉)...")

    except Exception as e:
        logger.error(f"{log_prefix} 라이브 트레이딩 시작 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"라이브 트레이딩 시작 실패: {e}", context=f"라이브 세션: {label}")
        with state.traders_lock:
            state.ctx.active_live_traders.pop(label, None)
            state.ctx.live_trader_threads.pop(label, None)


def start_live_trading():
    """
    라이브 트레이딩 세션 시작.
    장 시작 시각에 호출되며, 프리셋 기반으로 세션을 생성합니다.
    """
    if not _has_live_trader:
        return

    if os.getenv('LIVE_TRADING_ENABLED', 'false').strip().lower() != 'true':
        return

    # 킬스위치 확인
    try:
        if state.ctx.global_db.get_live_state('kill_switch_active') == 'true':
            reason = state.ctx.global_db.get_live_state('kill_switch_reason') or 'unknown'
            logger.warning(f"Kill switch active ({reason}), skipping live trading")
            return
    except (AttributeError, Exception):
        pass

    if not _is_trading_day():
        return

    logger.info("=" * 60)
    logger.info("라이브 트레이딩 세션 시작...")
    logger.info("=" * 60)

    if state.preset_configs:
        logger.info(f"총 {len(state.preset_configs)}개 프리셋 라이브 세션 시작")

        # 멀티 프리셋: 공유 브로커를 한 번만 생성
        if len(state.preset_configs) > 1 and state.ctx.global_broker is None:
            shared = _create_kis_broker()
            if shared:
                state.ctx.global_broker = shared
                logger.info("멀티 프리셋용 공유 브로커 초기화 완료")

        for cfg in state.preset_configs:
            label = cfg.get('_preset_name', 'unknown')
            _start_single_live_session(label, cfg)
    else:
        _start_single_live_session("기본", None)

    with state.traders_lock:
        logger.info(f"활성 라이브 세션 수: {len(state.ctx.active_live_traders)}")


def _stop_single_live_session(label: str):
    """
    단일 라이브 트레이딩 세션 중지 및 리포트 생성 헬퍼.
    _stop_single_session()의 라이브 버전.

    Args:
        label: 세션 라벨
    """
    log_prefix = f"[live:{label}]"

    with state.traders_lock:
        trader = state.ctx.active_live_traders.pop(label, None)
        thread = state.ctx.live_trader_threads.pop(label, None)

    if trader is None:
        logger.warning(f"{log_prefix} 중지할 라이브 세션 없음")
        return

    try:
        trader.is_running = False
        trader._stop_event.set()

        logger.info(f"{log_prefix} 라이브 트레이딩 루프 종료 대기 중...")
        if thread and thread.is_alive():
            thread.join(timeout=30)
            if thread.is_alive():
                logger.warning(f"{log_prefix} 라이브 스레드가 30초 내에 종료되지 않음")
            else:
                logger.info(f"{log_prefix} 라이브 스레드 정상 종료")
        else:
            exited = trader._loop_exited.wait(timeout=30)
            if exited:
                logger.info(f"{log_prefix} 라이브 트레이딩 루프 정상 종료")
            else:
                logger.warning(f"{log_prefix} 라이브 트레이딩 루프가 30초 내에 종료되지 않음")

        trader.stop()

        # 세션 요약 및 리포트
        if trader.session_id and trader.db:
            summary = trader.db.get_live_session(trader.session_id)

            if summary:
                logger.info(f"{log_prefix} 라이브 세션 중지 성공")
                logger.info(f"{log_prefix}   세션 ID: {trader.session_id}")
                logger.info(f"{log_prefix}   모드: {summary.get('mode', 'unknown')}")
                if summary.get('final_capital') is not None:
                    logger.info(f"{log_prefix}   최종 자본: ${summary['final_capital']:,.2f}")
                if summary.get('total_return') is not None:
                    logger.info(f"{log_prefix}   총 수익률: {summary['total_return']:.2f}%")

                # 리포트 생성
                try:
                    report_gen = ReportGenerator(trader.db)
                    report_files = report_gen.generate_session_report(
                        trader.session_id,
                        output_dir='reports/',
                        formats=['csv', 'json']
                    )

                    logger.info(f"{log_prefix} 리포트 생성 완료:")
                    for format_name, file_path in report_files.items():
                        logger.info(f"{log_prefix}   {format_name.upper()}: {file_path}")

                    # Slack 업로드
                    file_paths = list(report_files.values())
                    upload_success = state.notifier.notify_daily_report_with_files(
                        session_summary={
                            'strategy_name': f"[LIVE] {summary.get('display_name') or label}",
                            'total_return': summary.get('total_return', 0.0) or 0.0,
                            'sharpe_ratio': summary.get('sharpe_ratio', 0.0) or 0.0,
                            'max_drawdown': summary.get('max_drawdown', 0.0) or 0.0,
                            'win_rate': summary.get('win_rate', 0.0) or 0.0,
                            'num_trades': len(trader.db.get_live_orders(trader.session_id))
                        },
                        report_files=file_paths
                    )

                    if upload_success:
                        logger.info(f"{log_prefix} Slack 리포트 업로드 완료")
                    else:
                        logger.warning(f"{log_prefix} Slack 리포트 업로드 실패")

                except Exception as e:
                    logger.error(f"{log_prefix} 리포트 생성 실패: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"{log_prefix} 라이브 세션 중지 실패: {e}", exc_info=True)
        state.notifier.notify_error(f"라이브 세션 중지 실패: {e}", context=f"라이브 장 마감: {label}")


def stop_live_trading():
    """
    모든 라이브 트레이딩 세션 중지 및 리포트 생성.
    장 마감 시각에 호출됩니다.
    """
    logger.info("=" * 60)
    logger.info("모든 라이브 트레이딩 세션 중지 중...")
    logger.info("=" * 60)

    with state.traders_lock:
        labels = list(state.ctx.active_live_traders.keys())

    if not labels:
        logger.info("중지할 활성 라이브 세션 없음")
        return

    logger.info(f"총 {len(labels)}개 라이브 세션 중지 시작")

    for label in labels:
        _stop_single_live_session(label)

    logger.info(f"전체 {len(labels)}개 라이브 세션 중지 완료")
