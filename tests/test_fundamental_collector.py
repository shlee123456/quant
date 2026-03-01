"""FundamentalCollector 및 _build_fundamentals_data_block 테스트"""

import sys
import pytest
from unittest.mock import patch, MagicMock


# yfinance를 모킹하기 위해 sys.modules에 가짜 모듈 등록
_mock_yf_module = MagicMock()
sys.modules.setdefault('yfinance', _mock_yf_module)


class TestFundamentalCollector:
    """FundamentalCollector 클래스 테스트"""

    def _make_collector(self, api_delay: float = 0.0):
        from trading_bot.fundamental_collector import FundamentalCollector
        return FundamentalCollector(api_delay=api_delay)

    # ------------------------------------------------------------------
    # collect() 기본 동작
    # ------------------------------------------------------------------

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_returns_fundamentals(self, mock_sleep):
        """정상적인 심볼 리스트로 collect() 호출 시 데이터 반환"""
        collector = self._make_collector()

        mock_info = {
            'trailingPE': 25.3,
            'forwardPE': 22.1,
            'trailingEps': 6.57,
            'dividendYield': 0.005,
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'beta': 1.24,
            'fiftyTwoWeekHigh': 199.62,
            'fiftyTwoWeekLow': 124.17,
            'marketCap': 3000000000000,
        }

        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is not None
        assert 'collected_at' in result
        assert 'fundamentals' in result
        assert 'AAPL' in result['fundamentals']

        aapl = result['fundamentals']['AAPL']
        assert aapl['pe_ratio'] == 25.3
        assert aapl['forward_pe'] == 22.1
        assert aapl['eps'] == 6.57
        assert aapl['dividend_yield'] == 0.005
        assert aapl['sector'] == 'Technology'
        assert aapl['industry'] == 'Consumer Electronics'
        assert aapl['beta'] == 1.24
        assert aapl['fifty_two_week_high'] == 199.62
        assert aapl['fifty_two_week_low'] == 124.17
        assert aapl['market_cap'] == 3000000000000.0

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_multiple_symbols(self, mock_sleep):
        """여러 심볼 수집"""
        collector = self._make_collector()

        infos = {
            'AAPL': {'trailingPE': 25.0, 'sector': 'Technology'},
            'MSFT': {'trailingPE': 30.0, 'sector': 'Technology'},
        }

        def mock_ticker_factory(symbol):
            mock = MagicMock()
            mock.info = infos.get(symbol, {})
            return mock

        with patch("yfinance.Ticker", side_effect=mock_ticker_factory):
            result = collector.collect(['AAPL', 'MSFT'])

        assert result is not None
        assert len(result['fundamentals']) == 2
        assert result['fundamentals']['AAPL']['pe_ratio'] == 25.0
        assert result['fundamentals']['MSFT']['pe_ratio'] == 30.0

    # ------------------------------------------------------------------
    # 빈 입력 처리
    # ------------------------------------------------------------------

    def test_collect_empty_symbols(self):
        """빈 심볼 리스트 → None 반환"""
        collector = self._make_collector()
        result = collector.collect([])
        assert result is None

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_empty_info(self, mock_sleep):
        """Ticker.info가 빈 딕셔너리 → None 반환"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is None

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_none_info(self, mock_sleep):
        """Ticker.info가 None → None 반환"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = None

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is None

    # ------------------------------------------------------------------
    # 에러 처리
    # ------------------------------------------------------------------

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_per_symbol_exception(self, mock_sleep):
        """개별 심볼 예외 시 해당 심볼만 스킵"""
        collector = self._make_collector()

        def mock_ticker_factory(symbol):
            if symbol == 'BAD':
                raise Exception("Network error")
            mock = MagicMock()
            mock.info = {'trailingPE': 20.0, 'sector': 'Tech'}
            return mock

        with patch("yfinance.Ticker", side_effect=mock_ticker_factory):
            result = collector.collect(['AAPL', 'BAD', 'MSFT'])

        assert result is not None
        assert 'AAPL' in result['fundamentals']
        assert 'BAD' not in result['fundamentals']
        assert 'MSFT' in result['fundamentals']

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_all_symbols_fail(self, mock_sleep):
        """모든 심볼 실패 → None 반환"""
        collector = self._make_collector()

        def mock_ticker_factory(symbol):
            raise Exception("API down")

        with patch("yfinance.Ticker", side_effect=mock_ticker_factory):
            result = collector.collect(['AAPL', 'MSFT'])

        assert result is None

    # ------------------------------------------------------------------
    # 필드 매핑
    # ------------------------------------------------------------------

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_field_mapping_partial(self, mock_sleep):
        """일부 필드만 있는 경우"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {
            'trailingPE': 15.0,
            'sector': 'Healthcare',
        }

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['JNJ'])

        assert result is not None
        jnj = result['fundamentals']['JNJ']
        assert jnj['pe_ratio'] == 15.0
        assert jnj['sector'] == 'Healthcare'
        assert 'eps' not in jnj
        assert 'beta' not in jnj

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_field_mapping_none_values(self, mock_sleep):
        """필드 값이 None인 경우 스킵"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {
            'trailingPE': None,
            'forwardPE': 20.0,
            'sector': None,
            'beta': 1.1,
        }

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['XYZ'])

        assert result is not None
        xyz = result['fundamentals']['XYZ']
        assert 'pe_ratio' not in xyz
        assert xyz['forward_pe'] == 20.0
        assert 'sector' not in xyz
        assert xyz['beta'] == 1.1

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_numeric_type_conversion(self, mock_sleep):
        """정수 값이 float로 변환되는지 확인"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {
            'trailingPE': 25,
            'marketCap': 3000000000000,
        }

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is not None
        aapl = result['fundamentals']['AAPL']
        assert isinstance(aapl['pe_ratio'], float)
        assert isinstance(aapl['market_cap'], float)

    # ------------------------------------------------------------------
    # api_delay
    # ------------------------------------------------------------------

    def test_api_delay_default(self):
        """기본 api_delay 확인"""
        collector = self._make_collector()
        assert collector.api_delay == 0.0

    def test_api_delay_custom(self):
        """커스텀 api_delay 확인"""
        from trading_bot.fundamental_collector import FundamentalCollector
        collector = FundamentalCollector(api_delay=1.5)
        assert collector.api_delay == 1.5

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_api_delay_called(self, mock_sleep):
        """각 심볼 후 api_delay만큼 sleep 호출"""
        from trading_bot.fundamental_collector import FundamentalCollector
        collector = FundamentalCollector(api_delay=0.5)

        mock_ticker = MagicMock()
        mock_ticker.info = {'trailingPE': 20.0}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            collector.collect(['AAPL', 'MSFT'])

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.5)

    # ------------------------------------------------------------------
    # FIELDS 상수
    # ------------------------------------------------------------------

    def test_fields_dict_completeness(self):
        """FIELDS 딕셔너리에 10개 필드 매핑 존재"""
        from trading_bot.fundamental_collector import FundamentalCollector
        assert len(FundamentalCollector.FIELDS) == 10
        assert 'trailingPE' in FundamentalCollector.FIELDS
        assert 'marketCap' in FundamentalCollector.FIELDS

    # ------------------------------------------------------------------
    # collected_at 형식
    # ------------------------------------------------------------------

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collected_at_format(self, mock_sleep):
        """collected_at 필드가 올바른 형식인지"""
        import re
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {'trailingPE': 20.0}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is not None
        assert re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', result['collected_at'])

    # ------------------------------------------------------------------
    # 데이터가 없는 심볼 (info에 FIELDS 키 없음)
    # ------------------------------------------------------------------

    @patch("trading_bot.fundamental_collector.time.sleep")
    def test_collect_no_matching_fields(self, mock_sleep):
        """info에 FIELDS의 키가 하나도 없는 경우 해당 심볼 스킵"""
        collector = self._make_collector()

        mock_ticker = MagicMock()
        mock_ticker.info = {'shortName': 'Apple Inc', 'currency': 'USD'}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = collector.collect(['AAPL'])

        assert result is None


class TestBuildFundamentalsDataBlock:
    """_build_fundamentals_data_block 함수 테스트"""

    def _build(self, data):
        from trading_bot.market_analysis_prompt import _build_fundamentals_data_block
        return _build_fundamentals_data_block(data)

    def test_none_input(self):
        """None 입력 → 빈 문자열"""
        assert self._build(None) == ''

    def test_empty_dict(self):
        """빈 딕셔너리 → 빈 문자열"""
        assert self._build({}) == ''

    def test_empty_fundamentals(self):
        """fundamentals 키가 빈 딕셔너리 → 빈 문자열"""
        assert self._build({'fundamentals': {}}) == ''

    def test_full_data(self):
        """전체 데이터로 마크다운 테이블 생성"""
        data = {
            'fundamentals': {
                'AAPL': {
                    'pe_ratio': 25.3,
                    'forward_pe': 22.1,
                    'eps': 6.57,
                    'dividend_yield': 0.005,
                    'sector': 'Technology',
                    'beta': 1.24,
                    'fifty_two_week_high': 199.62,
                    'fifty_two_week_low': 124.17,
                },
            },
        }

        result = self._build(data)

        assert '## Company Fundamentals' in result
        assert '| Symbol | P/E |' in result
        assert '| AAPL |' in result
        assert '25.3' in result
        assert '22.1' in result
        assert '6.57' in result
        assert '0.50%' in result
        assert 'Technology' in result
        assert '1.24' in result
        assert '$200' in result
        assert '$124' in result

    def test_partial_data(self):
        """일부 필드만 있는 경우 - 로 표시"""
        data = {
            'fundamentals': {
                'TSLA': {
                    'pe_ratio': 80.5,
                    'sector': 'Consumer Cyclical',
                },
            },
        }

        result = self._build(data)

        assert '| TSLA |' in result
        assert '80.5' in result
        assert 'Consumer Cyclical' in result
        assert result.count('-') > 0

    def test_multiple_symbols(self):
        """여러 심볼 테이블 생성"""
        data = {
            'fundamentals': {
                'AAPL': {'pe_ratio': 25.0, 'sector': 'Tech'},
                'MSFT': {'pe_ratio': 30.0, 'sector': 'Tech'},
                'JNJ': {'pe_ratio': 15.0, 'sector': 'Healthcare'},
            },
        }

        result = self._build(data)

        assert '| AAPL |' in result
        assert '| MSFT |' in result
        assert '| JNJ |' in result

    def test_dividend_yield_zero(self):
        """배당 수익률 0인 경우"""
        data = {
            'fundamentals': {
                'TSLA': {'dividend_yield': 0},
            },
        }

        result = self._build(data)
        assert '0.00%' in result

    def test_no_dividend_yield(self):
        """배당 수익률 없는 경우 → -"""
        data = {
            'fundamentals': {
                'TSLA': {'pe_ratio': 80.0},
            },
        }

        result = self._build(data)
        assert '| TSLA |' in result
