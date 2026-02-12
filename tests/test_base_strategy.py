"""
BaseStrategy ABC 테스트

BaseStrategy 추상 기본 클래스의 공통 기능과 인터페이스 계약을 검증합니다.
"""

import pytest
import pandas as pd
import numpy as np
from abc import ABC

from trading_bot.strategies.base_strategy import BaseStrategy, VALID_SIGNALS, REQUIRED_OHLCV_COLUMNS


# ---------------------------------------------------------------------------
# 테스트용 구체 전략 클래스
# ---------------------------------------------------------------------------

class DummyStrategy(BaseStrategy):
    """BaseStrategy를 올바르게 구현한 더미 전략"""

    def __init__(self):
        super().__init__(name="Dummy")

    def calculate_indicators(self, df):
        data = df.copy()
        data['signal'] = 0
        data['position'] = 0
        return data

    def get_current_signal(self, df):
        return 0, {'close': df.iloc[-1]['close']}

    def get_all_signals(self, df):
        return []

    def get_params(self):
        return {}


class IncompleteStrategy(BaseStrategy):
    """abstractmethod를 일부만 구현한 불완전 전략 (calculate_indicators만 구현)"""

    def __init__(self):
        super().__init__(name="Incomplete")

    def calculate_indicators(self, df):
        return df.copy()

    # get_current_signal, get_all_signals 미구현


# ---------------------------------------------------------------------------
# 테스트 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy():
    return DummyStrategy()


@pytest.fixture
def ohlcv_df():
    """정상 OHLCV DataFrame"""
    np.random.seed(42)
    n = 50
    prices = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        'open': prices,
        'high': prices + abs(np.random.randn(n)),
        'low': prices - abs(np.random.randn(n)),
        'close': prices + np.random.randn(n) * 0.5,
        'volume': np.random.randint(1000, 10000, n),
    })


# ---------------------------------------------------------------------------
# 1. ABC 직접 인스턴스화 불가
# ---------------------------------------------------------------------------

class TestABCInstantiation:
    """ABC 인스턴스화 관련 테스트"""

    def test_cannot_instantiate_base_strategy(self):
        """BaseStrategy를 직접 인스턴스화하면 TypeError 발생"""
        with pytest.raises(TypeError):
            BaseStrategy(name="Fail")

    def test_incomplete_subclass_cannot_instantiate(self):
        """abstractmethod를 모두 구현하지 않으면 인스턴스화 불가"""
        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_base_strategy_is_abstract(self):
        """BaseStrategy가 ABC를 상속하는지 확인"""
        assert issubclass(BaseStrategy, ABC)


# ---------------------------------------------------------------------------
# 2. validate_signal 테스트
# ---------------------------------------------------------------------------

class TestValidateSignal:
    """validate_signal 메서드 테스트"""

    @pytest.mark.parametrize("signal", [1, 0, -1])
    def test_valid_signals(self, dummy, signal):
        """유효한 시그널 값(1, 0, -1)은 True"""
        assert dummy.validate_signal(signal) is True

    @pytest.mark.parametrize("signal", [2, -2, 99, 10, -10])
    def test_invalid_signals(self, dummy, signal):
        """범위 밖 시그널 값은 False"""
        assert dummy.validate_signal(signal) is False


# ---------------------------------------------------------------------------
# 3. validate_dataframe 테스트
# ---------------------------------------------------------------------------

class TestValidateDataframe:
    """validate_dataframe 메서드 테스트"""

    def test_valid_ohlcv_passes(self, dummy, ohlcv_df):
        """OHLCV 컬럼이 모두 있으면 예외 없음"""
        dummy.validate_dataframe(ohlcv_df)  # 예외 발생하면 테스트 실패

    def test_missing_column_raises_valueerror(self, dummy):
        """필수 컬럼 누락 시 ValueError 발생"""
        df = pd.DataFrame({'open': [1], 'high': [2], 'low': [0.5]})
        with pytest.raises(ValueError) as exc_info:
            dummy.validate_dataframe(df)
        # 누락 컬럼이 에러 메시지에 포함되어야 함
        error_msg = str(exc_info.value)
        assert 'close' in error_msg or 'volume' in error_msg

    def test_missing_all_columns_raises_valueerror(self, dummy):
        """컬럼이 전혀 없는 DataFrame"""
        df = pd.DataFrame({'x': [1, 2]})
        with pytest.raises(ValueError):
            dummy.validate_dataframe(df)

    def test_empty_dataframe_with_columns_passes(self, dummy):
        """빈 DataFrame이어도 컬럼이 있으면 통과"""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        dummy.validate_dataframe(df)


# ---------------------------------------------------------------------------
# 4. name 속성, __str__, __repr__ 테스트
# ---------------------------------------------------------------------------

class TestNameAndRepr:
    """name 속성 및 문자열 표현 테스트"""

    def test_name_property(self, dummy):
        """name 속성이 정상 동작"""
        assert dummy.name == "Dummy"

    def test_str_output(self, dummy):
        """__str__이 클래스명과 이름을 포함"""
        result = str(dummy)
        assert "DummyStrategy" in result
        assert "Dummy" in result

    def test_repr_output(self, dummy):
        """__repr__이 클래스명을 포함"""
        result = repr(dummy)
        assert "DummyStrategy" in result

    def test_repr_with_params(self):
        """get_params가 값을 반환하면 __repr__에 파라미터 포함"""

        class ParamStrategy(BaseStrategy):
            def __init__(self):
                super().__init__(name="PS")

            def calculate_indicators(self, df):
                return df.copy()

            def get_current_signal(self, df):
                return 0, {}

            def get_all_signals(self, df):
                return []

            def get_params(self):
                return {"period": 14, "overbought": 70}

        s = ParamStrategy()
        r = repr(s)
        assert "period=14" in r
        assert "overbought=70" in r


# ---------------------------------------------------------------------------
# 5. get_params / get_param_info 기본 동작 테스트
# ---------------------------------------------------------------------------

class TestGetParamsMethods:
    """get_params 및 get_param_info 기본 반환값 테스트"""

    def test_get_params_returns_dict(self, dummy):
        """get_params 기본 반환값이 dict"""
        result = dummy.get_params()
        assert isinstance(result, dict)

    def test_get_param_info_returns_dict(self, dummy):
        """get_param_info 기본 반환값이 dict"""
        result = dummy.get_param_info()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 6. 실제 전략들이 BaseStrategy의 인스턴스인지 확인
# ---------------------------------------------------------------------------

class TestRealStrategiesAreBaseStrategy:
    """모든 실제 전략이 BaseStrategy를 상속하는지 확인"""

    def test_moving_average_crossover(self):
        from trading_bot.strategy import MovingAverageCrossover
        s = MovingAverageCrossover(fast_period=5, slow_period=10)
        assert isinstance(s, BaseStrategy)

    def test_rsi_strategy(self):
        from trading_bot.strategies.rsi_strategy import RSIStrategy
        s = RSIStrategy(period=14)
        assert isinstance(s, BaseStrategy)

    def test_macd_strategy(self):
        from trading_bot.strategies.macd_strategy import MACDStrategy
        s = MACDStrategy()
        assert isinstance(s, BaseStrategy)

    def test_bollinger_bands_strategy(self):
        from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
        s = BollingerBandsStrategy()
        assert isinstance(s, BaseStrategy)

    def test_stochastic_strategy(self):
        from trading_bot.strategies.stochastic_strategy import StochasticStrategy
        s = StochasticStrategy()
        assert isinstance(s, BaseStrategy)

    def test_rsi_macd_combo_strategy(self):
        from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy
        s = RSIMACDComboStrategy()
        assert isinstance(s, BaseStrategy)

    def test_custom_combo_strategy(self):
        from trading_bot.custom_combo_strategy import CustomComboStrategy
        from trading_bot.strategies.rsi_strategy import RSIStrategy
        sub = RSIStrategy(period=14)
        s = CustomComboStrategy(strategies=[sub], strategy_names=["RSI"])
        assert isinstance(s, BaseStrategy)

    def test_all_strategies_have_get_params(self):
        """모든 실제 전략이 get_params를 dict로 반환"""
        from trading_bot.strategy import MovingAverageCrossover
        from trading_bot.strategies import (
            RSIStrategy, MACDStrategy, BollingerBandsStrategy,
            StochasticStrategy, RSIMACDComboStrategy,
        )
        from trading_bot.custom_combo_strategy import CustomComboStrategy

        strategies = [
            MovingAverageCrossover(),
            RSIStrategy(),
            MACDStrategy(),
            BollingerBandsStrategy(),
            StochasticStrategy(),
            RSIMACDComboStrategy(),
            CustomComboStrategy(strategies=[RSIStrategy()], strategy_names=["RSI"]),
        ]
        for s in strategies:
            assert isinstance(s.get_params(), dict), f"{s.name}: get_params가 dict가 아님"

    def test_all_strategies_have_get_param_info(self):
        """모든 실제 전략이 get_param_info를 dict로 반환"""
        from trading_bot.strategy import MovingAverageCrossover
        from trading_bot.strategies import (
            RSIStrategy, MACDStrategy, BollingerBandsStrategy,
            StochasticStrategy, RSIMACDComboStrategy,
        )
        from trading_bot.custom_combo_strategy import CustomComboStrategy

        strategies = [
            MovingAverageCrossover(),
            RSIStrategy(),
            MACDStrategy(),
            BollingerBandsStrategy(),
            StochasticStrategy(),
            RSIMACDComboStrategy(),
            CustomComboStrategy(strategies=[RSIStrategy()], strategy_names=["RSI"]),
        ]
        for s in strategies:
            assert isinstance(s.get_param_info(), dict), f"{s.name}: get_param_info가 dict가 아님"
