"""5-Layer Intelligence 시스템의 과거 성과를 백테스트.

과거 yfinance 데이터로 매일 분석을 시뮬레이션하고,
이후 N일 시장 수익률과 비교하여 시그널 정확도를 측정합니다.

사용법:
    from trading_bot.intelligence_backtest import IntelligenceBacktester
    bt = IntelligenceBacktester(lookback_years=2, forward_days=5)
    result = bt.run()
    print(result.summary)
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """인텔리전스 백테스트 결과."""

    total_days: int = 0

    # 핵심 지표
    information_coefficient: float = 0.0  # 점수-수익률 순위 상관 (Spearman)
    signal_hit_rate: float = 0.0          # 방향 맞춘 비율 (%)

    # 레이어별 성과
    layer_hit_rates: Dict[str, float] = field(default_factory=dict)
    layer_ic: Dict[str, float] = field(default_factory=dict)

    # 시계열 데이터
    daily_scores: Optional[pd.DataFrame] = None  # date, composite, layer scores, forward_return

    # 요약
    summary: str = ""


class IntelligenceBacktester:
    """5-Layer Intelligence 시스템의 과거 성과를 측정합니다.

    Args:
        lookback_years: 백테스트 기간 (기본 2년)
        forward_days: 시그널 후 성과 측정 기간 (기본 5일)
        warmup_days: 지표 안정화를 위한 워밍업 기간 (기본 130 거래일 ~ 6개월)
        step_days: 분석 간격 (기본 5 = 주 1회, 속도를 위해)
    """

    def __init__(
        self,
        lookback_years: int = 2,
        forward_days: int = 5,
        warmup_days: int = 130,
        step_days: int = 5,
    ):
        self.lookback_years = lookback_years
        self.forward_days = forward_days
        self.warmup_days = warmup_days
        self.step_days = step_days

    def run(self, symbols: Optional[List[str]] = None) -> BacktestResult:
        """전체 백테스트 실행.

        Flow:
        1. yfinance에서 전체 기간 데이터 한 번에 다운로드
        2. warmup 이후부터 step_days 간격으로:
           a. 해당 날짜까지의 데이터 슬라이스로 분석 실행
           b. forward_days 후의 SPY 수익률 기록
        3. 성과 지표 계산
        """
        import yfinance as yf
        from trading_bot.market_intelligence import MarketIntelligence
        from trading_bot.market_intelligence.data_fetcher import MarketDataCache, _get_all_symbols

        if symbols is None:
            symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL']

        # Step 1: 전체 기간 데이터 한 번에 다운로드
        total_period = f"{self.lookback_years + 1}y"  # 워밍업 포함
        logger.info(f"백테스트 데이터 다운로드 중 ({total_period})...")

        all_symbols = list(set(_get_all_symbols() + symbols + ['SPY']))

        try:
            raw = yf.download(
                tickers=all_symbols,
                period=total_period,
                interval='1d',
                group_by='ticker',
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.error(f"데이터 다운로드 실패: {e}")
            return BacktestResult(summary=f"데이터 다운로드 실패: {e}")

        # SPY 수익률 계산
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                spy_close = raw[('SPY', 'Close')].dropna()
            else:
                spy_close = raw['Close'].dropna()
        except (KeyError, TypeError):
            logger.error("SPY 데이터를 추출할 수 없습니다")
            return BacktestResult(summary="SPY 데이터 없음")

        spy_forward_returns = spy_close.pct_change(self.forward_days).shift(-self.forward_days)

        # Step 2: 날짜별 분석 루프
        all_dates = spy_close.index[self.warmup_days:-self.forward_days]
        if len(all_dates) == 0:
            return BacktestResult(summary="분석 가능한 날짜가 없습니다 (데이터 부족)")

        sample_dates = all_dates[::self.step_days]

        logger.info(
            f"백테스트 시작: {len(sample_dates)}개 샘플 "
            f"({sample_dates[0].date()} ~ {sample_dates[-1].date()})"
        )

        records = []

        for i, date in enumerate(sample_dates):
            try:
                # 해당 날짜까지의 데이터 슬라이스
                cache = self._build_cache_snapshot(raw, all_symbols, date)

                if cache is None:
                    continue

                # MarketIntelligence 분석 (FRED 없이, ETF 프록시만)
                mi = MarketIntelligence(period='6mo')
                mi.cache = cache

                # 최소한의 stocks_data 구성
                stocks_data = self._build_minimal_stocks(cache, symbols)

                report = mi.analyze(
                    stock_symbols=symbols,
                    stocks_data=stocks_data if stocks_data else None,
                )

                composite = report['overall']['score']
                signal = report['overall']['signal']
                forward_ret = spy_forward_returns.get(date)

                if forward_ret is None or pd.isna(forward_ret) or pd.isna(composite):
                    continue

                record = {
                    'date': date,
                    'composite_score': composite,
                    'signal': signal,
                    'forward_return': forward_ret,
                    'meta_confidence': report['overall'].get('meta_confidence', None),
                }

                # 레이어별 점수 기록
                for layer_key, layer_data in report.get('layers', {}).items():
                    score = layer_data.get('score', 0)
                    if not math.isnan(score):
                        record[f'layer_{layer_key}'] = score

                records.append(record)

                if (i + 1) % 20 == 0:
                    logger.info(f"  진행: {i+1}/{len(sample_dates)} ({date.date()})")

            except Exception as e:
                logger.debug(f"  {date.date()} 분석 실패: {e}")
                continue

        if not records:
            return BacktestResult(summary="분석 가능한 날짜가 없습니다")

        # Step 3: 성과 지표 계산
        df = pd.DataFrame(records)
        return self._compute_metrics(df)

    def _build_cache_snapshot(self, raw, symbols, end_date) -> Optional[Any]:
        """특정 날짜까지의 데이터로 MarketDataCache를 구성."""
        from trading_bot.market_intelligence.data_fetcher import MarketDataCache

        cache = MarketDataCache.__new__(MarketDataCache)
        cache.period = '6mo'
        cache.interval = '1d'
        cache._data = {}
        cache._fred_data = {}
        cache._fred_fetcher = None
        cache._fetched = True

        for sym in symbols:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    sym_data = raw[sym].loc[:end_date].dropna(how='all')
                else:
                    sym_data = raw.loc[:end_date].dropna(how='all')

                if len(sym_data) > 0:
                    # Standardize column names to PascalCase (yfinance standard)
                    col_map = {}
                    for col in sym_data.columns:
                        col_lower = col.lower() if isinstance(col, str) else str(col).lower()
                        pascal = col_lower.capitalize()
                        if col != pascal:
                            col_map[col] = pascal
                    if col_map:
                        sym_data = sym_data.rename(columns=col_map)
                    cache._data[sym] = sym_data
            except (KeyError, TypeError):
                continue

        return cache if cache._data else None

    def _build_minimal_stocks(self, cache, symbols) -> Optional[Dict]:
        """캐시에서 최소한의 종목 데이터를 구성."""
        from trading_bot.market_intelligence.scoring import calc_rsi

        stocks = {}
        for sym in symbols:
            df = cache.get(sym)
            if df is None or len(df) < 30:
                continue

            close = None
            for col in ('Close', 'close', 'Adj Close'):
                if col in df.columns:
                    close = df[col]
                    break

            if close is None or len(close) < 30:
                continue

            last_price = float(close.iloc[-1])
            rsi = calc_rsi(close)
            rsi_value = (
                float(rsi.iloc[-1])
                if not rsi.empty and not pd.isna(rsi.iloc[-1])
                else 50.0
            )

            stocks[sym] = {
                'price': {
                    'last': last_price,
                    'change_1d': (
                        float((close.iloc[-1] / close.iloc[-2] - 1) * 100)
                        if len(close) > 1
                        else 0
                    ),
                    'change_5d': (
                        float((close.iloc[-1] / close.iloc[-6] - 1) * 100)
                        if len(close) > 5
                        else 0
                    ),
                    'change_20d': (
                        float((close.iloc[-1] / close.iloc[-21] - 1) * 100)
                        if len(close) > 20
                        else 0
                    ),
                },
                'indicators': {
                    'rsi': {'value': rsi_value},
                    'macd': {'histogram': 0, 'signal': 'neutral', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.5},
                    'stochastic': {'k': 50, 'd': 50},
                    'adx': {'value': 20, 'trend': 'neutral'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            }

        return stocks if stocks else None

    def _compute_metrics(self, df: pd.DataFrame) -> BacktestResult:
        """백테스트 결과에서 성과 지표 계산."""
        result = BacktestResult()
        result.total_days = len(df)
        result.daily_scores = df

        # Information Coefficient (Spearman rank correlation)
        result.information_coefficient = self._safe_spearman(
            df['composite_score'], df['forward_return']
        )

        # Signal Hit Rate
        df['predicted_direction'] = df['composite_score'].apply(
            lambda x: 'up' if x > 20 else ('down' if x < -20 else 'neutral')
        )
        df['actual_direction'] = df['forward_return'].apply(
            lambda x: 'up' if x > 0 else 'down'
        )

        directional = df[df['predicted_direction'] != 'neutral']
        if len(directional) > 0:
            hits = (directional['predicted_direction'] == directional['actual_direction']).sum()
            result.signal_hit_rate = round(float(hits / len(directional) * 100), 1)

        # Layer-level IC and hit rates
        layer_cols = [c for c in df.columns if c.startswith('layer_')]
        for col in layer_cols:
            layer_name = col.replace('layer_', '')
            layer_scores = df[col].dropna()
            if len(layer_scores) > 10:
                result.layer_ic[layer_name] = self._safe_spearman(
                    layer_scores, df.loc[layer_scores.index, 'forward_return']
                )

                # Layer hit rate
                layer_pred = layer_scores.apply(
                    lambda x: 'up' if x > 20 else ('down' if x < -20 else 'neutral')
                )
                layer_dir = df.loc[layer_scores.index, 'forward_return'].apply(
                    lambda x: 'up' if x > 0 else 'down'
                )
                dir_mask = layer_pred != 'neutral'
                if dir_mask.sum() > 0:
                    layer_hits = (layer_pred[dir_mask] == layer_dir[dir_mask]).sum()
                    result.layer_hit_rates[layer_name] = round(
                        float(layer_hits / dir_mask.sum() * 100), 1
                    )

        # Summary
        lines = [
            "=== 5-Layer Intelligence 백테스트 결과 ===",
            (
                f"기간: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()} "
                f"({result.total_days}일 샘플)"
            ),
            "",
            "종합 성과:",
            f"  Information Coefficient: {result.information_coefficient:+.4f}",
            f"  시그널 적중률: {result.signal_hit_rate:.1f}%",
            "",
            "레이어별 IC (순위 상관):",
        ]

        sorted_layers = sorted(
            result.layer_ic.items(), key=lambda x: abs(x[1]), reverse=True
        )
        for name, ic in sorted_layers:
            hit = result.layer_hit_rates.get(name, 0)
            lines.append(f"  {name}: IC={ic:+.4f}, 적중률={hit:.1f}%")

        lines.extend([
            "",
            "해석:",
            "  IC > 0.05: 유용한 시그널",
            "  IC > 0.10: 우수한 시그널",
            "  적중률 > 55%: 유용",
        ])

        result.summary = "\n".join(lines)
        return result

    @staticmethod
    def _safe_spearman(x: pd.Series, y: pd.Series) -> float:
        """Spearman 순위 상관을 안전하게 계산.

        scipy가 있으면 scipy.stats.spearmanr 사용,
        없으면 pandas .corr(method='spearman') 폴백,
        둘 다 실패 시 numpy 기반 수동 계산.
        """
        try:
            from scipy import stats
            corr, _ = stats.spearmanr(x, y)
            return round(float(corr), 4) if not np.isnan(corr) else 0.0
        except ImportError:
            pass
        except Exception:
            return 0.0

        try:
            corr = x.corr(y, method='spearman')
            return round(float(corr), 4) if not np.isnan(corr) else 0.0
        except (ImportError, Exception):
            pass

        # numpy 기반 수동 Spearman 계산
        try:
            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            # NaN 제거
            mask = ~(np.isnan(x_arr) | np.isnan(y_arr))
            x_arr = x_arr[mask]
            y_arr = y_arr[mask]
            if len(x_arr) < 2:
                return 0.0
            # 상수 시리즈 체크 (분산 0이면 상관 정의 불가)
            if np.std(x_arr) == 0 or np.std(y_arr) == 0:
                return 0.0
            # 순위 계산 (argsort of argsort)
            x_ranks = np.empty_like(x_arr)
            x_ranks[np.argsort(x_arr)] = np.arange(len(x_arr), dtype=float)
            y_ranks = np.empty_like(y_arr)
            y_ranks[np.argsort(y_arr)] = np.arange(len(y_arr), dtype=float)
            # Pearson correlation of ranks
            x_mean = x_ranks.mean()
            y_mean = y_ranks.mean()
            x_diff = x_ranks - x_mean
            y_diff = y_ranks - y_mean
            num = (x_diff * y_diff).sum()
            denom = np.sqrt((x_diff ** 2).sum() * (y_diff ** 2).sum())
            if denom == 0:
                return 0.0
            corr = num / denom
            return round(float(corr), 4)
        except Exception:
            return 0.0
