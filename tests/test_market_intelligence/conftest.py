"""
Market Intelligence 테스트용 공통 헬퍼 및 fixtures.
"""

import numpy as np
import pandas as pd
import pytest
from typing import Dict, List, Optional


def make_ohlcv(
    n: int = 200,
    start_price: float = 100.0,
    trend: float = 0.0005,
    volatility: float = 0.02,
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV DataFrame with yfinance-style columns.

    Args:
        n: 데이터 포인트 수
        start_price: 시작 가격
        trend: 일일 평균 추세 (0.001 = 0.1%/일 상승)
        volatility: 일일 변동성 표준편차
        seed: 랜덤 시드

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume (PascalCase)
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random.RandomState()

    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq='B')

    # Random walk with drift
    log_returns = rng.normal(trend, volatility, n)
    log_returns[0] = 0.0
    prices = start_price * np.exp(np.cumsum(log_returns))

    # OHLCV 생성
    intraday_vol = volatility * 0.5
    opens = prices * (1 + rng.normal(0, intraday_vol * 0.3, n))
    highs = np.maximum(prices, opens) * (1 + np.abs(rng.normal(0, intraday_vol, n)))
    lows = np.minimum(prices, opens) * (1 - np.abs(rng.normal(0, intraday_vol, n)))
    volumes = rng.randint(100_000, 10_000_000, n).astype(float)

    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': prices,
        'Volume': volumes,
    }, index=dates)

    return df


class MockCache:
    """테스트용 MockCache.

    MarketDataCache와 동일한 get()/get_many() 인터페이스를 제공합니다.
    """

    def __init__(self, data: Optional[Dict[str, pd.DataFrame]] = None, fred_data: Optional[Dict[str, pd.Series]] = None):
        self._data = data or {}
        self._fred_data = fred_data or {}

    def get(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._data.get(symbol)

    def get_many(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        return {s: self._data[s] for s in symbols if s in self._data}

    @property
    def available_symbols(self) -> List[str]:
        return list(self._data.keys())

    def freshness_multiplier(self, symbol: str) -> float:
        """테스트용 신선도: 데이터 있으면 1.0, 없으면 0.0."""
        if symbol not in self._data:
            return 0.0
        return 1.0

    def avg_freshness_for_symbols(self, symbols: list) -> float:
        """테스트용 벌크 신선도."""
        vals = [1.0 for s in symbols if s in self._data]
        return sum(vals) / len(vals) if vals else 1.0

    def fred_freshness(self, key: str) -> float:
        """테스트용 FRED 신선도."""
        return 1.0

    def avg_fred_freshness(self, keys: list) -> float:
        """테스트용 FRED 벌크 신선도."""
        return 1.0

    def get_fred(self, key: str):
        """테스트용 FRED 데이터 조회."""
        return self._fred_data.get(key)

    def spy_ma200_status(self):
        """테스트용 SPY MA200 상태."""
        return {}


def make_trending_cache(
    trend: float = 0.001,
    n: int = 200,
    seed: int = 42,
) -> MockCache:
    """모든 주요 심볼에 대해 trending 데이터를 가진 MockCache 생성.

    Args:
        trend: 일일 추세
        n: 데이터 포인트 수
        seed: 기본 랜덤 시드

    Returns:
        MockCache with all standard symbols populated
    """
    from trading_bot.market_intelligence.data_fetcher import LAYER_SYMBOLS

    all_symbols = set()
    for symbols in LAYER_SYMBOLS.values():
        all_symbols.update(symbols)

    data = {}
    for i, sym in enumerate(sorted(all_symbols)):
        # 각 심볼마다 약간 다른 시드 사용
        data[sym] = make_ohlcv(
            n=n,
            start_price=50.0 + i * 5,
            trend=trend,
            volatility=0.015,
            seed=seed + i,
        )

    return MockCache(data)


@pytest.fixture
def bullish_cache() -> MockCache:
    """상승 추세 데이터를 가진 MockCache fixture."""
    return make_trending_cache(trend=0.002, seed=100)


@pytest.fixture
def bearish_cache() -> MockCache:
    """하락 추세 데이터를 가진 MockCache fixture."""
    return make_trending_cache(trend=-0.002, seed=200)


@pytest.fixture
def neutral_cache() -> MockCache:
    """횡보 데이터를 가진 MockCache fixture."""
    return make_trending_cache(trend=0.0, seed=300)


@pytest.fixture
def empty_cache() -> MockCache:
    """빈 MockCache fixture."""
    return MockCache({})
