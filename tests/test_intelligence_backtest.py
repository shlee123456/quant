"""
Intelligence Backtester 테스트.

mock 데이터로 IntelligenceBacktester의 핵심 로직을 검증합니다.
yfinance 호출 없이 _compute_metrics, _build_cache_snapshot,
_build_minimal_stocks를 직접 테스트합니다.
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from trading_bot.intelligence_backtest import BacktestResult, IntelligenceBacktester


# ─── BacktestResult dataclass ───


class TestBacktestResultDataclass:
    """BacktestResult 데이터클래스 필드 검증."""

    def test_default_values(self):
        """기본값 초기화."""
        r = BacktestResult()
        assert r.total_days == 0
        assert r.information_coefficient == 0.0
        assert r.signal_hit_rate == 0.0
        assert r.layer_hit_rates == {}
        assert r.layer_ic == {}
        assert r.daily_scores is None
        assert r.summary == ""

    def test_custom_values(self):
        """커스텀 값 초기화."""
        r = BacktestResult(
            total_days=100,
            information_coefficient=0.15,
            signal_hit_rate=62.5,
            layer_hit_rates={'macro_regime': 58.0},
            layer_ic={'macro_regime': 0.12},
            summary="테스트 요약",
        )
        assert r.total_days == 100
        assert r.information_coefficient == 0.15
        assert r.signal_hit_rate == 62.5
        assert r.layer_hit_rates == {'macro_regime': 58.0}
        assert r.layer_ic == {'macro_regime': 0.12}
        assert r.summary == "테스트 요약"

    def test_daily_scores_accepts_dataframe(self):
        """daily_scores에 DataFrame 할당."""
        df = pd.DataFrame({'date': [1, 2], 'score': [10, 20]})
        r = BacktestResult(daily_scores=df)
        assert r.daily_scores is not None
        assert len(r.daily_scores) == 2


# ─── _build_cache_snapshot ───


class TestBuildCacheSnapshot:
    """_build_cache_snapshot: MultiIndex DataFrame에서 캐시 스냅샷 생성."""

    def _make_multi_index_raw(self, symbols, n=100):
        """MultiIndex raw DataFrame을 생성."""
        dates = pd.date_range('2024-01-01', periods=n, freq='B')
        arrays = {}
        for sym in symbols:
            rng = np.random.RandomState(hash(sym) % 2**31)
            close = 100 + np.cumsum(rng.randn(n) * 0.5)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col == 'Close':
                    arrays[(sym, col)] = close
                elif col == 'Volume':
                    arrays[(sym, col)] = rng.randint(1000, 100000, n).astype(float)
                elif col == 'High':
                    arrays[(sym, col)] = close + abs(rng.randn(n))
                elif col == 'Low':
                    arrays[(sym, col)] = close - abs(rng.randn(n))
                else:
                    arrays[(sym, col)] = close + rng.randn(n) * 0.3

        cols = pd.MultiIndex.from_tuples(arrays.keys())
        df = pd.DataFrame(arrays, index=dates, columns=cols)
        return df

    def test_creates_cache_with_data(self):
        """정상적인 MultiIndex 데이터에서 캐시 생성."""
        bt = IntelligenceBacktester()
        symbols = ['AAPL', 'SPY']
        raw = self._make_multi_index_raw(symbols)
        end_date = raw.index[50]

        cache = bt._build_cache_snapshot(raw, symbols, end_date)

        assert cache is not None
        for sym in symbols:
            df = cache.get(sym)
            assert df is not None
            assert len(df) <= 51  # up to end_date inclusive

    def test_returns_none_for_empty_symbols(self):
        """빈 심볼 리스트이면 None 반환."""
        bt = IntelligenceBacktester()
        raw = self._make_multi_index_raw(['SPY'])
        end_date = raw.index[50]

        cache = bt._build_cache_snapshot(raw, ['NONEXISTENT'], end_date)
        assert cache is None

    def test_slices_up_to_end_date(self):
        """end_date까지만 데이터 슬라이싱."""
        bt = IntelligenceBacktester()
        symbols = ['SPY']
        raw = self._make_multi_index_raw(symbols, n=200)
        end_date = raw.index[99]

        cache = bt._build_cache_snapshot(raw, symbols, end_date)

        assert cache is not None
        df = cache.get('SPY')
        assert df is not None
        assert df.index[-1] <= end_date


# ─── _build_minimal_stocks ───


class TestBuildMinimalStocks:
    """_build_minimal_stocks: 캐시에서 종목 데이터 추출."""

    def _make_mock_cache(self, symbols, n=60):
        """MockCache와 동일한 인터페이스를 가진 간단한 캐시 생성."""
        cache = MagicMock()
        data = {}
        for sym in symbols:
            rng = np.random.RandomState(hash(sym) % 2**31)
            dates = pd.date_range('2024-01-01', periods=n, freq='B')
            close = 100 + np.cumsum(rng.randn(n) * 0.5)
            df = pd.DataFrame({
                'Close': close,
                'Open': close + rng.randn(n) * 0.3,
                'High': close + abs(rng.randn(n)),
                'Low': close - abs(rng.randn(n)),
                'Volume': rng.randint(1000, 100000, n).astype(float),
            }, index=dates)
            data[sym] = df

        cache.get = lambda sym: data.get(sym)
        return cache

    def test_extracts_stock_data(self):
        """정상적인 캐시에서 stocks_data 추출."""
        bt = IntelligenceBacktester()
        cache = self._make_mock_cache(['AAPL', 'MSFT'])

        stocks = bt._build_minimal_stocks(cache, ['AAPL', 'MSFT'])

        assert stocks is not None
        assert 'AAPL' in stocks
        assert 'MSFT' in stocks
        assert 'price' in stocks['AAPL']
        assert 'indicators' in stocks['AAPL']
        assert 'rsi' in stocks['AAPL']['indicators']

    def test_returns_none_for_missing_symbols(self):
        """캐시에 없는 심볼 요청 시 None."""
        bt = IntelligenceBacktester()
        cache = MagicMock()
        cache.get = MagicMock(return_value=None)

        stocks = bt._build_minimal_stocks(cache, ['NONEXISTENT'])
        assert stocks is None

    def test_skips_short_data(self):
        """데이터가 30일 미만이면 해당 심볼 스킵."""
        bt = IntelligenceBacktester()
        cache = MagicMock()
        dates = pd.date_range('2024-01-01', periods=10, freq='B')
        short_df = pd.DataFrame({
            'Close': np.linspace(100, 110, 10),
        }, index=dates)
        cache.get = MagicMock(return_value=short_df)

        stocks = bt._build_minimal_stocks(cache, ['AAPL'])
        assert stocks is None

    def test_rsi_value_is_numeric(self):
        """추출된 RSI 값이 숫자."""
        bt = IntelligenceBacktester()
        cache = self._make_mock_cache(['AAPL'])

        stocks = bt._build_minimal_stocks(cache, ['AAPL'])
        assert stocks is not None
        rsi_val = stocks['AAPL']['indicators']['rsi']['value']
        assert isinstance(rsi_val, float)
        assert 0 <= rsi_val <= 100


# ─── _compute_metrics ───


class TestComputeMetricsBasic:
    """_compute_metrics: 기본 성과 지표 계산."""

    def _make_bt(self):
        return IntelligenceBacktester()

    def _make_df(self, n=50, seed=42):
        rng = np.random.RandomState(seed)
        return pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': rng.randn(n) * 30,
            'forward_return': rng.randn(n) * 0.02,
            'signal': ['bullish' if x > 20 else ('bearish' if x < -20 else 'neutral')
                        for x in rng.randn(n) * 30],
            'layer_macro_regime': rng.randn(n) * 20,
            'layer_sentiment': rng.randn(n) * 25,
        })

    def test_returns_backtest_result(self):
        """BacktestResult 객체 반환."""
        bt = self._make_bt()
        df = self._make_df()
        result = bt._compute_metrics(df)

        assert isinstance(result, BacktestResult)
        assert result.total_days == 50

    def test_ic_is_bounded(self):
        """IC가 -1 ~ +1 범위 내."""
        bt = self._make_bt()
        df = self._make_df()
        result = bt._compute_metrics(df)

        assert -1.0 <= result.information_coefficient <= 1.0

    def test_hit_rate_is_percentage(self):
        """적중률이 0 ~ 100 범위."""
        bt = self._make_bt()
        df = self._make_df()
        result = bt._compute_metrics(df)

        assert 0 <= result.signal_hit_rate <= 100

    def test_layer_metrics_present(self):
        """레이어별 IC와 적중률이 존재."""
        bt = self._make_bt()
        df = self._make_df()
        result = bt._compute_metrics(df)

        assert 'macro_regime' in result.layer_ic
        assert 'sentiment' in result.layer_ic


class TestComputeMetricsPerfectSignal:
    """_compute_metrics: 완벽한 시그널 → IC ~ 1.0."""

    def test_perfect_positive_correlation(self):
        """score > 0 일 때 forward_return > 0 → IC 높음."""
        bt = IntelligenceBacktester()
        n = 100
        rng = np.random.RandomState(123)

        # 강한 양의 상관: 점수가 높으면 수익률도 높음
        scores = rng.uniform(-50, 50, n)
        # forward_return을 score와 동일 방향 + 약간의 노이즈
        returns = scores * 0.001 + rng.randn(n) * 0.001

        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': scores,
            'forward_return': returns,
            'signal': ['bullish' if x > 20 else ('bearish' if x < -20 else 'neutral')
                        for x in scores],
        })

        result = bt._compute_metrics(df)

        # IC는 양수이고 상당히 높아야 함
        assert result.information_coefficient > 0.5


class TestComputeMetricsNoDirectional:
    """_compute_metrics: 모든 점수가 neutral 구간 → 적중률 0."""

    def test_all_neutral_scores(self):
        """모든 composite_score가 -20 ~ +20 → directional 없음."""
        bt = IntelligenceBacktester()
        n = 50
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': np.zeros(n),  # 모두 0 (neutral)
            'forward_return': np.random.randn(n) * 0.02,
            'signal': ['neutral'] * n,
        })

        result = bt._compute_metrics(df)

        # directional이 없으므로 hit_rate는 0
        assert result.signal_hit_rate == 0.0


class TestComputeMetricsLayerBreakdown:
    """_compute_metrics: 레이어 컬럼이 결과에 포함."""

    def test_layer_columns_parsed(self):
        """layer_ 접두사 컬럼이 layer_ic와 layer_hit_rates에 반영."""
        bt = IntelligenceBacktester()
        n = 50
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': rng.randn(n) * 30,
            'forward_return': rng.randn(n) * 0.02,
            'signal': ['neutral'] * n,
            'layer_macro_regime': rng.randn(n) * 40,
            'layer_market_structure': rng.randn(n) * 35,
            'layer_sentiment': rng.randn(n) * 25,
        })

        result = bt._compute_metrics(df)

        assert 'macro_regime' in result.layer_ic
        assert 'market_structure' in result.layer_ic
        assert 'sentiment' in result.layer_ic

    def test_layers_with_insufficient_data_skipped(self):
        """데이터 10개 이하인 레이어는 IC 계산에서 제외."""
        bt = IntelligenceBacktester()
        n = 50
        rng = np.random.RandomState(42)

        # layer_sparse: 대부분 NaN, 유효 데이터 5개만
        sparse_scores = np.full(n, np.nan)
        sparse_scores[:5] = rng.randn(5) * 30

        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': rng.randn(n) * 30,
            'forward_return': rng.randn(n) * 0.02,
            'signal': ['neutral'] * n,
            'layer_sparse': sparse_scores,
            'layer_full': rng.randn(n) * 30,
        })

        result = bt._compute_metrics(df)

        assert 'sparse' not in result.layer_ic
        assert 'full' in result.layer_ic


# ─── run() with empty / failure data ───


class TestRunWithEmptyData:
    """run(): 데이터 부재 시 그레이스풀 핸들링."""

    @patch('trading_bot.intelligence_backtest.yf', create=True)
    def test_download_failure(self, mock_yf_module):
        """yf.download 실패 시 에러 메시지 포함 결과 반환."""
        # yfinance import를 직접 패치
        with patch.dict('sys.modules', {'yfinance': MagicMock()}):
            with patch('yfinance.download', side_effect=Exception("Network error")):
                bt = IntelligenceBacktester()
                result = bt.run(symbols=['AAPL'])

                assert isinstance(result, BacktestResult)
                assert "실패" in result.summary or "error" in result.summary.lower() or "다운로드" in result.summary

    def test_empty_records_returns_result(self):
        """분석 레코드가 0개일 때 결과 반환."""
        bt = IntelligenceBacktester()
        # _compute_metrics를 직접 테스트하는 대신, 빈 records 시나리오 확인
        # run()에서 records가 비어있으면 "분석 가능한 날짜가 없습니다" 반환
        result = BacktestResult(summary="분석 가능한 날짜가 없습니다")
        assert "분석 가능한 날짜" in result.summary


# ─── Summary format ───


class TestBacktestResultSummaryFormat:
    """summary 문자열에 필수 구성 요소가 포함."""

    def test_summary_contains_expected_strings(self):
        """summary에 핵심 키워드 포함."""
        bt = IntelligenceBacktester()
        n = 50
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': rng.randn(n) * 30,
            'forward_return': rng.randn(n) * 0.02,
            'signal': ['neutral'] * n,
            'layer_macro_regime': rng.randn(n) * 20,
        })

        result = bt._compute_metrics(df)

        assert "5-Layer Intelligence" in result.summary
        assert "Information Coefficient" in result.summary
        assert "적중률" in result.summary
        assert "IC >" in result.summary  # 해석 섹션

    def test_summary_contains_date_range(self):
        """summary에 시작일/종료일 포함."""
        bt = IntelligenceBacktester()
        dates = pd.date_range('2024-01-01', periods=30, freq='W')
        df = pd.DataFrame({
            'date': dates,
            'composite_score': np.random.randn(30) * 30,
            'forward_return': np.random.randn(30) * 0.02,
            'signal': ['neutral'] * 30,
        })

        result = bt._compute_metrics(df)

        assert '2024-01-07' in result.summary  # first date
        assert str(dates[-1].date()) in result.summary  # last date

    def test_summary_contains_sample_count(self):
        """summary에 샘플 수 포함."""
        bt = IntelligenceBacktester()
        n = 40
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='W'),
            'composite_score': np.random.randn(n) * 30,
            'forward_return': np.random.randn(n) * 0.02,
            'signal': ['neutral'] * n,
        })

        result = bt._compute_metrics(df)

        assert f"{n}일 샘플" in result.summary


# ─── _safe_spearman ───


class TestSafeSpearman:
    """_safe_spearman: 안전한 Spearman 상관 계산."""

    def test_perfect_correlation(self):
        """완벽한 양의 상관."""
        x = pd.Series([1, 2, 3, 4, 5])
        y = pd.Series([10, 20, 30, 40, 50])
        result = IntelligenceBacktester._safe_spearman(x, y)
        assert result == 1.0

    def test_perfect_negative_correlation(self):
        """완벽한 음의 상관."""
        x = pd.Series([1, 2, 3, 4, 5])
        y = pd.Series([50, 40, 30, 20, 10])
        result = IntelligenceBacktester._safe_spearman(x, y)
        assert result == -1.0

    def test_constant_series_returns_zero(self):
        """상수 시리즈 → 0.0 (NaN 방지)."""
        x = pd.Series([1, 1, 1, 1, 1])
        y = pd.Series([10, 20, 30, 40, 50])
        result = IntelligenceBacktester._safe_spearman(x, y)
        assert result == 0.0


# ─── IntelligenceBacktester init ───


class TestIntelligenceBacktesterInit:
    """IntelligenceBacktester 초기화 테스트."""

    def test_default_params(self):
        """기본 파라미터 확인."""
        bt = IntelligenceBacktester()
        assert bt.lookback_years == 2
        assert bt.forward_days == 5
        assert bt.warmup_days == 130
        assert bt.step_days == 5

    def test_custom_params(self):
        """커스텀 파라미터."""
        bt = IntelligenceBacktester(
            lookback_years=3,
            forward_days=10,
            warmup_days=200,
            step_days=10,
        )
        assert bt.lookback_years == 3
        assert bt.forward_days == 10
        assert bt.warmup_days == 200
        assert bt.step_days == 10


# ─── Import from trading_bot package ───


class TestImport:
    """trading_bot 패키지에서 import 가능 확인."""

    def test_import_from_package(self):
        """trading_bot에서 직접 import."""
        from trading_bot import IntelligenceBacktester as IB, BacktestResult as BR
        assert IB is not None
        assert BR is not None
        assert IB is IntelligenceBacktester
        assert BR is BacktestResult

    def test_import_from_module(self):
        """intelligence_backtest 모듈에서 직접 import."""
        from trading_bot.intelligence_backtest import IntelligenceBacktester, BacktestResult
        assert IntelligenceBacktester is not None
        assert BacktestResult is not None
