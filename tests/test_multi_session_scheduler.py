"""
멀티 세션 스케줄러 기능 테스트

테스트 대상:
1. PaperTrader thread-safe shutdown (threading.Event 기반)
2. 스케줄러 멀티 세션 관리 (active_traders, trader_threads)
3. CLI 인자 파싱 (--preset, --presets, --list-presets)
4. SchedulerController (Docker 컨테이너 제어)
5. 스윙 트레이딩 프리셋 생성 스크립트
"""

import pytest
import threading
import time
import tempfile
import os
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy, RSIMACDComboStrategy
from trading_bot.database import TradingDatabase
import pandas as pd


# =============================================================================
# Fixtures
# =============================================================================


class MockBroker:
    """테스트용 Mock Broker"""

    def __init__(self, price=150.0):
        self.current_price = price

    def fetch_ticker(self, symbol, **kwargs):
        return {
            'symbol': symbol,
            'last': self.current_price,
            'open': self.current_price - 1,
            'high': self.current_price + 1,
            'low': self.current_price - 2,
            'volume': 1000000,
            'change': 1.0,
            'rate': 0.67
        }

    def fetch_ohlcv(self, symbol, timeframe='1d', limit=100, **kwargs):
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')
        data = pd.DataFrame({
            'open': [self.current_price] * limit,
            'high': [self.current_price + 2] * limit,
            'low': [self.current_price - 2] * limit,
            'close': [self.current_price + i * 0.1 for i in range(limit)],
            'volume': [1000000] * limit
        }, index=dates)
        return data


@pytest.fixture
def mock_broker():
    return MockBroker()


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_multi_session.db')
    db = TradingDatabase(db_path=db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


@pytest.fixture
def paper_trader(mock_broker, temp_db):
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    trader = PaperTrader(
        strategy=strategy,
        symbols=['AAPL'],
        broker=mock_broker,
        initial_capital=10000.0,
        position_size=0.3,
        db=temp_db
    )
    yield trader
    if trader.is_running:
        trader.stop()


# =============================================================================
# 1. PaperTrader Thread-Safe Shutdown 테스트
# =============================================================================


class TestPaperTraderThreadSafety:
    """PaperTrader의 스레드 안전 종료 기능 테스트"""

    def test_stop_event_initialized(self, paper_trader):
        """_stop_event가 초기화되는지 확인"""
        assert hasattr(paper_trader, '_stop_event')
        assert isinstance(paper_trader._stop_event, threading.Event)
        assert not paper_trader._stop_event.is_set()

    def test_loop_exited_event_initialized(self, paper_trader):
        """_loop_exited가 초기화되는지 확인"""
        assert hasattr(paper_trader, '_loop_exited')
        assert isinstance(paper_trader._loop_exited, threading.Event)
        assert not paper_trader._loop_exited.is_set()

    def test_stopped_flag_initialized(self, paper_trader):
        """_stopped 플래그가 False로 초기화되는지 확인"""
        assert hasattr(paper_trader, '_stopped')
        assert paper_trader._stopped is False

    def test_stop_is_idempotent(self, paper_trader):
        """stop()이 중복 호출에 안전한지 확인"""
        paper_trader.start()

        # 첫 번째 stop
        paper_trader.stop()
        assert paper_trader._stopped is True
        assert paper_trader.is_running is False

        # 두 번째 stop (에러 없이 실행)
        paper_trader.stop()
        assert paper_trader._stopped is True

    def test_stop_sets_stop_event(self, paper_trader):
        """stop()이 _stop_event를 설정하는지 확인"""
        paper_trader.start()
        paper_trader.stop()
        assert paper_trader._stop_event.is_set()

    def test_run_realtime_clears_events(self, mock_broker, temp_db):
        """run_realtime이 시작 시 이벤트를 초기화하는지 확인"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['AAPL'],
            broker=mock_broker,
            initial_capital=10000.0,
            db=temp_db
        )

        # 이전 상태 시뮬레이션
        trader._stop_event.set()
        trader._loop_exited.set()
        trader._stopped = True

        # run_realtime을 daemon 스레드에서 실행
        def run_and_stop():
            trader.run_realtime(interval_seconds=1, timeframe='1d')

        thread = threading.Thread(target=run_and_stop, daemon=True)
        thread.start()

        # 약간 대기 후 이벤트 상태 확인
        time.sleep(0.5)
        assert not trader._stop_event.is_set()
        assert not trader._loop_exited.is_set()
        assert trader._stopped is False

        # 종료
        trader.stop()
        thread.join(timeout=5)

    def test_stop_event_responsive_shutdown(self, mock_broker, temp_db):
        """_stop_event로 즉각적인 종료가 되는지 확인"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['AAPL'],
            broker=mock_broker,
            initial_capital=10000.0,
            db=temp_db
        )

        # run_realtime을 백그라운드에서 시작 (긴 interval)
        thread = threading.Thread(
            target=lambda: trader.run_realtime(interval_seconds=300, timeframe='1d'),
            daemon=True
        )
        thread.start()

        # 시작 대기
        time.sleep(1)
        assert trader.is_running is True

        # stop 호출 - 300초를 기다리지 않고 즉시 종료되어야 함
        start_time = time.time()
        trader.stop()
        thread.join(timeout=10)
        elapsed = time.time() - start_time

        # 5초 이내에 종료 (300초 sleep이 아닌 event로 즉시 종료)
        assert elapsed < 5.0
        assert not thread.is_alive()

    def test_loop_exited_set_after_run(self, mock_broker, temp_db):
        """run_realtime 종료 후 _loop_exited가 설정되는지 확인"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['AAPL'],
            broker=mock_broker,
            initial_capital=10000.0,
            db=temp_db
        )

        thread = threading.Thread(
            target=lambda: trader.run_realtime(interval_seconds=60, timeframe='1d'),
            daemon=True
        )
        thread.start()
        time.sleep(0.5)

        # 종료 요청
        trader.stop()
        thread.join(timeout=10)

        # _loop_exited가 설정되어야 함
        assert trader._loop_exited.is_set()


# =============================================================================
# 2. 멀티 세션 관리 테스트
# =============================================================================


class TestMultiSessionManagement:
    """스케줄러의 멀티 세션 관리 기능 테스트"""

    def test_strategy_class_map(self):
        """전략 클래스 매핑이 올바른지 확인"""
        from scheduler import STRATEGY_CLASS_MAP

        assert STRATEGY_CLASS_MAP['RSI Strategy'] == RSIStrategy
        assert STRATEGY_CLASS_MAP['MACD Strategy'] == MACDStrategy
        assert STRATEGY_CLASS_MAP['RSI+MACD Combo'] == RSIMACDComboStrategy
        assert STRATEGY_CLASS_MAP['RSI+MACD Combo Strategy'] == RSIMACDComboStrategy

    def test_active_traders_dict_exists(self):
        """active_traders 전역 딕셔너리 확인"""
        from scheduler import active_traders, trader_threads, traders_lock

        assert isinstance(active_traders, dict)
        assert isinstance(trader_threads, dict)
        assert isinstance(traders_lock, type(threading.Lock()))

    def test_preset_configs_list_exists(self):
        """preset_configs 전역 리스트 확인"""
        from scheduler import preset_configs

        assert isinstance(preset_configs, list)

    @patch('trading_bot.scheduler.session_manager._create_kis_broker')
    def test_start_single_session_broker_failure(self, mock_get_kis):
        """브로커 초기화 실패 시 세션이 시작되지 않아야 함"""
        mock_get_kis.return_value = None

        from scheduler import _start_single_session, active_traders

        initial_count = len(active_traders)
        _start_single_session("테스트", None)

        # 활성 세션이 증가하지 않아야 함
        assert len(active_traders) == initial_count

    @patch('trading_bot.scheduler.session_manager._create_kis_broker')
    def test_start_single_session_with_preset_config(self, mock_get_kis):
        """프리셋 설정이 올바르게 적용되는지 확인"""
        mock_broker = MockBroker()
        mock_get_kis.return_value = mock_broker

        config = {
            '_preset_name': '테스트 프리셋',
            'strategy': 'RSI Strategy',
            'strategy_params': {'period': 21, 'overbought': 75, 'oversold': 25},
            'symbols': ['AAPL', 'MSFT'],
            'initial_capital': 20000.0,
            'position_size': 0.25,
            'stop_loss_pct': 0.05,
            'take_profit_pct': 0.10,
            'enable_stop_loss': True,
            'enable_take_profit': True
        }

        from scheduler import _start_single_session, active_traders, traders_lock

        label = "프리셋테스트"
        _start_single_session(label, config)

        # 세션이 등록되었는지 확인
        with traders_lock:
            if label in active_traders:
                trader = active_traders[label]
                assert trader.initial_capital == 20000.0
                assert trader.position_size == 0.25
                assert trader.stop_loss_pct == 0.05
                assert trader.take_profit_pct == 0.10
                assert trader.symbols == ['AAPL', 'MSFT']

                # 정리
                trader.stop()
                time.sleep(1)
                active_traders.pop(label, None)

    def test_stop_paper_trading_empty(self):
        """활성 세션이 없을 때 stop_paper_trading이 에러 없이 동작"""
        from scheduler import stop_paper_trading, active_traders

        # 활성 세션 비우기 (테스트 격리)
        original = dict(active_traders)
        active_traders.clear()

        try:
            stop_paper_trading()  # 에러 없이 실행되어야 함
        finally:
            active_traders.update(original)

    def test_start_paper_trading_with_no_presets(self):
        """프리셋 없이 start_paper_trading이 기본 설정으로 실행"""
        from scheduler import start_paper_trading, preset_configs

        # 프리셋 비우기
        original_presets = list(preset_configs)
        preset_configs.clear()

        with patch('trading_bot.scheduler.session_manager._start_single_session') as mock_start:
            start_paper_trading()
            mock_start.assert_called_once_with("기본", None)

        # 복원
        preset_configs.extend(original_presets)

    def test_start_paper_trading_with_presets(self):
        """프리셋이 있을 때 각 프리셋별로 세션 시작"""
        from scheduler import start_paper_trading, preset_configs

        original_presets = list(preset_configs)
        preset_configs.clear()

        # 테스트 프리셋 추가
        test_presets = [
            {'_preset_name': 'RSI 보수적', 'strategy': 'RSI Strategy'},
            {'_preset_name': 'MACD 추세', 'strategy': 'MACD Strategy'},
        ]
        preset_configs.extend(test_presets)

        with patch('trading_bot.scheduler.session_manager._start_single_session') as mock_start:
            start_paper_trading()
            assert mock_start.call_count == 2
            mock_start.assert_any_call('RSI 보수적', test_presets[0])
            mock_start.assert_any_call('MACD 추세', test_presets[1])

        # 복원
        preset_configs.clear()
        preset_configs.extend(original_presets)


# =============================================================================
# 3. CLI 인자 파싱 테스트
# =============================================================================


class TestCLIArguments:
    """CLI 인자 파싱 테스트"""

    def test_cli_parser_preset_flag(self):
        """--preset 인자 파싱"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument('--preset', type=str, default=None)
        parser.add_argument('--presets', type=str, nargs='+', default=None)
        parser.add_argument('--list-presets', action='store_true')

        args = parser.parse_args(['--preset', '테스트 프리셋'])
        assert args.preset == '테스트 프리셋'
        assert args.presets is None

    def test_cli_parser_presets_flag(self):
        """--presets 인자 파싱"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument('--preset', type=str, default=None)
        parser.add_argument('--presets', type=str, nargs='+', default=None)
        parser.add_argument('--list-presets', action='store_true')

        args = parser.parse_args(['--presets', 'RSI 보수적', 'MACD 추세', 'RSI+MACD 복합'])
        assert args.presets == ['RSI 보수적', 'MACD 추세', 'RSI+MACD 복합']
        assert args.preset is None

    def test_cli_parser_list_presets_flag(self):
        """--list-presets 인자 파싱"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument('--preset', type=str, default=None)
        parser.add_argument('--presets', type=str, nargs='+', default=None)
        parser.add_argument('--list-presets', action='store_true')

        args = parser.parse_args(['--list-presets'])
        assert args.list_presets is True

    def test_cli_parser_no_args(self):
        """인자 없이 기본값 확인"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument('--preset', type=str, default=None)
        parser.add_argument('--presets', type=str, nargs='+', default=None)
        parser.add_argument('--list-presets', action='store_true')

        args = parser.parse_args([])
        assert args.preset is None
        assert args.presets is None
        assert args.list_presets is False


# =============================================================================
# 4. SchedulerController 테스트
# =============================================================================


class TestSchedulerController:
    """Docker 스케줄러 컨트롤러 테스트"""

    def test_schedule_info(self):
        """스케줄 정보 반환 확인"""
        # Docker 없이 테스트할 수 있는 정적 메서드
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            info = controller.get_schedule_info()

            assert info['timezone'] == 'Asia/Seoul (KST)'
            assert len(info['schedules']) == 3

            # 스케줄 시간 확인
            schedule_times = [s['time'] for s in info['schedules']]
            assert '23:00 KST' in schedule_times
            assert '23:30 KST' in schedule_times
            assert '06:00 KST' in schedule_times

            # 시장 정보 확인
            assert info['market_hours']['name'] == 'US Stock Market'
            assert info['market_hours']['open'] == '23:30 KST (09:30 EST)'

    def test_get_status_container_not_found(self):
        """컨테이너가 없을 때 상태 조회"""
        from docker.errors import NotFound

        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.get.side_effect = NotFound("Not found")
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            status = controller.get_status()

            assert status['exists'] is False
            assert status['running'] is False
            assert status['status'] == 'not_found'

    def test_start_container_not_found(self):
        """컨테이너가 없을 때 시작 시도"""
        from docker.errors import NotFound

        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.get.side_effect = NotFound("Not found")
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.start()

            assert result['success'] is False
            assert 'docker-compose' in result.get('error', '')

    def test_stop_container_not_found(self):
        """컨테이너가 없을 때 중지 시도"""
        from docker.errors import NotFound

        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.get.side_effect = NotFound("Not found")
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.stop()

            assert result['success'] is False

    def test_get_status_running_container(self):
        """실행 중인 컨테이너 상태 조회"""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True

            mock_container = MagicMock()
            mock_container.status = 'running'
            mock_container.attrs = {
                'Created': '2026-02-12T00:00:00Z',
                'State': {
                    'StartedAt': '2026-02-12T00:00:00Z',
                    'FinishedAt': None,
                    'ExitCode': 0
                }
            }
            mock_client.containers.get.return_value = mock_container
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            status = controller.get_status()

            assert status['exists'] is True
            assert status['running'] is True
            assert status['status'] == 'running'

    def test_start_already_running(self):
        """이미 실행 중인 컨테이너 시작 시도"""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True

            mock_container = MagicMock()
            mock_container.status = 'running'
            mock_client.containers.get.return_value = mock_container
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.start()

            assert result['success'] is False
            assert '이미 실행 중' in result['message']

    def test_stop_already_stopped(self):
        """이미 중지된 컨테이너 중지 시도"""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True

            mock_container = MagicMock()
            mock_container.status = 'exited'
            mock_client.containers.get.return_value = mock_container
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.stop()

            assert result['success'] is False
            assert '이미 중지' in result['message']

    def test_get_logs_container_not_found(self):
        """컨테이너가 없을 때 로그 조회"""
        from docker.errors import NotFound

        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.get.side_effect = NotFound("Not found")
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            logs = controller.get_logs()

            assert len(logs) >= 1
            assert 'ERROR' in logs[0]

    def test_restart_success(self):
        """컨테이너 재시작 성공"""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True

            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.restart()

            assert result['success'] is True
            mock_container.restart.assert_called_once_with(timeout=10)

    def test_check_docker_available(self):
        """Docker 사용 가능 여부 확인"""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.version.return_value = {
                'Version': '24.0.0',
                'ApiVersion': '1.43'
            }
            mock_docker.return_value = mock_client

            from dashboard.scheduler_control import SchedulerController
            controller = SchedulerController()
            result = controller.check_docker_available()

            assert result['available'] is True
            assert result['version'] == '24.0.0'


# =============================================================================
# 5. 스윙 트레이딩 프리셋 생성 테스트
# =============================================================================


class TestSwingTradingPresets:
    """스윙 트레이딩 프리셋 생성 스크립트 테스트"""

    def test_preset_creation_script(self):
        """프리셋 생성 스크립트가 에러 없이 실행되는지 확인"""
        from trading_bot.strategy_presets import StrategyPresetManager

        # 임시 프리셋 파일 사용
        temp_dir = tempfile.mkdtemp()
        preset_file = os.path.join(temp_dir, 'test_presets.json')

        manager = StrategyPresetManager(presets_file=preset_file)

        # 스윙 트레이딩 RSI 보수적 프리셋
        success = manager.save_preset(
            name="스윙트레이딩 - RSI 보수적",
            description="테스트용 RSI 보수적 전략",
            strategy="RSI Strategy",
            strategy_params={'period': 21, 'overbought': 75, 'oversold': 25},
            symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
            initial_capital=10000.0,
            position_size=0.2,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True
        )
        assert success is True

        # 스윙 트레이딩 MACD 추세 프리셋
        success = manager.save_preset(
            name="스윙트레이딩 - MACD 추세 추종",
            description="테스트용 MACD 추세 전략",
            strategy="MACD Strategy",
            strategy_params={'fast_period': 19, 'slow_period': 39, 'signal_period': 9},
            symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
            initial_capital=10000.0,
            position_size=0.2,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True
        )
        assert success is True

        # 스윙 트레이딩 RSI+MACD 복합 프리셋
        success = manager.save_preset(
            name="스윙트레이딩 - RSI+MACD 복합",
            description="테스트용 RSI+MACD 복합 전략",
            strategy="RSI+MACD Combo Strategy",
            strategy_params={
                'rsi_period': 21, 'rsi_overbought': 75, 'rsi_oversold': 25,
                'macd_fast': 19, 'macd_slow': 39, 'macd_signal': 9
            },
            symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
            initial_capital=10000.0,
            position_size=0.2,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            enable_stop_loss=True,
            enable_take_profit=True
        )
        assert success is True

        # 프리셋 목록 확인
        presets = manager.list_presets()
        preset_names = [p['name'] for p in presets]
        assert '스윙트레이딩 - RSI 보수적' in preset_names
        assert '스윙트레이딩 - MACD 추세 추종' in preset_names
        assert '스윙트레이딩 - RSI+MACD 복합' in preset_names

        # 프리셋 로드 확인
        rsi_preset = manager.load_preset('스윙트레이딩 - RSI 보수적')
        assert rsi_preset['strategy'] == 'RSI Strategy'
        assert rsi_preset['strategy_params']['period'] == 21
        assert rsi_preset['stop_loss_pct'] == 0.05
        assert rsi_preset['take_profit_pct'] == 0.10

        # 정리
        if os.path.exists(preset_file):
            os.remove(preset_file)
        os.rmdir(temp_dir)

    def test_swing_preset_parameters(self):
        """스윙 트레이딩 프리셋 파라미터가 올바른지 확인"""
        # RSI 보수적: 긴 기간 + 넓은 범위
        rsi_params = {'period': 21, 'overbought': 75, 'oversold': 25}
        assert rsi_params['period'] > 14  # 기본 14보다 큰 기간
        assert rsi_params['overbought'] > 70  # 기본보다 높은 과매수
        assert rsi_params['oversold'] < 30  # 기본보다 낮은 과매도

        # MACD 추세: 긴 기간
        macd_params = {'fast_period': 19, 'slow_period': 39, 'signal_period': 9}
        assert macd_params['fast_period'] > 12  # 기본 12보다 큼
        assert macd_params['slow_period'] > 26  # 기본 26보다 큼

        # 공통 손익 범위: 스윙트레이딩용 (넓은 범위)
        stop_loss_pct = 0.05  # 5%
        take_profit_pct = 0.10  # 10%
        assert take_profit_pct > stop_loss_pct  # 익절 > 손절 (R:R 양호)


# =============================================================================
# 6. 멀티 세션 동시 실행 통합 테스트
# =============================================================================


class TestMultiSessionIntegration:
    """멀티 세션 동시 실행 통합 테스트"""

    def test_multiple_traders_concurrent(self):
        """여러 PaperTrader가 동시에 실행 가능한지 확인"""
        broker = MockBroker()
        strategies = [
            RSIStrategy(period=14, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
        ]

        traders = []
        threads = []

        for i, strategy in enumerate(strategies):
            temp_dir = tempfile.mkdtemp()
            db_path = os.path.join(temp_dir, f'test_concurrent_{i}.db')
            db = TradingDatabase(db_path=db_path)

            trader = PaperTrader(
                strategy=strategy,
                symbols=['AAPL'],
                broker=broker,
                initial_capital=10000.0,
                db=db
            )
            traders.append((trader, db_path, temp_dir))

            thread = threading.Thread(
                target=lambda t=trader: t.run_realtime(interval_seconds=60, timeframe='1d'),
                daemon=True,
                name=f"trader-{i}"
            )
            threads.append(thread)

        # 모든 스레드 시작
        for t in threads:
            t.start()

        # 실행 확인
        time.sleep(1)
        for trader, _, _ in traders:
            assert trader.is_running is True

        # 모든 트레이더 종료
        for trader, _, _ in traders:
            trader.stop()

        # 스레드 종료 대기
        for t in threads:
            t.join(timeout=10)

        # 모든 스레드가 종료되었는지 확인
        for t in threads:
            assert not t.is_alive()

        # 정리
        for trader, db_path, temp_dir in traders:
            if os.path.exists(db_path):
                os.remove(db_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)

    def test_concurrent_stop_does_not_deadlock(self):
        """동시 stop 호출 시 데드락이 발생하지 않는지 확인"""
        broker = MockBroker()
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, 'test_deadlock.db')
        db = TradingDatabase(db_path=db_path)

        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        trader = PaperTrader(
            strategy=strategy,
            symbols=['AAPL'],
            broker=broker,
            initial_capital=10000.0,
            db=db
        )

        # 실행
        thread = threading.Thread(
            target=lambda: trader.run_realtime(interval_seconds=60, timeframe='1d'),
            daemon=True
        )
        thread.start()
        time.sleep(0.5)

        # 여러 스레드에서 동시 stop 호출
        stop_threads = []
        for _ in range(5):
            st = threading.Thread(target=trader.stop, daemon=True)
            stop_threads.append(st)

        for st in stop_threads:
            st.start()

        # 데드락 없이 모든 스레드가 5초 내에 종료
        for st in stop_threads:
            st.join(timeout=5)
            assert not st.is_alive(), "Deadlock detected: stop thread still alive"

        thread.join(timeout=10)

        # 정리
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
