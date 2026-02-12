"""
전략 선택 UI 컴포넌트

StrategyRegistry를 활용하여 전략 목록, 파라미터 UI를 자동 생성합니다.
"""
import streamlit as st
from typing import Dict, Any, Optional

from trading_bot.strategy_registry import StrategyRegistry
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, StochasticStrategy, RSIMACDComboStrategy
from trading_bot.custom_combo_strategy import CustomComboStrategy


# 전략별 UI 파라미터 설정 (min, max, default, label, step)
# StrategyRegistry는 클래스 관리, 여기는 UI 슬라이더 설정
STRATEGY_PARAM_UI = {
    'Moving Average Crossover': {
        'registry_name': 'MA_Crossover',
        'params': {
            'fast_period': {'min': 5, 'max': 50, 'default': 10, 'label': 'Fast MA Period'},
            'slow_period': {'min': 10, 'max': 200, 'default': 30, 'label': 'Slow MA Period'}
        },
        'description': 'Generates BUY when fast MA crosses above slow MA, SELL when fast MA crosses below slow MA'
    },
    'RSI Strategy': {
        'registry_name': 'RSI',
        'params': {
            'period': {'min': 5, 'max': 30, 'default': 14, 'label': 'RSI Period'},
            'overbought': {'min': 60, 'max': 90, 'default': 70, 'label': 'Overbought Level'},
            'oversold': {'min': 10, 'max': 40, 'default': 30, 'label': 'Oversold Level'}
        },
        'description': 'Generates BUY when RSI crosses below oversold level, SELL when RSI crosses above overbought level'
    },
    'MACD Strategy': {
        'registry_name': 'MACD',
        'params': {
            'fast_period': {'min': 5, 'max': 20, 'default': 12, 'label': 'Fast EMA Period'},
            'slow_period': {'min': 20, 'max': 40, 'default': 26, 'label': 'Slow EMA Period'},
            'signal_period': {'min': 5, 'max': 15, 'default': 9, 'label': 'Signal Period'}
        },
        'description': 'Generates BUY when MACD line crosses above signal line, SELL when MACD line crosses below signal line'
    },
    'Bollinger Bands': {
        'registry_name': 'BollingerBands',
        'params': {
            'period': {'min': 10, 'max': 50, 'default': 20, 'label': 'Period'},
            'num_std': {'min': 1.0, 'max': 3.0, 'default': 2.0, 'step': 0.1, 'label': 'Std Deviations'}
        },
        'description': 'Generates BUY when price crosses below lower band, SELL when price crosses above upper band'
    },
    'Stochastic Oscillator': {
        'registry_name': 'Stochastic',
        'params': {
            'k_period': {'min': 5, 'max': 30, 'default': 14, 'label': '%K Period'},
            'd_period': {'min': 3, 'max': 10, 'default': 3, 'label': '%D Period'},
            'overbought': {'min': 60, 'max': 90, 'default': 80, 'label': 'Overbought Level'},
            'oversold': {'min': 10, 'max': 40, 'default': 20, 'label': 'Oversold Level'}
        },
        'description': 'Generates BUY when %K crosses above %D in oversold zone, SELL when %K crosses below %D in overbought zone'
    },
    'RSI+MACD Combo': {
        'registry_name': 'RSI_MACD_Combo',
        'params': {
            'rsi_period': {'min': 5, 'max': 30, 'default': 14, 'label': 'RSI Period'},
            'rsi_oversold': {'min': 20, 'max': 40, 'default': 35, 'label': 'RSI Oversold'},
            'rsi_overbought': {'min': 60, 'max': 85, 'default': 70, 'label': 'RSI Overbought'},
            'macd_fast': {'min': 8, 'max': 20, 'default': 12, 'label': 'MACD Fast'},
            'macd_slow': {'min': 20, 'max': 40, 'default': 26, 'label': 'MACD Slow'},
            'macd_signal': {'min': 5, 'max': 15, 'default': 9, 'label': 'MACD Signal'}
        },
        'description': '기술주 반등 전략: RSI 과매도(35 이하) + MACD 골든크로스 시 BUY, RSI 과매수(70 이상) 또는 MACD 데드크로스 시 SELL'
    }
}

# 기존 코드 호환성을 위한 STRATEGY_CONFIGS (class 키 포함)
STRATEGY_CONFIGS = {}
for name, config in STRATEGY_PARAM_UI.items():
    registry = StrategyRegistry()
    try:
        strategy_class = registry.get_strategy_class(config['registry_name'])
    except (ValueError, KeyError):
        # 폴백: 직접 import
        strategy_class = None

    STRATEGY_CONFIGS[name] = {
        'class': strategy_class,
        'params': config['params'],
        'description': config['description'],
        'registry_name': config['registry_name']
    }


def create_strategy(strategy_name: str, params: Dict[str, Any]):
    """StrategyRegistry를 사용하여 전략 인스턴스 생성"""
    config = STRATEGY_PARAM_UI.get(strategy_name)
    if config:
        registry = StrategyRegistry()
        return registry.create(config['registry_name'], **params)
    raise ValueError(f"Unknown strategy: {strategy_name}")


def get_strategy_names() -> list:
    """사용 가능한 전략 이름 목록 반환"""
    return list(STRATEGY_PARAM_UI.keys())


def get_strategy_config(strategy_name: str) -> Dict:
    """특정 전략의 설정 반환"""
    return STRATEGY_CONFIGS.get(strategy_name, {})


def render_strategy_params(strategy_name: str, key_prefix: str = "",
                           preset_params: Optional[Dict] = None) -> Dict[str, Any]:
    """
    전략 파라미터 슬라이더 UI를 렌더링하고 선택된 값을 반환

    Args:
        strategy_name: 전략 이름
        key_prefix: streamlit 위젯 키 접두사 (중복 방지)
        preset_params: 프리셋에서 불러온 기본값 (선택)

    Returns:
        파라미터 dict
    """
    config = STRATEGY_PARAM_UI.get(strategy_name, {})
    param_config = config.get('params', {})

    if not param_config:
        return {}

    strategy_params = {}
    param_cols = st.columns(min(len(param_config), 3))

    for idx, (param_name, pc) in enumerate(param_config.items()):
        col_idx = idx % len(param_cols)
        default_val = preset_params.get(param_name, pc['default']) if preset_params else pc['default']

        with param_cols[col_idx]:
            if isinstance(pc['default'], float):
                strategy_params[param_name] = st.slider(
                    pc['label'],
                    min_value=float(pc['min']),
                    max_value=float(pc['max']),
                    value=float(default_val),
                    step=pc.get('step', 0.1),
                    key=f"{key_prefix}{param_name}"
                )
            else:
                strategy_params[param_name] = st.slider(
                    pc['label'],
                    min_value=int(pc['min']),
                    max_value=int(pc['max']),
                    value=int(default_val),
                    key=f"{key_prefix}{param_name}"
                )

    return strategy_params
