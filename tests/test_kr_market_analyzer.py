"""
KRMarketAnalyzer 통합 검증 테스트

SimulationDataGenerator로 모의 데이터를 생성하여
실제 KIS API 없이 전체 파이프라인을 검증합니다.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest

from trading_bot.kr_market_analyzer import (
    KRMarketAnalyzer,
    KRX_TOP_SYMBOLS,
    KR_STOCK_NAMES,
)
from trading_bot.simulation_data import SimulationDataGenerator


# ─── Fixtures ───


@pytest.fixture
def sample_ohlcv():
    """SimulationDataGenerator로 200봉 OHLCV 데이터 생성"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_ohlcv(periods=200, initial_price=65000.0)


@pytest.fixture
def mock_broker(sample_ohlcv):
    """fetch_ohlcv를 모킹한 가짜 브로커 (overseas=False)"""
    broker = MagicMock()
    broker.fetch_ohlcv.return_value = sample_ohlcv
    broker.fetch_ticker.return_value = {
        'per': 12.5,
        'pbr': 1.3,
        'eps': 5200,
        'bps': 50000,
        'sector': '반도체',
    }
    return broker


@pytest.fixture
def analyzer():
    return KRMarketAnalyzer(ohlcv_limit=200, api_delay=0.0)


# ─── 지표 계산 테스트 ───


class TestKRMarketAnalyzerIndicators:
    """지표 계산 정확성 테스트"""

    def test_calc_rsi_range(self, sample_ohlcv):
        """RSI 값이 0~100 범위 내인지 확인"""
        rsi = KRMarketAnalyzer._calc_rsi(sample_ohlcv['close'], period=14)
        valid = rsi.dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_calc_macd_components(self, sample_ohlcv):
        """MACD 구성요소가 올바르게 계산되는지 확인"""
        macd_line, signal_line, histogram = KRMarketAnalyzer._calc_macd(sample_ohlcv['close'])
        assert len(macd_line) == len(sample_ohlcv)
        assert len(signal_line) == len(sample_ohlcv)
        np.testing.assert_allclose(
            histogram.dropna().values,
            (macd_line - signal_line).dropna().values,
            rtol=1e-10
        )

    def test_calc_bollinger_bands(self, sample_ohlcv):
        """볼린저 밴드: upper > middle > lower 관계 확인"""
        upper, middle, lower = KRMarketAnalyzer._calc_bollinger(sample_ohlcv['close'])
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()

    def test_calc_stochastic_range(self, sample_ohlcv):
        """스토캐스틱 %K, %D가 0~100 범위 내인지 확인"""
        k, d = KRMarketAnalyzer._calc_stochastic(
            sample_ohlcv['high'], sample_ohlcv['low'], sample_ohlcv['close']
        )
        valid_k = k.dropna()
        valid_d = d.dropna()
        assert valid_k.min() >= 0
        assert valid_k.max() <= 100
        assert valid_d.min() >= 0
        assert valid_d.max() <= 100

    def test_calc_pct_b(self):
        """Bollinger %B 계산"""
        assert KRMarketAnalyzer._calc_pct_b(65000.0, 70000.0, 60000.0) == 0.5
        assert KRMarketAnalyzer._calc_pct_b(70000.0, 70000.0, 60000.0) == 1.0
        assert KRMarketAnalyzer._calc_pct_b(60000.0, 70000.0, 60000.0) == 0.0
        assert KRMarketAnalyzer._calc_pct_b(65000.0, 65000.0, 65000.0) == 0.5


# ─── 분류 헬퍼 테스트 ───


class TestKRMarketAnalyzerClassifiers:
    """분류 헬퍼 테스트"""

    def test_classify_rsi(self):
        assert KRMarketAnalyzer._classify_rsi(15)[0] == 'oversold'
        assert KRMarketAnalyzer._classify_rsi(30)[0] == 'near_oversold'
        assert KRMarketAnalyzer._classify_rsi(50)[0] == 'neutral'
        assert KRMarketAnalyzer._classify_rsi(70)[0] == 'near_overbought'
        assert KRMarketAnalyzer._classify_rsi(85)[0] == 'overbought'

    def test_classify_bollinger(self):
        assert KRMarketAnalyzer._classify_bollinger(-0.1) == 'below_lower'
        assert KRMarketAnalyzer._classify_bollinger(0.1) == 'near_lower'
        assert KRMarketAnalyzer._classify_bollinger(0.5) == 'neutral'
        assert KRMarketAnalyzer._classify_bollinger(0.9) == 'near_upper'
        assert KRMarketAnalyzer._classify_bollinger(1.1) == 'above_upper'

    def test_classify_stochastic(self):
        assert KRMarketAnalyzer._classify_stochastic(10, 10) == 'oversold_zone'
        assert KRMarketAnalyzer._classify_stochastic(90, 90) == 'overbought_zone'
        assert KRMarketAnalyzer._classify_stochastic(50, 50) == 'neutral'

    def test_classify_adx(self):
        assert KRMarketAnalyzer._classify_adx(10) == 'no_trend'
        assert KRMarketAnalyzer._classify_adx(20) == 'weak_trend'
        assert KRMarketAnalyzer._classify_adx(30) == 'moderate_trend'
        assert KRMarketAnalyzer._classify_adx(50) == 'strong_trend'


# ─── 패턴 감지 테스트 ───


class TestKRMarketAnalyzerPatterns:
    """패턴 감지 테스트"""

    def test_detect_patterns_short_data(self, analyzer):
        short_prices = np.array([65000.0] * 10)
        result = analyzer._detect_patterns(short_prices)
        assert result['double_bottom'] is False
        assert result['support_levels'] == []

    def test_detect_patterns_returns_support_levels(self, analyzer):
        gen = SimulationDataGenerator(seed=99)
        df = gen.generate_volatile_data(periods=100, initial_price=65000.0)
        result = analyzer._detect_patterns(df['close'].values)
        assert isinstance(result['support_levels'], list)


# ─── 시그널 진단 테스트 ───


class TestKRMarketAnalyzerDiagnosis:
    """시그널 진단 테스트"""

    def test_diagnose_signals_oversold(self, analyzer):
        indicators = {'rsi': {'value': 25.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(25.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is True
        assert result['rsi_35_65']['sell_triggered'] is False

    def test_diagnose_signals_overbought(self, analyzer):
        indicators = {'rsi': {'value': 75.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(75.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is False
        assert result['rsi_35_65']['sell_triggered'] is True

    def test_diagnose_signals_neutral(self, analyzer):
        indicators = {'rsi': {'value': 50.0}, 'macd': {}, 'bollinger': {}, 'stochastic': {}, 'adx': {}}
        result = analyzer._diagnose_signals(50.0, indicators)
        assert result['rsi_35_65']['buy_triggered'] is False
        assert result['rsi_35_65']['sell_triggered'] is False


# ─── 통합 테스트 ───


class TestKRMarketAnalyzerIntegration:
    """전체 분석 파이프라인 통합 테스트 (overseas=False)"""

    def test_analyze_single_symbol(self, analyzer, mock_broker):
        """단일 종목 분석"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )

        assert 'date' in results
        assert results['market'] == 'kr'
        assert 'market_summary' in results
        assert 'stocks' in results
        assert '005930' in results['stocks']

        stock = results['stocks']['005930']
        assert 'name' in stock
        assert stock['name'] == '삼성전자'
        assert 'price' in stock
        assert 'indicators' in stock
        assert 'regime' in stock
        assert 'patterns' in stock
        assert 'signal_diagnosis' in stock

    def test_analyze_calls_overseas_false(self, analyzer, mock_broker):
        """overseas=False로 호출되는지 확인"""
        analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )

        call_kwargs = mock_broker.fetch_ohlcv.call_args[1]
        assert call_kwargs['overseas'] is False

    def test_analyze_multiple_symbols(self, analyzer, mock_broker):
        """여러 종목 동시 분석"""
        symbols = ['005930', '000660', '005380']
        results = analyzer.analyze(
            symbols, mock_broker,
            collect_news=False, collect_events=False,
        )

        assert results['market_summary']['total_stocks'] == 3
        for sym in symbols:
            assert sym in results['stocks']

    def test_analyze_with_failed_symbol(self, analyzer):
        """일부 종목 조회 실패 시 나머지는 정상 분석"""
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_ohlcv(periods=200, initial_price=65000.0)

        broker = MagicMock()

        def side_effect(**kwargs):
            symbol = kwargs.get('symbol', '')
            if symbol == 'FAIL_SYM':
                raise Exception("API Error")
            return df

        broker.fetch_ohlcv.side_effect = side_effect
        broker.fetch_ticker.return_value = None

        results = analyzer.analyze(
            ['FAIL_SYM', 'GOOD_SYM'], broker,
            collect_news=False, collect_events=False,
        )
        assert 'FAIL_SYM' not in results['stocks']
        assert 'GOOD_SYM' in results['stocks']

    def test_analyze_all_fail(self, analyzer):
        """모든 종목 실패 시 빈 결과 반환"""
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = None

        results = analyzer.analyze(
            ['BAD1', 'BAD2'], broker,
            collect_news=False, collect_events=False,
        )
        assert results['stocks'] == {}
        assert results['market_summary'] == {}
        assert results['market'] == 'kr'

    def test_indicator_structure(self, analyzer, mock_broker):
        """지표 딕셔너리 구조 검증"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )
        indicators = results['stocks']['005930']['indicators']

        assert 'value' in indicators['rsi']
        assert 'signal' in indicators['rsi']
        assert 'zone' in indicators['rsi']
        assert isinstance(indicators['rsi']['value'], float)

        assert 'histogram' in indicators['macd']
        assert 'signal' in indicators['macd']
        assert 'cross_recent' in indicators['macd']
        assert isinstance(indicators['macd']['cross_recent'], bool)

        assert 'pct_b' in indicators['bollinger']
        assert 'signal' in indicators['bollinger']

        assert 'k' in indicators['stochastic']
        assert 'd' in indicators['stochastic']
        assert 'signal' in indicators['stochastic']

        assert 'value' in indicators['adx']
        assert 'trend' in indicators['adx']

    def test_market_summary_structure(self, analyzer, mock_broker):
        """시장 요약 구조 검증"""
        results = analyzer.analyze(
            ['005930', '000660', '005380'], mock_broker,
            collect_news=False, collect_events=False,
        )
        summary = results['market_summary']

        assert summary['total_stocks'] == 3
        assert isinstance(summary['bullish_count'], int)
        assert isinstance(summary['bearish_count'], int)
        assert isinstance(summary['sideways_count'], int)
        assert isinstance(summary['avg_rsi'], float)
        assert summary['market_sentiment'] in ['강한 약세', '약세', '중립', '강세', '강한 강세']
        assert isinstance(summary['notable_events'], list)

    def test_regime_structure(self, analyzer, mock_broker):
        """레짐 감지 결과 구조 검증"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )
        regime = results['stocks']['005930']['regime']

        assert 'state' in regime
        assert 'confidence' in regime
        assert regime['state'] in ['BULLISH', 'BEARISH', 'SIDEWAYS', 'VOLATILE', 'UNKNOWN']
        assert 0.0 <= regime['confidence'] <= 1.0

    def test_fundamentals_collected(self, analyzer, mock_broker):
        """펀더멘탈 데이터가 수집되는지 확인"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )
        stock = results['stocks']['005930']

        assert 'fundamentals' in stock
        assert stock['fundamentals']['per'] == 12.5
        assert stock['fundamentals']['sector'] == '반도체'


# ─── JSON 저장 테스트 ───


class TestKRMarketAnalyzerSaveJson:
    """JSON 저장 테스트"""

    def test_save_json_creates_kr_file(self, analyzer, mock_broker):
        """JSON 파일이 {date}_kr.json으로 생성되는지 확인"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)
            assert Path(path).exists()
            assert path.endswith('_kr.json')

            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            assert loaded['date'] == results['date']
            assert loaded['market'] == 'kr'
            assert '005930' in loaded['stocks']

    def test_save_json_roundtrip(self, analyzer, mock_broker):
        """저장 후 다시 로드했을 때 데이터 무결성 확인"""
        results = analyzer.analyze(
            ['005930', '000660'], mock_broker,
            collect_news=False, collect_events=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = analyzer.save_json(results, output_dir=tmpdir)

            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            assert len(loaded['stocks']) == len(results['stocks'])
            for sym in results['stocks']:
                assert loaded['stocks'][sym]['indicators']['rsi']['value'] == \
                       results['stocks'][sym]['indicators']['rsi']['value']


# ─── 뉴스 통합 테스트 ───


class TestKRMarketAnalyzerNewsIntegration:
    """뉴스 수집 통합 테스트"""

    def test_analyze_with_news(self, analyzer, mock_broker):
        """collect_news=True 시 뉴스 수집 시도"""
        with patch('trading_bot.kr_market_analyzer.KRNewsCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = {
                'collected_at': '2026-03-18T09:00:00',
                'market_news': [{'title': '코스피 상승', 'source': '한경', 'published': '2026-03-18', 'link': ''}],
                'stock_news': {
                    '005930': [{'title': '삼성전자 실적', 'source': '매일경제', 'published': '2026-03-18', 'link': ''}]
                }
            }

            results = analyzer.analyze(
                ['005930'], mock_broker,
                collect_news=True, collect_events=False,
            )

            assert 'news' in results
            assert len(results['news']['market_news']) == 1

    def test_analyze_without_news(self, analyzer, mock_broker):
        """collect_news=False 시 news 키 없음"""
        results = analyzer.analyze(
            ['005930'], mock_broker,
            collect_news=False, collect_events=False,
        )
        assert 'news' not in results


# ─── 이벤트 통합 테스트 ───


class TestKRMarketAnalyzerEventsIntegration:
    """이벤트 캘린더 통합 테스트"""

    def test_analyze_with_events(self, analyzer, mock_broker):
        """collect_events=True 시 이벤트 수집"""
        with patch('trading_bot.kr_market_analyzer.KREventCalendarCollector') as MockCollector:
            mock_instance = MockCollector.return_value
            mock_instance.collect.return_value = {
                'collected_at': '2026-03-18 09:00:00',
                'bok_rate': {'next_date': '2026-04-10', 'days_until': 23, 'remaining_2026': ['2026-04-10']},
                'economic': {'cpi': {'next_date': '2026-04-02', 'days_until': 15}},
                'options': {'monthly_expiry': {'next_date': '2026-04-09', 'days_until': 22}},
                'market_structure': {'krx_rebalance': {'next_date': '2026-06-12', 'days_until': 86}},
                'holidays': {'next_holiday': {'date': '2026-05-05', 'name': '어린이날', 'days_until': 48}},
            }

            results = analyzer.analyze(
                ['005930'], mock_broker,
                collect_news=False, collect_events=True,
            )

            assert 'events' in results
            assert results['events']['bok_rate']['next_date'] == '2026-04-10'


# ─── 다양한 시장 상황 테스트 ───


class TestKRMarketAnalyzerMarketConditions:
    """다양한 시장 조건에서의 분석 검증"""

    def test_bullish_market(self):
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=200, trend='bullish', initial_price=65000.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df
        broker.fetch_ticker.return_value = None

        analyzer = KRMarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(
            ['005930'], broker,
            collect_news=False, collect_events=False,
        )

        assert '005930' in results['stocks']
        rsi = results['stocks']['005930']['indicators']['rsi']['value']
        assert rsi > 20

    def test_bearish_market(self):
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=200, trend='bearish', initial_price=85000.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df
        broker.fetch_ticker.return_value = None

        analyzer = KRMarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(
            ['005930'], broker,
            collect_news=False, collect_events=False,
        )

        assert '005930' in results['stocks']
        rsi = results['stocks']['005930']['indicators']['rsi']['value']
        assert rsi < 80

    def test_volatile_market(self):
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_volatile_data(periods=200, initial_price=65000.0)
        broker = MagicMock()
        broker.fetch_ohlcv.return_value = df
        broker.fetch_ticker.return_value = None

        analyzer = KRMarketAnalyzer(api_delay=0.0)
        results = analyzer.analyze(
            ['005930'], broker,
            collect_news=False, collect_events=False,
        )

        assert '005930' in results['stocks']
        pct_b = results['stocks']['005930']['indicators']['bollinger']['pct_b']
        assert isinstance(pct_b, float)


# ─── 상수 검증 테스트 ───


class TestKRMarketAnalyzerConstants:
    """상수 및 매핑 검증"""

    def test_krx_top_symbols_count(self):
        assert len(KRX_TOP_SYMBOLS) == 16

    def test_kr_stock_names_coverage(self):
        """모든 KRX_TOP_SYMBOLS에 대해 한글명이 매핑되어 있는지"""
        for symbol in KRX_TOP_SYMBOLS:
            assert symbol in KR_STOCK_NAMES, f"{symbol} 한글명 누락"

    def test_samsung_name(self):
        assert KR_STOCK_NAMES['005930'] == '삼성전자'

    def test_sk_hynix_name(self):
        assert KR_STOCK_NAMES['000660'] == 'SK하이닉스'
