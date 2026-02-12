"""
StrategyRegistry 테스트

전략 등록/조회 시스템의 싱글턴 패턴, CRUD, 데코레이터를 검증합니다.
"""

import pytest

from trading_bot.strategy_registry import StrategyRegistry, register_strategy
from trading_bot.strategies.base_strategy import BaseStrategy


# ---------------------------------------------------------------------------
# Fixture: 레지스트리 상태를 테스트 간에 격리
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_registry():
    """
    테스트 전 현재 등록 상태를 백업하고, 테스트 후 복원.
    clear() 또는 unregister()를 사용하는 테스트가 다른 테스트에 영향을 주지 않도록 한다.
    """
    registry = StrategyRegistry()
    backup = dict(registry._strategies)
    yield
    registry._strategies.clear()
    registry._strategies.update(backup)


# ---------------------------------------------------------------------------
# 1. 싱글턴 패턴 테스트
# ---------------------------------------------------------------------------

class TestSingleton:
    """StrategyRegistry 싱글턴 패턴 검증"""

    def test_same_instance(self):
        """두 인스턴스가 동일 객체"""
        r1 = StrategyRegistry()
        r2 = StrategyRegistry()
        assert r1 is r2

    def test_shared_state(self):
        """인스턴스 간 등록 상태 공유"""
        r1 = StrategyRegistry()
        r2 = StrategyRegistry()
        assert r1.list_strategies() == r2.list_strategies()


# ---------------------------------------------------------------------------
# 2. 내장 전략 등록 확인
# ---------------------------------------------------------------------------

class TestBuiltinStrategies:
    """내장 전략 자동 등록 확인"""

    def test_builtin_strategies_registered(self):
        """list_strategies에 7개 내장 전략이 포함되어야 함"""
        registry = StrategyRegistry()
        strategies = registry.list_strategies()

        expected = [
            "MA_Crossover", "RSI", "MACD",
            "BollingerBands", "Stochastic",
            "RSI_MACD_Combo", "Custom_Combo",
        ]
        for name in expected:
            assert name in strategies, f"내장 전략 '{name}'이 등록되지 않음"

    def test_list_strategies_returns_list(self):
        """list_strategies 반환 타입이 list"""
        registry = StrategyRegistry()
        assert isinstance(registry.list_strategies(), list)


# ---------------------------------------------------------------------------
# 3. create 테스트
# ---------------------------------------------------------------------------

class TestCreate:
    """create 메서드 테스트"""

    def test_create_rsi_strategy(self):
        """RSI 전략을 파라미터와 함께 생성"""
        registry = StrategyRegistry()
        rsi = registry.create("RSI", period=10, overbought=80, oversold=20)
        assert rsi is not None
        params = rsi.get_params()
        assert params["period"] == 10
        assert params["overbought"] == 80
        assert params["oversold"] == 20

    def test_create_ma_crossover(self):
        """MA_Crossover 전략 생성"""
        registry = StrategyRegistry()
        ma = registry.create("MA_Crossover", fast_period=5, slow_period=20)
        assert ma is not None
        params = ma.get_params()
        assert params["fast_period"] == 5
        assert params["slow_period"] == 20

    def test_create_unknown_raises_valueerror(self):
        """등록되지 않은 이름으로 create 시 ValueError"""
        registry = StrategyRegistry()
        with pytest.raises(ValueError, match="등록되지 않은 전략"):
            registry.create("NotExist")


# ---------------------------------------------------------------------------
# 4. get_strategy_class 테스트
# ---------------------------------------------------------------------------

class TestGetStrategyClass:
    """get_strategy_class 메서드 테스트"""

    def test_returns_correct_class(self):
        """등록된 이름에 대해 올바른 클래스 반환"""
        from trading_bot.strategies.rsi_strategy import RSIStrategy

        registry = StrategyRegistry()
        cls = registry.get_strategy_class("RSI")
        assert cls is RSIStrategy

    def test_unknown_name_raises_valueerror(self):
        """등록되지 않은 이름은 ValueError"""
        registry = StrategyRegistry()
        with pytest.raises(ValueError, match="등록되지 않은 전략"):
            registry.get_strategy_class("Unknown")


# ---------------------------------------------------------------------------
# 5. get_strategy_info 테스트
# ---------------------------------------------------------------------------

class TestGetStrategyInfo:
    """get_strategy_info 메서드 테스트"""

    def test_returns_dict(self):
        """반환값이 dict"""
        registry = StrategyRegistry()
        info = registry.get_strategy_info("RSI")
        assert isinstance(info, dict)

    def test_contains_required_keys(self):
        """name, class_name, docstring 키 포함"""
        registry = StrategyRegistry()
        info = registry.get_strategy_info("RSI")
        assert "name" in info
        assert "class_name" in info
        assert "docstring" in info

    def test_info_name_matches(self):
        """info['name']이 요청한 이름과 일치"""
        registry = StrategyRegistry()
        info = registry.get_strategy_info("MACD")
        assert info["name"] == "MACD"


# ---------------------------------------------------------------------------
# 6. unregister 테스트
# ---------------------------------------------------------------------------

class TestUnregister:
    """unregister 메서드 테스트"""

    def test_unregister_then_create_fails(self):
        """등록 해제 후 create 시 ValueError"""
        registry = StrategyRegistry()
        # 임시 전략 등록 후 해제
        from trading_bot.strategies.rsi_strategy import RSIStrategy
        registry.register("TempRSI", RSIStrategy)
        registry.unregister("TempRSI")
        with pytest.raises(ValueError):
            registry.create("TempRSI")

    def test_unregister_nonexistent_no_error(self):
        """존재하지 않는 이름 해제 시 에러 없음"""
        registry = StrategyRegistry()
        registry.unregister("NeverRegistered")  # 예외 없이 정상


# ---------------------------------------------------------------------------
# 7. clear 테스트
# ---------------------------------------------------------------------------

class TestClear:
    """clear 메서드 테스트 (autouse fixture가 상태 복원)"""

    def test_clear_empties_registry(self):
        """clear 후 list_strategies가 빈 리스트"""
        registry = StrategyRegistry()
        registry.clear()
        assert registry.list_strategies() == []


# ---------------------------------------------------------------------------
# 8. @register_strategy 데코레이터 테스트
# ---------------------------------------------------------------------------

class TestRegisterDecorator:
    """@register_strategy 데코레이터 테스트"""

    def test_decorator_registers_class(self):
        """데코레이터로 새 전략이 레지스트리에 등록됨"""

        @register_strategy("TestDecorated")
        class DecoratedStrategy(BaseStrategy):
            def __init__(self):
                super().__init__(name="Decorated")

            def calculate_indicators(self, df):
                return df.copy()

            def get_current_signal(self, df):
                return 0, {}

            def get_all_signals(self, df):
                return []

        registry = StrategyRegistry()
        assert "TestDecorated" in registry.list_strategies()

        # 인스턴스 생성 확인
        instance = registry.create("TestDecorated")
        assert isinstance(instance, DecoratedStrategy)
        assert isinstance(instance, BaseStrategy)


# ---------------------------------------------------------------------------
# 9. 생성된 전략이 BaseStrategy 인스턴스인지 확인
# ---------------------------------------------------------------------------

class TestCreatedInstancesAreBaseStrategy:
    """create로 생성된 전략이 BaseStrategy 인스턴스인지 확인"""

    @pytest.mark.parametrize("name", [
        "MA_Crossover", "RSI", "MACD",
        "BollingerBands", "Stochastic", "RSI_MACD_Combo",
    ])
    def test_created_strategy_is_base_strategy(self, name):
        """레지스트리에서 생성한 전략이 BaseStrategy를 상속"""
        registry = StrategyRegistry()
        instance = registry.create(name)
        assert isinstance(instance, BaseStrategy), (
            f"'{name}' 전략이 BaseStrategy 인스턴스가 아님"
        )


# ---------------------------------------------------------------------------
# 10. register에 클래스가 아닌 값 전달 시 TypeError
# ---------------------------------------------------------------------------

class TestRegisterValidation:
    """register 메서드 입력 검증"""

    def test_register_non_class_raises_typeerror(self):
        """클래스가 아닌 값 등록 시 TypeError"""
        registry = StrategyRegistry()
        with pytest.raises(TypeError):
            registry.register("Bad", "not_a_class")

    def test_register_instance_raises_typeerror(self):
        """인스턴스 전달 시 TypeError"""
        from trading_bot.strategies.rsi_strategy import RSIStrategy
        registry = StrategyRegistry()
        with pytest.raises(TypeError):
            registry.register("BadInstance", RSIStrategy())
