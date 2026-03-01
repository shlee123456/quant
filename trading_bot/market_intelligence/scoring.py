"""
Shared scoring utilities for the Market Intelligence system.

모든 레이어에서 공통으로 사용하는 점수 계산 함수들을 제공합니다.
numpy/pandas만 사용합니다 (외부 TA 라이브러리 미사용).
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def percentile_rank(value: float, series: pd.Series) -> float:
    """시리즈 내에서 값의 백분위 순위를 계산.

    Args:
        value: 순위를 구할 값
        series: 비교 대상 시리즈

    Returns:
        0 ~ 100 범위의 백분위 순위. 데이터 부족 시 50.0 반환.
    """
    clean = series.dropna()
    if len(clean) == 0:
        return 50.0
    count_below = (clean < value).sum()
    return float(count_below / len(clean) * 100)


def rolling_z_score(series: pd.Series, window: int = 60) -> pd.Series:
    """롤링 Z-score 계산.

    Args:
        series: 입력 시리즈
        window: 롤링 윈도우 크기

    Returns:
        Z-score 시리즈 (NaN은 0.0으로 채움)
    """
    rolling_mean = series.rolling(window=window, min_periods=max(1, window // 2)).mean()
    rolling_std = series.rolling(window=window, min_periods=max(1, window // 2)).std()
    # std가 0인 경우 division by zero 방지
    z = (series - rolling_mean) / rolling_std.replace(0, np.nan)
    return z.fillna(0.0)


def momentum_score(series: pd.Series, periods: Optional[List[int]] = None) -> float:
    """다중 기간 모멘텀 점수를 계산.

    각 기간의 수익률을 계산하고 평균을 취합니다.
    짧은 기간의 모멘텀이 더 최신 정보를 반영합니다.

    Args:
        series: 가격 시리즈 (Close 등)
        periods: 모멘텀 계산 기간 리스트 (기본: [5, 10, 20])

    Returns:
        -100 ~ +100 범위의 모멘텀 점수. 데이터 부족 시 0.0.
    """
    if periods is None:
        periods = [5, 10, 20]

    clean = series.dropna()
    if len(clean) < 2:
        return 0.0

    returns = []
    for p in periods:
        ret = pct_change(clean, p)
        if ret is not None:
            returns.append(ret)

    if not returns:
        return 0.0

    # 수익률 평균을 -100..+100으로 스케일링
    # 일반적으로 5~20일 수익률은 -20% ~ +20% 범위
    avg_return = np.mean(returns)
    # 20%를 100점으로 매핑
    score = avg_return / 0.20 * 100
    return float(max(-100.0, min(100.0, score)))


def weighted_composite(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    """가중 합성 점수 계산.

    Args:
        scores: {메트릭명: 점수} 딕셔너리
        weights: {메트릭명: 가중치} 딕셔너리

    Returns:
        가중 합성 점수. scores와 weights에 공통 키가 없으면 0.0.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for key, weight in weights.items():
        if key in scores and not np.isnan(scores[key]):
            weighted_sum += scores[key] * weight
            total_weight += weight

    if total_weight == 0.0:
        return 0.0

    return weighted_sum / total_weight


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) 계산.

    MarketAnalyzer와 동일한 EWM 방식을 사용합니다.

    Args:
        close: 종가 시리즈
        period: RSI 기간 (기본 14)

    Returns:
        0 ~ 100 범위의 RSI 시리즈
    """
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gains = gains.ewm(span=period, min_periods=period, adjust=False).mean()
    avg_losses = losses.ewm(span=period, min_periods=period, adjust=False).mean()
    rs = avg_gains / avg_losses.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def pct_change(series: pd.Series, periods: int) -> Optional[float]:
    """주어진 기간의 퍼센트 변화율을 계산.

    Args:
        series: 가격 시리즈
        periods: 기간 (일수)

    Returns:
        퍼센트 변화율 (0.05 = 5%). 데이터 부족 시 None.
    """
    clean = series.dropna()
    if len(clean) <= periods:
        return None

    current = clean.iloc[-1]
    past = clean.iloc[-1 - periods]

    if past == 0 or np.isnan(past) or np.isnan(current):
        return None

    return float((current - past) / past)
