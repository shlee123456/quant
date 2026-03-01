"""
MarketAnalyzer 매크로 분석 기능 테스트

analyze_macro(), _fetch_macro_data(), _analyze_macro_symbol(),
_calc_sector_rankings(), _detect_rotation(), _calc_breadth(),
_assess_risk_env(), _generate_macro_summary() 메서드를 검증합니다.
"""

from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_analyzer import MarketAnalyzer


# ─── 테스트 헬퍼 ───


def _make_ohlcv(n=100, base_price=100.0, trend=0.001):
    """n일치 OHLCV 테스트 데이터 생성 (yfinance 컬럼명: Open/High/Low/Close/Volume)"""
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    np.random.seed(42)
    prices = [base_price]
    for i in range(1, n):
        prices.append(prices[-1] * (1 + trend + np.random.normal(0, 0.01)))
    close = np.array(prices)
    return pd.DataFrame({
        'Open': close * 0.999,
        'High': close * 1.005,
        'Low': close * 0.995,
        'Close': close,
        'Volume': np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)


def _make_multi_download(symbols, n=100):
    """
    yf.download(group_by='ticker') 결과를 모킹하는 MultiIndex DataFrame.

    반환값은 columns가 (ticker, Price) 형태의 MultiIndex입니다.
    """
    np.random.seed(0)
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    arrays_sym = []
    arrays_col = []
    data_dict = {}

    for sym in symbols:
        base_price = np.random.uniform(50, 500)
        prices_list = [base_price]
        for i in range(1, n):
            prices_list.append(prices_list[-1] * (1 + 0.001 + np.random.normal(0, 0.01)))
        close = np.array(prices_list)

        for col_name, col_data in [
            ('Open', close * 0.999),
            ('High', close * 1.005),
            ('Low', close * 0.995),
            ('Close', close),
            ('Volume', np.random.randint(1_000_000, 5_000_000, n).astype(float)),
        ]:
            arrays_sym.append(sym)
            arrays_col.append(col_name)
            data_dict[(sym, col_name)] = col_data

    multi_index = pd.MultiIndex.from_arrays([arrays_sym, arrays_col])
    df = pd.DataFrame(data_dict, index=dates)
    df.columns = multi_index
    return df


# ─── Fixtures ───


@pytest.fixture
def analyzer():
    return MarketAnalyzer(ohlcv_limit=200, api_delay=0.0)


@pytest.fixture
def all_macro_symbols():
    """매크로 분석에 사용되는 모든 심볼 리스트"""
    return (
        MarketAnalyzer.MACRO_INDICES
        + list(MarketAnalyzer.MACRO_SECTORS.keys())
        + MarketAnalyzer.MACRO_RISK
    )


@pytest.fixture
def mock_macro_data(all_macro_symbols):
    """_fetch_macro_data()가 반환하는 형태의 Dict[str, DataFrame]"""
    np.random.seed(42)
    result = {}
    for sym in all_macro_symbols:
        result[sym] = _make_ohlcv(n=100, base_price=np.random.uniform(50, 500), trend=0.001)
    return result


# ─── 1. test_analyze_macro_without_yfinance ───


class TestAnalyzeMacroWithoutYfinance:

    def test_returns_none_when_yfinance_missing(self, analyzer):
        """yfinance가 없는 경우 analyze_macro()가 None을 반환"""
        with patch('trading_bot.market_analyzer._has_yfinance', False):
            result = analyzer.analyze_macro()
        assert result is None


# ─── 2. test_analyze_macro_success ───


class TestAnalyzeMacroSuccess:

    def test_returns_correct_structure(self, analyzer, all_macro_symbols):
        """정상적인 yf.download() 결과로 analyze_macro()가 올바른 구조를 반환"""
        multi_df = _make_multi_download(all_macro_symbols, n=100)

        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = multi_df
            result = analyzer.analyze_macro()

        assert result is not None
        assert 'indices' in result
        assert 'sectors' in result
        assert 'rotation' in result
        assert 'breadth' in result
        assert 'risk_environment' in result
        assert 'overall' in result

    def test_indices_contains_expected_keys(self, analyzer, all_macro_symbols):
        """indices에 SPY, QQQ, DIA, IWM 키가 포함"""
        multi_df = _make_multi_download(all_macro_symbols, n=100)

        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = multi_df
            result = analyzer.analyze_macro()

        for idx_sym in ['SPY', 'QQQ', 'DIA', 'IWM']:
            assert idx_sym in result['indices']


# ─── 3. test_fetch_macro_data ───


class TestFetchMacroData:

    def test_converts_multiindex_to_dict(self, analyzer, all_macro_symbols):
        """_fetch_macro_data()가 MultiIndex DataFrame을 Dict[str, DataFrame]으로 변환"""
        multi_df = _make_multi_download(all_macro_symbols, n=100)

        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = multi_df
            result = analyzer._fetch_macro_data()

        assert isinstance(result, dict)
        for sym in all_macro_symbols:
            assert sym in result
            assert isinstance(result[sym], pd.DataFrame)
            assert 'Close' in result[sym].columns

    def test_skips_symbols_with_insufficient_data(self, analyzer, all_macro_symbols):
        """데이터가 30봉 미만인 심볼은 건너뜀"""
        # 짧은 데이터로 MultiIndex 생성
        multi_df = _make_multi_download(all_macro_symbols, n=20)

        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = multi_df
            result = analyzer._fetch_macro_data()

        # 모든 심볼이 30봉 미만이므로 결과가 비어야 함
        assert result == {}


# ─── 4. test_analyze_macro_symbol ───


class TestAnalyzeMacroSymbol:

    def test_returns_required_keys(self, analyzer):
        """충분한 데이터에서 필수 키 존재 확인"""
        df = _make_ohlcv(n=100, base_price=150.0, trend=0.002)
        result = analyzer._analyze_macro_symbol(df)

        assert result is not None
        for key in ['last', 'chg_1d', 'chg_5d', 'chg_20d', 'rsi', 'vol_ratio']:
            assert key in result

    def test_change_calculations(self, analyzer):
        """수익률 계산이 올바른지 확인"""
        df = _make_ohlcv(n=100, base_price=100.0, trend=0.0)
        result = analyzer._analyze_macro_symbol(df)

        assert result is not None
        # last는 양수여야 함
        assert result['last'] > 0
        # 수익률은 None이 아닌 float
        assert isinstance(result['chg_1d'], (int, float))
        assert isinstance(result['chg_5d'], (int, float))
        assert isinstance(result['chg_20d'], (int, float))

    def test_rsi_in_valid_range(self, analyzer):
        """RSI가 0~100 범위 내"""
        df = _make_ohlcv(n=100, base_price=200.0, trend=0.005)
        result = analyzer._analyze_macro_symbol(df)

        assert result is not None
        assert 0 <= result['rsi'] <= 100

    def test_returns_none_for_short_data(self, analyzer):
        """데이터가 30봉 미만이면 None 반환"""
        df = _make_ohlcv(n=20, base_price=100.0)
        result = analyzer._analyze_macro_symbol(df)
        assert result is None


# ─── 5. test_calc_sector_rankings ───


class TestCalcSectorRankings:

    def test_rankings_are_1_to_n(self, analyzer, mock_macro_data):
        """rank_5d, rank_20d가 1~N 범위의 순위"""
        sectors = analyzer._calc_sector_rankings(mock_macro_data)

        assert len(sectors) > 0
        n = len(sectors)
        ranks_5d = sorted([s['rank_5d'] for s in sectors.values()])
        ranks_20d = sorted([s['rank_20d'] for s in sectors.values()])

        assert ranks_5d == list(range(1, n + 1))
        assert ranks_20d == list(range(1, n + 1))

    def test_name_field_is_korean(self, analyzer, mock_macro_data):
        """name 필드가 한글 섹터명"""
        sectors = analyzer._calc_sector_rankings(mock_macro_data)

        korean_names = set(MarketAnalyzer.MACRO_SECTORS.values())
        for sym, data in sectors.items():
            assert 'name' in data
            assert data['name'] in korean_names

    def test_returns_empty_when_no_data(self, analyzer):
        """섹터 데이터가 없으면 빈 딕셔너리 반환"""
        result = analyzer._calc_sector_rankings({})
        assert result == {}


# ─── 6. test_detect_rotation_risk_on ───


class TestDetectRotationRiskOn:

    def test_offensive_dominance_signals_risk_on(self, analyzer):
        """공격적 섹터 >> 방어적 섹터일 때 리스크온 판단"""
        sectors = {}
        # 공격적 섹터: 높은 5일 수익률
        for sym in MarketAnalyzer.OFFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 3.0, 'name': 'test'}
        # 방어적 섹터: 낮은 5일 수익률
        for sym in MarketAnalyzer.DEFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 0.5, 'name': 'test'}

        result = analyzer._detect_rotation(sectors)

        assert '리스크온' in result['signal']
        assert result['diff'] > 1.0


# ─── 7. test_detect_rotation_risk_off ───


class TestDetectRotationRiskOff:

    def test_defensive_dominance_signals_risk_off(self, analyzer):
        """방어적 섹터 >> 공격적 섹터일 때 리스크오프 판단"""
        sectors = {}
        for sym in MarketAnalyzer.OFFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 0.5, 'name': 'test'}
        for sym in MarketAnalyzer.DEFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 3.0, 'name': 'test'}

        result = analyzer._detect_rotation(sectors)

        assert '리스크오프' in result['signal']
        assert result['diff'] < -1.0


# ─── 8. test_detect_rotation_neutral ───


class TestDetectRotationNeutral:

    def test_similar_returns_signals_neutral(self, analyzer):
        """차이가 -1.0~1.0 사이일 때 중립 판단"""
        sectors = {}
        for sym in MarketAnalyzer.OFFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 1.5, 'name': 'test'}
        for sym in MarketAnalyzer.DEFENSIVE_SECTORS:
            sectors[sym] = {'chg_5d': 1.0, 'name': 'test'}

        result = analyzer._detect_rotation(sectors)

        assert '중립' in result['signal']
        assert -1.0 <= result['diff'] <= 1.0


# ─── 9. test_assess_risk_env_risk_off ───


class TestAssessRiskEnvRiskOff:

    def test_tlt_up_gld_up_hyg_down_is_risk_off(self, analyzer):
        """TLT up + GLD up + HYG down => 리스크오프"""
        # TLT: 상승 (5일 전 대비 +2%)
        tlt_df = _make_ohlcv(n=100, base_price=100.0, trend=0.004)
        # GLD: 상승
        gld_df = _make_ohlcv(n=100, base_price=180.0, trend=0.004)
        # HYG: 하락
        hyg_df = _make_ohlcv(n=100, base_price=80.0, trend=-0.004)

        macro_data = {'TLT': tlt_df, 'GLD': gld_df, 'HYG': hyg_df}
        result = analyzer._assess_risk_env(macro_data)

        assert '리스크오프' in result['assessment']


# ─── 10. test_assess_risk_env_risk_on ───


class TestAssessRiskEnvRiskOn:

    def test_tlt_down_gld_down_hyg_up_is_risk_on(self, analyzer):
        """TLT down + GLD down + HYG up => 리스크온"""
        tlt_df = _make_ohlcv(n=100, base_price=100.0, trend=-0.004)
        gld_df = _make_ohlcv(n=100, base_price=180.0, trend=-0.004)
        hyg_df = _make_ohlcv(n=100, base_price=80.0, trend=0.004)

        macro_data = {'TLT': tlt_df, 'GLD': gld_df, 'HYG': hyg_df}
        result = analyzer._assess_risk_env(macro_data)

        assert '리스크온' in result['assessment']


# ─── 11. test_assess_risk_env_mixed ───


class TestAssessRiskEnvMixed:

    def test_mixed_signals_is_mixed(self, analyzer):
        """혼합 시그널일 때 혼조 판단"""
        # TLT up, GLD down, HYG up => 혼조
        tlt_df = _make_ohlcv(n=100, base_price=100.0, trend=0.004)
        gld_df = _make_ohlcv(n=100, base_price=180.0, trend=-0.004)
        hyg_df = _make_ohlcv(n=100, base_price=80.0, trend=0.004)

        macro_data = {'TLT': tlt_df, 'GLD': gld_df, 'HYG': hyg_df}
        result = analyzer._assess_risk_env(macro_data)

        assert '혼조' in result['assessment']


# ─── 12. test_calc_breadth ───


class TestCalcBreadth:

    def test_spy_vs_iwm_divergence(self, analyzer):
        """SPY vs IWM 괴리 계산 확인"""
        indices = {
            'SPY': {'chg_5d': 2.0},
            'IWM': {'chg_5d': 0.5},
            'QQQ': {'chg_5d': 1.5},
        }
        sectors = {}

        result = analyzer._calc_breadth(indices, sectors)

        assert result['spy_vs_iwm_5d'] == round(2.0 - 0.5, 1)
        assert result['spy_vs_qqq_5d'] == round(2.0 - 1.5, 1)

    def test_sectors_positive_negative_count(self, analyzer):
        """sectors_positive/negative 카운트 확인"""
        indices = {'SPY': {'chg_5d': 1.0}, 'IWM': {'chg_5d': 0.5}}
        sectors = {
            'XLK': {'chg_5d': 2.0},
            'XLF': {'chg_5d': 1.5},
            'XLE': {'chg_5d': -0.5},
            'XLV': {'chg_5d': -1.0},
            'XLI': {'chg_5d': 0.0},  # 0은 negative로 카운트 (<=0)
        }

        result = analyzer._calc_breadth(indices, sectors)

        assert result['sectors_positive_5d'] == 2  # XLK, XLF
        assert result['sectors_negative_5d'] == 3  # XLE, XLV, XLI

    def test_interpretation_is_string(self, analyzer):
        """interpretation이 비어있지 않은 문자열"""
        indices = {'SPY': {'chg_5d': 1.0}, 'IWM': {'chg_5d': 1.0}}
        sectors = {}
        result = analyzer._calc_breadth(indices, sectors)

        assert isinstance(result['interpretation'], str)
        assert len(result['interpretation']) > 0


# ─── 13. test_generate_macro_summary ───


class TestGenerateMacroSummary:

    def test_best_worst_sectors_in_summary(self, analyzer):
        """최강/최약 섹터가 요약에 포함"""
        indices = {'SPY': {'chg_5d': 1.0}}
        sectors = {
            'XLK': {'chg_5d': 5.0, 'name': '기술'},
            'XLF': {'chg_5d': 2.0, 'name': '금융'},
            'XLU': {'chg_5d': -3.0, 'name': '유틸리티'},
        }
        rotation = {'signal': '뚜렷한 로테이션 없음 (중립)'}
        breadth = {'spy_vs_iwm_5d': 0.5}
        risk_env = {'assessment': '혼조 (방향성 불확실)'}

        result = analyzer._generate_macro_summary(indices, sectors, rotation, breadth, risk_env)

        assert isinstance(result, str)
        assert len(result) > 0
        # 최강 섹터(기술) 또는 최약 섹터(유틸리티)가 포함되어야 함
        assert '기술' in result or '유틸리티' in result

    def test_summary_not_empty_with_data(self, analyzer):
        """데이터가 있으면 요약이 비어있지 않음"""
        indices = {}
        sectors = {
            'XLK': {'chg_5d': 1.0, 'name': '기술'},
        }
        rotation = {'signal': '중립'}
        breadth = {}
        risk_env = {'assessment': '혼조'}

        result = analyzer._generate_macro_summary(indices, sectors, rotation, breadth, risk_env)

        assert len(result) > 0
        assert result.endswith('.')

    def test_summary_with_empty_sectors(self, analyzer):
        """섹터가 비어있을 때도 에러 없이 반환"""
        result = analyzer._generate_macro_summary({}, {}, {'signal': ''}, {}, {'assessment': ''})

        assert isinstance(result, str)
        assert len(result) > 0


# ─── 14. test_analyze_macro_fetch_failure ───


class TestAnalyzeMacroFetchFailure:

    def test_returns_none_on_empty_download(self, analyzer):
        """yf.download()가 빈 DataFrame 반환 시 None"""
        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = pd.DataFrame()
            result = analyzer.analyze_macro()

        assert result is None

    def test_returns_none_on_download_exception(self, analyzer):
        """yf.download()가 예외를 던질 때 None"""
        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.side_effect = Exception("Network error")
            result = analyzer.analyze_macro()

        assert result is None

    def test_returns_none_on_none_download(self, analyzer):
        """yf.download()가 None 반환 시 None"""
        with patch('trading_bot.market_analyzer._has_yfinance', True), \
             patch('trading_bot.market_analyzer.yf') as mock_yf:
            mock_yf.download.return_value = None
            result = analyzer.analyze_macro()

        assert result is None
