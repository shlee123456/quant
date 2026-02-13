"""
Dashboard Integrated Scheduler Manager

대시보드 내부에서 실행되는 스케줄러 관리 모듈
기존 scheduler.py의 로직을 대시보드에 통합

Features:
- APScheduler BackgroundScheduler 사용
- UI에서 스케줄 시작/중지
- 스케줄 시간 동적 설정
- 실시간 로그 표시
- 세션 상태 관리

Usage:
    from dashboard.scheduler_manager import SchedulerManager

    manager = SchedulerManager()
    manager.start()
    manager.stop()
    status = manager.get_status()
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, time
from typing import Optional, Dict, List, Callable
import pandas as pd
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, RSIMACDComboStrategy
from trading_bot.database import TradingDatabase
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.notifications import NotificationService
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.reports import ReportGenerator

logger = logging.getLogger(__name__)

# 전략 이름 → 클래스 매핑 (프리셋/STRATEGY_CONFIGS 양쪽 이름 모두 지원)
STRATEGY_CLASS_MAP = {
    'RSI Strategy': RSIStrategy,
    'MACD Strategy': MACDStrategy,
    'Bollinger Bands': BollingerBandsStrategy,
    'RSI+MACD Combo': RSIMACDComboStrategy,
    'RSI+MACD Combo Strategy': RSIMACDComboStrategy,
    'Moving Average Crossover': None,  # strategy.py에서 직접 import 필요
}


class SchedulerManager:
    """
    대시보드 통합 스케줄러 관리 클래스

    APScheduler BackgroundScheduler를 사용하여
    Streamlit 앱 내부에서 스케줄 작업 관리
    """

    def __init__(self):
        """Initialize scheduler manager"""
        self.scheduler: Optional[BackgroundScheduler] = None
        self.active_traders: Dict[str, PaperTrader] = {}  # session_id → PaperTrader
        self.notifier = NotificationService()
        self.preset_manager = StrategyPresetManager()
        self.optimized_params: Optional[Dict] = None
        self.logs: List[str] = []  # 로그 메시지 저장
        self.max_logs = 500  # 최대 로그 라인 수

        # 기본 스케줄 시간 (KST)
        self.schedule_config = {
            'optimize_time': time(23, 0),  # 23:00 KST
            'start_time': time(23, 30),     # 23:30 KST
            'stop_time': time(6, 0)         # 06:00 KST
        }

        # 스케줄러 설정
        self.strategy_name = "RSI+MACD Combo Strategy"
        self.strategy_params: Optional[Dict] = None  # 프리셋에서 로드된 전략 파라미터
        self.symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
        self.initial_capital = 10000.0
        self.position_size = 0.2
        self.stop_loss_pct = 0.03
        self.take_profit_pct = 0.05
        self.enable_stop_loss = True
        self.enable_take_profit = True
        self.loaded_preset_name: Optional[str] = None  # 현재 로드된 프리셋 이름

    def load_from_preset(self, preset_name: str) -> bool:
        """
        저장된 프리셋을 불러와 스케줄러 설정에 적용

        Args:
            preset_name: 불러올 프리셋 이름

        Returns:
            True if loaded successfully, False otherwise
        """
        preset = self.preset_manager.load_preset(preset_name)
        if not preset:
            self._add_log(f"✗ 프리셋 '{preset_name}'을 찾을 수 없습니다")
            return False

        self.strategy_name = preset['strategy']
        self.strategy_params = preset.get('strategy_params')
        self.symbols = preset.get('symbols', ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'])
        self.initial_capital = preset.get('initial_capital', 10000.0)
        self.position_size = preset.get('position_size', 0.2)
        self.stop_loss_pct = preset.get('stop_loss_pct', 0.03)
        self.take_profit_pct = preset.get('take_profit_pct', 0.05)
        self.enable_stop_loss = preset.get('enable_stop_loss', True)
        self.enable_take_profit = preset.get('enable_take_profit', True)
        self.loaded_preset_name = preset_name

        self._add_log(f"✓ 프리셋 '{preset_name}' 불러오기 완료")
        self._add_log(f"  전략: {self.strategy_name}")
        self._add_log(f"  종목: {', '.join(self.symbols)}")
        self._add_log(f"  초기 자본: ${self.initial_capital:,.2f}")
        self._add_log(f"  파라미터: {self.strategy_params}")

        return True

    def _create_strategy(self, params: Optional[Dict] = None):
        """
        전략 이름으로부터 전략 인스턴스 생성

        Args:
            params: 전략 파라미터 (None이면 기본값 사용)

        Returns:
            Strategy instance
        """
        strategy_class = STRATEGY_CLASS_MAP.get(self.strategy_name)

        if strategy_class is None:
            # Moving Average Crossover 처리
            if 'Moving Average' in self.strategy_name:
                from trading_bot.strategy import MovingAverageCrossover
                strategy_class = MovingAverageCrossover
            else:
                self._add_log(f"⚠ 알 수 없는 전략: {self.strategy_name}, RSI+MACD Combo 사용")
                strategy_class = RSIMACDComboStrategy

        if params:
            return strategy_class(**params)
        else:
            return strategy_class()

    def _add_log(self, message: str):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)

        # 최대 로그 수 제한
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

        logger.info(message)

    def get_logs(self, lines: int = 100) -> List[str]:
        """최근 로그 조회"""
        return self.logs[-lines:]

    def clear_logs(self):
        """로그 초기화"""
        self.logs = []

    def optimize_strategy(self):
        """
        전략 최적화 작업 (23:00 KST)
        """
        self._add_log("=" * 60)
        self._add_log("전략 최적화 시작...")
        self._add_log("=" * 60)

        try:
            # 최적화용 다양한 시장 상황 데이터 생성
            data_gen = SimulationDataGenerator(seed=42)
            df_bullish = data_gen.generate_trend_data(periods=200, trend='bullish', initial_price=150.0)
            df_bearish = data_gen.generate_trend_data(periods=200, trend='bearish', initial_price=150.0)
            df_sideways = data_gen.generate_trend_data(periods=200, trend='sideways', initial_price=150.0)
            df = pd.concat([df_bullish, df_bearish, df_sideways], ignore_index=True)

            self._add_log(f"최적화 데이터: 상승({len(df_bullish)}) + 하락({len(df_bearish)}) + 횡보({len(df_sideways)}) = {len(df)}개")

            # RSI+MACD 복합 전략 파라미터 그리드
            param_grid = {
                'rsi_period': [10, 12, 14],
                'rsi_overbought': [70, 75, 78],
                'rsi_oversold': [30, 35, 38],
                'macd_fast': [8, 12],
                'macd_slow': [21, 26],
                'macd_signal': [9]
            }

            # 최적화 실행
            optimizer = StrategyOptimizer(initial_capital=10000.0)
            self._add_log("RSI+MACD 복합 전략 그리드 서치 최적화 실행 중...")
            best_result = optimizer.optimize(RSIMACDComboStrategy, df, param_grid)

            self._add_log(f"✓ 최적화 완료!")
            self._add_log(f"  최적 파라미터: {best_result['params']}")
            self._add_log(f"  샤프 비율: {best_result['sharpe_ratio']:.2f}")
            self._add_log(f"  총 수익률: {best_result['total_return']:.2f}%")

            # 알림 전송
            self.notifier.send_slack(
                f"📊 *전략 최적화 완료*\n\n"
                f"최적 파라미터: {best_result['params']}\n"
                f"샤프 비율: {best_result['sharpe_ratio']:.2f}\n"
                f"총 수익률: {best_result['total_return']:.2f}%",
                color='good'
            )

            # 최적 파라미터 저장
            self.optimized_params = best_result['params']

            # 프리셋으로 저장
            preset_name = f"자동최적화_{datetime.now().strftime('%Y%m%d_%H%M')}"
            self.preset_manager.save_preset(
                name=preset_name,
                description=f"자동 최적화 결과 (Sharpe: {best_result['sharpe_ratio']:.2f})",
                strategy="RSI+MACD Combo Strategy",
                strategy_params=best_result['params'],
                symbols=self.symbols,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
                enable_stop_loss=True,
                enable_take_profit=True
            )

            self._add_log(f"✓ 최적 파라미터 프리셋 저장: {preset_name}")

        except Exception as e:
            self._add_log(f"✗ 최적화 실패: {e}")
            self.notifier.notify_error(f"전략 최적화 실패: {e}", context="장전 작업")

    def start_paper_trading(self):
        """
        페이퍼 트레이딩 시작 (23:30 KST)

        새 세션을 생성하여 active_traders에 추가합니다.
        기존 세션은 유지됩니다.
        """
        self._add_log("=" * 60)
        self._add_log("페이퍼 트레이딩 세션 시작...")
        self._add_log("=" * 60)

        try:
            # 브로커 초기화 (실제 환경에서는 필요)
            from dashboard.kis_broker import get_kis_broker
            broker = get_kis_broker()

            if not broker:
                self._add_log("⚠ KIS 브로커 초기화 실패 - 시뮬레이션 모드로 전환")
                broker = None

            # 데이터베이스 초기화
            db = TradingDatabase()

            # 전략 생성 (우선순위: 최적화 결과 > 프리셋 파라미터 > 기본값)
            if self.optimized_params:
                self._add_log(f"최적화된 파라미터 사용: {self.optimized_params}")
                strategy = self._create_strategy(self.optimized_params)
            elif self.strategy_params:
                self._add_log(f"프리셋 파라미터 사용: {self.strategy_params}")
                strategy = self._create_strategy(self.strategy_params)
            else:
                self._add_log(f"기본 파라미터 사용 (최적화/프리셋 없음) - {self.strategy_name}")
                strategy = self._create_strategy()

            self._add_log(f"전략: {strategy.name}")
            self._add_log(f"종목: {', '.join(self.symbols)}")

            # 페이퍼 트레이더 생성
            trader = PaperTrader(
                strategy=strategy,
                symbols=self.symbols,
                broker=broker,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
                enable_stop_loss=self.enable_stop_loss,
                enable_take_profit=self.enable_take_profit,
                db=db
            )

            # Attach notifier
            trader.notifier = self.notifier

            # active_traders에 추가
            session_id = trader.session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.active_traders[session_id] = trader

            self._add_log("✓ 페이퍼 트레이더 초기화 완료")
            self._add_log(f"  세션 ID: {session_id}")
            self._add_log(f"  초기 자본: ${trader.initial_capital:,.2f}")
            self._add_log(f"  포지션 크기: {trader.position_size:.0%}")
            self._add_log(f"  활성 세션 수: {len(self.active_traders)}")

            # 세션 시작 알림
            self.notifier.notify_session_start({
                'strategy_name': strategy.name,
                'symbols': self.symbols,
                'initial_capital': trader.initial_capital
            })

            # 백그라운드 스레드로 실시간 트레이딩 시작
            def run_trading():
                try:
                    self._add_log(f"[{session_id[:8]}] 실시간 트레이딩 루프 시작 (60초 간격, 1시간봉)...")
                    trader.run_realtime(interval_seconds=60, timeframe='1h')
                except Exception as e:
                    self._add_log(f"✗ [{session_id[:8]}] 트레이딩 루프 오류: {e}")

            trading_thread = threading.Thread(target=run_trading, daemon=True)
            trading_thread.start()

        except Exception as e:
            self._add_log(f"✗ 페이퍼 트레이딩 실패: {e}")
            self.notifier.notify_error(f"페이퍼 트레이딩 실패: {e}", context="트레이딩 세션")

    def _stop_trader(self, session_id: str, trader: PaperTrader):
        """
        단일 트레이더 중지 및 리포트 생성 (내부 헬퍼)

        Args:
            session_id: 세션 ID
            trader: PaperTrader 인스턴스
        """
        try:
            trader.stop()

            if trader.session_id and trader.db:
                summary = trader.db.get_session_summary(trader.session_id)

                if summary:
                    self._add_log(f"✓ 세션 중지 성공: {session_id[:12]}")
                    self._add_log(f"  최종 자본: ${summary['final_capital']:,.2f}")
                    self._add_log(f"  총 수익률: {summary['total_return']:.2f}%")
                    self._add_log(f"  샤프 비율: {summary['sharpe_ratio']:.2f}")
                    self._add_log(f"  최대 낙폭: {summary['max_drawdown']:.2f}%")

                    trades = trader.db.get_session_trades(trader.session_id)
                    self._add_log(f"  총 거래: {len(trades)}회")

                    # 리포트 생성 및 Slack 업로드
                    try:
                        report_gen = ReportGenerator(trader.db)
                        report_files = report_gen.generate_session_report(
                            trader.session_id,
                            output_dir='reports/',
                            formats=['csv', 'json']
                        )

                        self._add_log("✓ 리포트 생성 완료:")
                        for format_name, file_path in report_files.items():
                            self._add_log(f"  {format_name.upper()}: {file_path}")

                        file_paths = list(report_files.values())
                        upload_success = self.notifier.notify_daily_report_with_files(
                            session_summary={
                                'strategy_name': summary.get('strategy_name', 'Unknown'),
                                'total_return': summary['total_return'],
                                'sharpe_ratio': summary['sharpe_ratio'],
                                'max_drawdown': summary['max_drawdown'],
                                'win_rate': summary['win_rate'] if summary['win_rate'] is not None else 0.0,
                                'num_trades': len(trades)
                            },
                            report_files=file_paths
                        )

                        if upload_success:
                            self._add_log("✓ Slack 리포트 업로드 완료")
                        else:
                            self._add_log("⚠ Slack 리포트 업로드 실패")

                    except Exception as e:
                        self._add_log(f"✗ 리포트 생성 실패: {e}")

        except Exception as e:
            self._add_log(f"✗ 세션 {session_id[:12]} 중지 실패: {e}")

    def stop_paper_trading(self):
        """
        모든 페이퍼 트레이딩 세션 중지 (06:00 KST 스케줄 또는 전체 중지)
        """
        self._add_log("=" * 60)
        self._add_log("모든 페이퍼 트레이딩 세션 중지 중...")
        self._add_log("=" * 60)

        if not self.active_traders:
            self._add_log("⚠ 중지할 활성 트레이딩 세션 없음")
            return

        session_ids = list(self.active_traders.keys())
        for session_id in session_ids:
            trader = self.active_traders.pop(session_id, None)
            if trader:
                self._stop_trader(session_id, trader)

        self._add_log(f"✓ 전체 {len(session_ids)}개 세션 중지 완료")

    def stop_single_session(self, session_id: str) -> bool:
        """
        특정 세션만 중지

        Args:
            session_id: 중지할 세션 ID

        Returns:
            True if stopped, False if session not found
        """
        trader = self.active_traders.pop(session_id, None)
        if trader is None:
            self._add_log(f"⚠ 세션 '{session_id[:12]}' 을 찾을 수 없습니다")
            return False

        self._add_log(f"세션 '{session_id[:12]}' 개별 중지 중...")
        self._stop_trader(session_id, trader)
        self._add_log(f"남은 활성 세션: {len(self.active_traders)}개")
        return True

    def start_manual_session(self) -> Optional[str]:
        """
        UI에서 즉시 세션을 추가하는 메서드

        현재 설정(프리셋/수동)으로 새 세션을 즉시 시작합니다.
        스케줄 cron과 무관하게 호출 가능합니다.

        Returns:
            생성된 session_id 또는 실패 시 None
        """
        self._add_log("수동 세션 추가 시작...")
        trader_count_before = len(self.active_traders)
        self.start_paper_trading()
        if len(self.active_traders) > trader_count_before:
            # 가장 최근 추가된 세션 ID 반환
            latest_id = list(self.active_traders.keys())[-1]
            return latest_id
        return None

    def start(self) -> Dict[str, any]:
        """
        스케줄러 시작

        Returns:
            Dict with success, message, error
        """
        if self.scheduler is not None:
            return {
                'success': False,
                'message': '스케줄러가 이미 실행 중입니다.',
                'error': None
            }

        try:
            # BackgroundScheduler 생성
            self.scheduler = BackgroundScheduler(timezone='Asia/Seoul')

            # 작업 추가
            self.scheduler.add_job(
                self.optimize_strategy,
                CronTrigger(
                    hour=self.schedule_config['optimize_time'].hour,
                    minute=self.schedule_config['optimize_time'].minute
                ),
                id='optimize_strategy',
                name='전략 최적화',
                misfire_grace_time=300
            )

            self.scheduler.add_job(
                self.start_paper_trading,
                CronTrigger(
                    hour=self.schedule_config['start_time'].hour,
                    minute=self.schedule_config['start_time'].minute
                ),
                id='start_trading',
                name='페이퍼 트레이딩 시작',
                misfire_grace_time=300
            )

            self.scheduler.add_job(
                self.stop_paper_trading,
                CronTrigger(
                    hour=self.schedule_config['stop_time'].hour,
                    minute=self.schedule_config['stop_time'].minute
                ),
                id='stop_trading',
                name='페이퍼 트레이딩 중지',
                misfire_grace_time=300
            )

            # 스케줄러 시작
            self.scheduler.start()

            self._add_log("=" * 60)
            self._add_log("✓ 스케줄러 시작 성공")
            self._add_log("=" * 60)
            self._add_log(f"전략 최적화: {self.schedule_config['optimize_time'].strftime('%H:%M')} KST")
            self._add_log(f"트레이딩 시작: {self.schedule_config['start_time'].strftime('%H:%M')} KST")
            self._add_log(f"트레이딩 중지: {self.schedule_config['stop_time'].strftime('%H:%M')} KST")

            return {
                'success': True,
                'message': '스케줄러가 성공적으로 시작되었습니다.',
                'error': None
            }

        except Exception as e:
            self._add_log(f"✗ 스케줄러 시작 실패: {e}")
            return {
                'success': False,
                'message': '스케줄러 시작 실패',
                'error': str(e)
            }

    def stop(self) -> Dict[str, any]:
        """
        스케줄러 중지

        Returns:
            Dict with success, message, error
        """
        if self.scheduler is None:
            return {
                'success': False,
                'message': '실행 중인 스케줄러가 없습니다.',
                'error': None
            }

        try:
            # 실행 중인 트레이딩 세션도 모두 중지
            if self.active_traders:
                self.stop_paper_trading()

            # 스케줄러 중지
            self.scheduler.shutdown(wait=False)
            self.scheduler = None

            self._add_log("✓ 스케줄러 중지됨")

            return {
                'success': True,
                'message': '스케줄러가 성공적으로 중지되었습니다.',
                'error': None
            }

        except Exception as e:
            self._add_log(f"✗ 스케줄러 중지 실패: {e}")
            return {
                'success': False,
                'message': '스케줄러 중지 실패',
                'error': str(e)
            }

    def get_active_sessions_info(self) -> List[Dict]:
        """
        활성 세션 목록 상세 정보 (인메모리 + DB 통합)

        대시보드 내부에서 시작한 세션(인메모리)과
        Docker 스케줄러 컨테이너에서 시작한 세션(DB)을 모두 반환합니다.

        Returns:
            List of dicts with session_id, strategy_name, symbols, start_time
        """
        sessions = []
        in_memory_ids = set()

        # 1) 인메모리 활성 세션 (대시보드에서 시작한 세션)
        for session_id, trader in self.active_traders.items():
            in_memory_ids.add(session_id)
            sessions.append({
                'session_id': session_id,
                'strategy_name': trader.strategy.name if trader.strategy else 'Unknown',
                'symbols': getattr(trader, 'symbols', []),
                'start_time': getattr(trader, 'start_time', None),
                'initial_capital': getattr(trader, 'initial_capital', 0),
                'source': 'dashboard',
            })

        # 2) DB에서 active 세션 조회 (Docker 스케줄러 등 외부에서 시작한 세션)
        try:
            db = TradingDatabase()
            db_sessions = db.get_all_sessions(status_filter='active')
            for s in db_sessions:
                if s['session_id'] not in in_memory_ids:
                    sessions.append({
                        'session_id': s['session_id'],
                        'strategy_name': s['strategy_name'],
                        'symbols': [],  # DB에 별도 저장 안 됨
                        'start_time': s.get('start_time'),
                        'initial_capital': s.get('initial_capital', 0),
                        'display_name': s.get('display_name'),
                        'source': 'external',
                    })
        except Exception as e:
            logger.warning(f"DB 세션 조회 실패: {e}")

        return sessions

    def get_status(self) -> Dict[str, any]:
        """
        스케줄러 상태 조회

        Returns:
            Dict with running, jobs, next_run_time, active_session_count, active_sessions, etc.
        """
        active_sessions = self.get_active_sessions_info()

        if self.scheduler is None:
            return {
                'running': False,
                'jobs': [],
                'next_run_time': None,
                'trading_active': len(active_sessions) > 0,
                'active_session_count': len(active_sessions),
                'active_sessions': active_sessions,
                'error': None
            }

        try:
            jobs_info = []
            for job in self.scheduler.get_jobs():
                jobs_info.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                })

            return {
                'running': True,
                'jobs': jobs_info,
                'next_run_time': min([j['next_run_time'] for j in jobs_info if j['next_run_time']]) if jobs_info else None,
                'trading_active': len(active_sessions) > 0,
                'active_session_count': len(active_sessions),
                'active_sessions': active_sessions,
                'error': None
            }

        except Exception as e:
            return {
                'running': False,
                'jobs': [],
                'next_run_time': None,
                'trading_active': False,
                'active_session_count': 0,
                'active_sessions': [],
                'error': str(e)
            }

    def update_schedule(self, optimize_time: time, start_time: time, stop_time: time) -> Dict[str, any]:
        """
        스케줄 시간 업데이트

        Args:
            optimize_time: 최적화 시간
            start_time: 트레이딩 시작 시간
            stop_time: 트레이딩 중지 시간

        Returns:
            Dict with success, message, error
        """
        self.schedule_config['optimize_time'] = optimize_time
        self.schedule_config['start_time'] = start_time
        self.schedule_config['stop_time'] = stop_time

        # 스케줄러가 실행 중이면 재시작
        if self.scheduler is not None:
            self._add_log("스케줄 시간 변경 - 스케줄러 재시작 중...")
            self.stop()
            return self.start()
        else:
            self._add_log("스케줄 시간 업데이트됨 (스케줄러 미실행)")
            return {
                'success': True,
                'message': '스케줄 시간이 업데이트되었습니다.',
                'error': None
            }

    def update_strategy_config(self, strategy_name: str, symbols: List[str],
                               initial_capital: float, position_size: float,
                               stop_loss_pct: float, take_profit_pct: float):
        """전략 설정 업데이트"""
        self.strategy_name = strategy_name
        self.symbols = symbols
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        # 프리셋에서 로드한 파라미터 초기화 (수동 설정이므로)
        self.strategy_params = None
        self.loaded_preset_name = None

        self._add_log("전략 설정 업데이트됨 (수동)")
        self._add_log(f"  전략: {strategy_name}")
        self._add_log(f"  종목: {', '.join(symbols)}")
        self._add_log(f"  초기 자본: ${initial_capital:,.2f}")
        self._add_log(f"  포지션 크기: {position_size:.0%}")
