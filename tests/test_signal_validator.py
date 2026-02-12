"""
SignalValidator 단위 테스트
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading_bot.signal_validator import SignalValidator
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies.rsi_strategy import RSIStrategy


class TestValidateSignalValue(unittest.TestCase):
    """validate_signal_value 테스트"""

    def test_valid_buy_signal(self):
        """BUY 시그널 (1) 유효"""
        self.assertTrue(SignalValidator.validate_signal_value(1))

    def test_valid_sell_signal(self):
        """SELL 시그널 (-1) 유효"""
        self.assertTrue(SignalValidator.validate_signal_value(-1))

    def test_valid_hold_signal(self):
        """HOLD 시그널 (0) 유효"""
        self.assertTrue(SignalValidator.validate_signal_value(0))

    def test_invalid_signal_positive(self):
        """범위 밖 양수 시그널 무효"""
        self.assertFalse(SignalValidator.validate_signal_value(2))

    def test_invalid_signal_negative(self):
        """범위 밖 음수 시그널 무효"""
        self.assertFalse(SignalValidator.validate_signal_value(-2))

    def test_invalid_signal_float(self):
        """소수점 시그널 무효"""
        self.assertFalse(SignalValidator.validate_signal_value(0.5))


class TestValidateSignalSequence(unittest.TestCase):
    """validate_signal_sequence 테스트"""

    def test_normal_sequence(self):
        """정상적인 BUY-HOLD-SELL 시퀀스"""
        signals = pd.Series([0, 0, 1, 0, 0, -1, 0, 0])
        warnings = SignalValidator.validate_signal_sequence(signals)
        self.assertEqual(len(warnings), 0)

    def test_duplicate_buy(self):
        """중복 BUY 탐지"""
        signals = pd.Series([0, 1, 0, 1, 0, -1])
        warnings = SignalValidator.validate_signal_sequence(signals)
        self.assertEqual(len(warnings), 1)
        self.assertIn("중복 BUY", warnings[0])

    def test_sell_without_position(self):
        """포지션 없이 SELL 탐지"""
        signals = pd.Series([0, 0, -1, 0])
        warnings = SignalValidator.validate_signal_sequence(signals)
        self.assertEqual(len(warnings), 1)
        self.assertIn("포지션 없는 SELL", warnings[0])

    def test_invalid_signal_value_in_sequence(self):
        """시퀀스 내 유효하지 않은 값 탐지"""
        signals = pd.Series([0, 1, 0, 3, -1])
        warnings = SignalValidator.validate_signal_sequence(signals)
        invalid_warnings = [w for w in warnings if "유효하지 않은 시그널 값" in w]
        self.assertGreater(len(invalid_warnings), 0)

    def test_empty_series(self):
        """빈 시리즈"""
        signals = pd.Series([], dtype=int)
        warnings = SignalValidator.validate_signal_sequence(signals)
        self.assertEqual(len(warnings), 0)

    def test_multiple_buy_sell_cycles(self):
        """여러 번 매수-매도 사이클 정상"""
        signals = pd.Series([1, 0, -1, 0, 1, 0, -1])
        warnings = SignalValidator.validate_signal_sequence(signals)
        self.assertEqual(len(warnings), 0)

    def test_consecutive_sell_after_buy(self):
        """매도 후 또 매도"""
        signals = pd.Series([1, -1, -1])
        warnings = SignalValidator.validate_signal_sequence(signals)
        sell_warnings = [w for w in warnings if "포지션 없는 SELL" in w]
        self.assertEqual(len(sell_warnings), 1)


class TestValidateIndicators(unittest.TestCase):
    """validate_indicators 테스트"""

    def test_valid_dataframe(self):
        """정상 DataFrame"""
        df = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'signal': [0, 1, -1],
            'position': [0, 1, 0],
            'rsi': [50.0, 30.0, 70.0],
        })
        warnings = SignalValidator.validate_indicators(df)
        self.assertEqual(len(warnings), 0)

    def test_nan_in_signal(self):
        """signal에 NaN 존재"""
        df = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'signal': [0, np.nan, -1],
            'position': [0, 0, 0],
        })
        warnings = SignalValidator.validate_indicators(df)
        nan_warnings = [w for w in warnings if "NaN" in w and "signal" in w]
        self.assertGreater(len(nan_warnings), 0)

    def test_invalid_signal_values(self):
        """signal에 유효하지 않은 값"""
        df = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'signal': [0, 2, -1],
            'position': [0, 0, 0],
        })
        warnings = SignalValidator.validate_indicators(df)
        invalid_warnings = [w for w in warnings if "유효하지 않은 값" in w]
        self.assertGreater(len(invalid_warnings), 0)

    def test_nan_in_position(self):
        """position에 NaN 존재"""
        df = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'signal': [0, 1, -1],
            'position': [0, np.nan, 0],
        })
        warnings = SignalValidator.validate_indicators(df)
        nan_warnings = [w for w in warnings if "NaN" in w and "position" in w]
        self.assertGreater(len(nan_warnings), 0)

    def test_inf_in_indicator(self):
        """지표에 Inf 존재"""
        df = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'signal': [0, 1, -1],
            'position': [0, 1, 0],
            'rsi': [50.0, np.inf, 70.0],
        })
        warnings = SignalValidator.validate_indicators(df)
        inf_warnings = [w for w in warnings if "Inf" in w]
        self.assertGreater(len(inf_warnings), 0)

    def test_missing_signal_column(self):
        """signal 컬럼 없음"""
        df = pd.DataFrame({
            'close': [100.0, 101.0],
            'position': [0, 1],
        })
        warnings = SignalValidator.validate_indicators(df)
        missing_warnings = [w for w in warnings if "존재하지 않음" in w and "signal" in w]
        self.assertGreater(len(missing_warnings), 0)

    def test_missing_position_column(self):
        """position 컬럼 없음"""
        df = pd.DataFrame({
            'close': [100.0, 101.0],
            'signal': [0, 1],
        })
        warnings = SignalValidator.validate_indicators(df)
        missing_warnings = [w for w in warnings if "존재하지 않음" in w and "position" in w]
        self.assertGreater(len(missing_warnings), 0)

    def test_empty_dataframe(self):
        """빈 DataFrame"""
        df = pd.DataFrame()
        warnings = SignalValidator.validate_indicators(df)
        self.assertEqual(len(warnings), 0)


class TestValidateNoLookahead(unittest.TestCase):
    """validate_no_lookahead 테스트"""

    def _create_sample_data(self, periods: int = 100) -> pd.DataFrame:
        """테스트용 OHLCV 데이터 생성"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1h')
        np.random.seed(42)
        prices = 100.0 + np.cumsum(np.random.randn(periods) * 2)
        return pd.DataFrame({
            'open': prices,
            'high': prices + abs(np.random.randn(periods)),
            'low': prices - abs(np.random.randn(periods)),
            'close': prices,
            'volume': np.random.randint(1000, 10000, periods),
        }, index=dates)

    def test_no_lookahead_with_ma_strategy(self):
        """MA 전략은 look-ahead bias가 없어야 함"""
        df = self._create_sample_data(100)
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        result = SignalValidator.validate_no_lookahead(df, strategy)
        self.assertTrue(result)

    def test_no_lookahead_with_rsi_strategy(self):
        """RSI 전략은 look-ahead bias가 없어야 함"""
        df = self._create_sample_data(100)
        strategy = RSIStrategy(period=14)
        result = SignalValidator.validate_no_lookahead(df, strategy)
        self.assertTrue(result)

    def test_lookahead_detected(self):
        """Look-ahead bias가 있는 전략 탐지"""

        class LookaheadStrategy:
            """의도적으로 look-ahead bias가 있는 전략"""
            def __init__(self):
                self.name = "Lookahead"

            def calculate_indicators(self, df):
                data = df.copy()
                # 미래 데이터 사용: 다음 행의 종가와 비교
                data['signal'] = 0
                data.loc[data['close'] > data['close'].shift(-1), 'signal'] = -1
                data.loc[data['close'] < data['close'].shift(-1), 'signal'] = 1
                data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)
                return data

        df = self._create_sample_data(100)
        strategy = LookaheadStrategy()
        result = SignalValidator.validate_no_lookahead(df, strategy)
        self.assertFalse(result)

    def test_insufficient_data(self):
        """데이터 부족 시 True 반환 (검증 불가)"""
        df = self._create_sample_data(5)
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        result = SignalValidator.validate_no_lookahead(df, strategy, n_rows=10)
        self.assertTrue(result)


class TestIntegrationWithStrategies(unittest.TestCase):
    """실제 전략과의 통합 테스트"""

    def setUp(self):
        """테스트 데이터 생성"""
        dates = pd.date_range(start='2024-01-01', periods=200, freq='1h')
        np.random.seed(42)
        prices = 100.0 + np.cumsum(np.random.randn(200) * 2)
        self.sample_data = pd.DataFrame({
            'open': prices,
            'high': prices + abs(np.random.randn(200)),
            'low': prices - abs(np.random.randn(200)),
            'close': prices,
            'volume': np.random.randint(1000, 10000, 200),
        }, index=dates)

    def test_validate_rsi_indicators(self):
        """RSI 전략의 지표 검증"""
        strategy = RSIStrategy(period=14)
        result = strategy.calculate_indicators(self.sample_data)
        warnings = SignalValidator.validate_indicators(result)
        # RSI warm-up 기간 이후에는 경고가 없어야 함 (NaN은 warm-up 기간에만)
        inf_warnings = [w for w in warnings if "Inf" in w]
        self.assertEqual(len(inf_warnings), 0)

    def test_validate_ma_indicators(self):
        """MA 전략의 지표 검증"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        result = strategy.calculate_indicators(self.sample_data)
        warnings = SignalValidator.validate_indicators(result)
        inf_warnings = [w for w in warnings if "Inf" in w]
        self.assertEqual(len(inf_warnings), 0)

    def test_validate_rsi_signal_sequence(self):
        """RSI 전략의 시그널 시퀀스 검증"""
        strategy = RSIStrategy(period=14)
        result = strategy.calculate_indicators(self.sample_data)
        warnings = SignalValidator.validate_signal_sequence(result['signal'])
        # 경고가 있을 수 있지만 오류는 아님 (전략 설계에 따라)
        self.assertIsInstance(warnings, list)


if __name__ == '__main__':
    unittest.main()
