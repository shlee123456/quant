"""
StrategyRegistry - 전략 등록 및 조회 시스템

전략을 이름으로 등록하고, 이름으로 인스턴스를 생성할 수 있는 싱글턴 레지스트리.
"""

from typing import Type, Dict, List, Optional, Any
import logging

logger = logging.getLogger("trading_bot.strategy_registry")


class StrategyRegistry:
    """
    전략 등록 및 조회 시스템 (싱글턴)

    전략 클래스를 이름으로 등록하고, 이름으로 인스턴스를 생성할 수 있습니다.

    사용법:
        registry = StrategyRegistry()
        registry.register("RSI", RSIStrategy)
        rsi = registry.create("RSI", period=14)
    """

    _instance: Optional["StrategyRegistry"] = None
    _strategies: Dict[str, Type] = {}

    def __new__(cls) -> "StrategyRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._strategies = {}
        return cls._instance

    def register(self, name: str, strategy_class: Type) -> None:
        """
        전략 클래스를 이름으로 등록

        Args:
            name: 전략 이름 (예: "RSI", "MACD")
            strategy_class: 전략 클래스

        Raises:
            TypeError: strategy_class가 클래스가 아닌 경우
        """
        if not isinstance(strategy_class, type):
            raise TypeError(f"strategy_class는 클래스여야 합니다: {strategy_class}")

        if name in self._strategies:
            logger.warning("전략 '%s' 덮어쓰기: %s → %s",
                           name, self._strategies[name].__name__,
                           strategy_class.__name__)
        else:
            logger.info("전략 등록: '%s' → %s", name, strategy_class.__name__)

        self._strategies[name] = strategy_class

    def create(self, name: str, **params: Any) -> Any:
        """
        이름으로 전략 인스턴스 생성

        Args:
            name: 등록된 전략 이름
            **params: 전략 생성자에 전달할 파라미터

        Returns:
            전략 인스턴스

        Raises:
            ValueError: 등록되지 않은 전략 이름인 경우
        """
        if name not in self._strategies:
            available = ", ".join(sorted(self._strategies.keys()))
            raise ValueError(
                f"등록되지 않은 전략: '{name}'. "
                f"사용 가능한 전략: [{available}]"
            )

        strategy_class = self._strategies[name]
        logger.info("전략 생성: '%s' (params: %s)", name, params)
        return strategy_class(**params)

    def list_strategies(self) -> List[str]:
        """등록된 전략 이름 목록 반환"""
        return list(self._strategies.keys())

    def get_strategy_class(self, name: str) -> Type:
        """
        전략 클래스 반환

        Args:
            name: 등록된 전략 이름

        Returns:
            전략 클래스

        Raises:
            ValueError: 등록되지 않은 전략 이름인 경우
        """
        if name not in self._strategies:
            available = ", ".join(sorted(self._strategies.keys()))
            raise ValueError(
                f"등록되지 않은 전략: '{name}'. "
                f"사용 가능한 전략: [{available}]"
            )
        return self._strategies[name]

    def get_strategy_info(self, name: str) -> Dict:
        """
        전략 설명 및 파라미터 정보 반환

        Args:
            name: 등록된 전략 이름

        Returns:
            전략 정보 딕셔너리:
            - name: 전략 이름
            - class_name: 클래스 이름
            - docstring: 클래스 docstring
            - param_info: 파라미터 정보 (get_param_info 지원 시)
        """
        strategy_class = self.get_strategy_class(name)

        info: Dict[str, Any] = {
            "name": name,
            "class_name": strategy_class.__name__,
            "docstring": (strategy_class.__doc__ or "").strip(),
        }

        # get_param_info() 지원 시 파라미터 정보 포함
        if hasattr(strategy_class, "get_param_info") and callable(strategy_class.get_param_info):
            try:
                # 인스턴스 메서드인 경우 임시 인스턴스 생성
                instance = strategy_class()
                info["param_info"] = instance.get_param_info()
            except Exception:
                info["param_info"] = {}
        else:
            info["param_info"] = {}

        return info

    def unregister(self, name: str) -> None:
        """
        전략 등록 해제 (주로 테스트용)

        Args:
            name: 해제할 전략 이름
        """
        if name in self._strategies:
            logger.info("전략 등록 해제: '%s'", name)
            del self._strategies[name]

    def clear(self) -> None:
        """모든 등록 해제 (주로 테스트용)"""
        logger.info("전략 레지스트리 초기화 (전체 해제)")
        self._strategies.clear()


def register_strategy(name: str):
    """
    전략 클래스 자동 등록 데코레이터

    사용법:
        @register_strategy("RSI")
        class RSIStrategy(BaseStrategy):
            ...
    """
    def decorator(cls: Type) -> Type:
        registry = StrategyRegistry()
        registry.register(name, cls)
        return cls
    return decorator


def _register_builtin_strategies() -> None:
    """내장 전략들을 자동으로 등록"""
    registry = StrategyRegistry()

    # 안전한 import - 실패해도 다른 전략 등록에 영향 없음
    builtin_strategies = [
        ("MA_Crossover", "trading_bot.strategy", "MovingAverageCrossover"),
        ("RSI", "trading_bot.strategies.rsi_strategy", "RSIStrategy"),
        ("MACD", "trading_bot.strategies.macd_strategy", "MACDStrategy"),
        ("BollingerBands", "trading_bot.strategies.bollinger_bands_strategy", "BollingerBandsStrategy"),
        ("Stochastic", "trading_bot.strategies.stochastic_strategy", "StochasticStrategy"),
        ("RSI_MACD_Combo", "trading_bot.strategies.rsi_macd_combo_strategy", "RSIMACDComboStrategy"),
        ("Custom_Combo", "trading_bot.custom_combo_strategy", "CustomComboStrategy"),
    ]

    for name, module_path, class_name in builtin_strategies:
        try:
            import importlib
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
            registry.register(name, strategy_class)
        except (ImportError, AttributeError) as e:
            logger.debug("내장 전략 '%s' 등록 실패 (무시): %s", name, e)


# 모듈 로드 시 자동 실행
_register_builtin_strategies()
