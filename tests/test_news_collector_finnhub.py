"""Tests for NewsCollector Finnhub integration"""

import pytest
from unittest.mock import patch, MagicMock

from trading_bot.news_collector import NewsCollector


class TestDeduplicateNews:
    """_deduplicate_news() 단위 테스트"""

    def test_removes_duplicate_titles(self):
        """중복 제목 제거"""
        collector = NewsCollector(request_delay=0.0)
        news = [
            {'title': 'Apple earnings', 'source': 'Reuters'},
            {'title': 'Apple earnings', 'source': 'Bloomberg'},
            {'title': 'Tesla rises', 'source': 'CNBC'},
        ]
        result = collector._deduplicate_news(news)
        assert len(result) == 2
        assert result[0]['title'] == 'Apple earnings'
        assert result[0]['source'] == 'Reuters'  # 첫 번째 유지
        assert result[1]['title'] == 'Tesla rises'

    def test_empty_list(self):
        """빈 리스트 처리"""
        collector = NewsCollector(request_delay=0.0)
        result = collector._deduplicate_news([])
        assert result == []

    def test_skips_empty_titles(self):
        """빈 제목은 건너뛰기"""
        collector = NewsCollector(request_delay=0.0)
        news = [
            {'title': '', 'source': 'Reuters'},
            {'title': 'Valid title', 'source': 'CNBC'},
            {'title': '', 'source': 'Bloomberg'},
        ]
        result = collector._deduplicate_news(news)
        assert len(result) == 1
        assert result[0]['title'] == 'Valid title'

    def test_no_duplicates(self):
        """중복 없을 때 그대로 반환"""
        collector = NewsCollector(request_delay=0.0)
        news = [
            {'title': 'News A', 'source': 'Reuters'},
            {'title': 'News B', 'source': 'Bloomberg'},
        ]
        result = collector._deduplicate_news(news)
        assert len(result) == 2


class TestFetchFinnhubNews:
    """_fetch_finnhub_news() 단위 테스트"""

    @patch('trading_bot.news_collector.requests.get')
    def test_successful_fetch(self, mock_get):
        """Finnhub 뉴스 정상 조회"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'headline': 'Apple reports record quarter',
                'source': 'Reuters',
                'datetime': 1709251200,
                'url': 'http://example.com/apple',
            },
            {
                'headline': 'Apple stock analysis',
                'source': 'Bloomberg',
                'datetime': 1709164800,
                'url': 'http://example.com/apple2',
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert len(news) == 2
        assert news[0]['title'] == 'Apple reports record quarter'
        assert news[0]['source'] == 'Reuters'
        assert news[0]['link'] == 'http://example.com/apple'
        assert news[0]['published'] != ''

    @patch('trading_bot.news_collector.requests.get')
    def test_max_items_limit(self, mock_get):
        """max_items 제한"""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'headline': f'News {i}', 'source': 'Test', 'datetime': 1709251200, 'url': f'http://example.com/{i}'}
            for i in range(10)
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL', max_items=3)

        assert len(news) == 3

    @patch('trading_bot.news_collector.requests.get')
    def test_empty_response(self, mock_get):
        """빈 응답 처리"""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert news == []

    @patch('trading_bot.news_collector.requests.get')
    def test_non_list_response(self, mock_get):
        """리스트가 아닌 응답 처리"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'error': 'invalid token'}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert news == []

    @patch('trading_bot.news_collector.requests.get')
    def test_timeout_error(self, mock_get):
        """타임아웃 에러 처리"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert news == []

    @patch('trading_bot.news_collector.requests.get')
    def test_http_error(self, mock_get):
        """HTTP 에러 처리 (401, 500 등)"""
        import requests
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert news == []

    @patch('trading_bot.news_collector.requests.get')
    def test_missing_datetime_field(self, mock_get):
        """datetime 필드 없는 기사 처리"""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                'headline': 'No datetime article',
                'source': 'Reuters',
                'url': 'http://example.com/no-dt',
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        news = collector._fetch_finnhub_news('AAPL')

        assert len(news) == 1
        assert news[0]['published'] == ''

    @patch('trading_bot.news_collector.requests.get')
    def test_request_params(self, mock_get):
        """요청 파라미터 확인"""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='my_api_key')
        collector._fetch_finnhub_news('MSFT', days_back=5)

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        params = call_kwargs[1]['params'] if 'params' in call_kwargs[1] else call_kwargs.kwargs['params']
        assert params['symbol'] == 'MSFT'
        assert params['token'] == 'my_api_key'
        assert 'from' in params
        assert 'to' in params


class TestEnrichWithFinnhub:
    """_enrich_with_finnhub() 단위 테스트"""

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_enriches_existing_news(self, mock_fetch, mock_sleep):
        """기존 뉴스에 Finnhub 뉴스 병합"""
        mock_fetch.return_value = [
            {'title': 'Finnhub exclusive', 'source': 'Finnhub', 'published': '', 'link': ''},
        ]

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {
            'AAPL': [
                {'title': 'Existing news', 'source': 'Google', 'published': '', 'link': ''},
            ],
        }

        collector._enrich_with_finnhub(['AAPL'], stock_news, max_per_symbol=5)

        assert len(stock_news['AAPL']) == 2
        titles = [n['title'] for n in stock_news['AAPL']]
        assert 'Existing news' in titles
        assert 'Finnhub exclusive' in titles

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_adds_news_for_symbol_without_existing(self, mock_fetch, mock_sleep):
        """기존 뉴스 없는 종목에 Finnhub 뉴스 추가"""
        mock_fetch.return_value = [
            {'title': 'New Finnhub news', 'source': 'Finnhub', 'published': '', 'link': ''},
        ]

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {}

        collector._enrich_with_finnhub(['TSLA'], stock_news, max_per_symbol=5)

        assert 'TSLA' in stock_news
        assert len(stock_news['TSLA']) == 1

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_deduplicates_merged_news(self, mock_fetch, mock_sleep):
        """병합 시 중복 제거"""
        mock_fetch.return_value = [
            {'title': 'Same headline', 'source': 'Finnhub', 'published': '', 'link': ''},
        ]

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {
            'AAPL': [
                {'title': 'Same headline', 'source': 'Google', 'published': '', 'link': ''},
                {'title': 'Unique news', 'source': 'Google', 'published': '', 'link': ''},
            ],
        }

        collector._enrich_with_finnhub(['AAPL'], stock_news, max_per_symbol=5)

        assert len(stock_news['AAPL']) == 2
        titles = [n['title'] for n in stock_news['AAPL']]
        assert titles.count('Same headline') == 1

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_respects_max_per_symbol(self, mock_fetch, mock_sleep):
        """max_per_symbol 제한 적용"""
        mock_fetch.return_value = [
            {'title': f'Finnhub {i}', 'source': 'Finnhub', 'published': '', 'link': ''}
            for i in range(5)
        ]

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {
            'AAPL': [
                {'title': f'Existing {i}', 'source': 'Google', 'published': '', 'link': ''}
                for i in range(3)
            ],
        }

        collector._enrich_with_finnhub(['AAPL'], stock_news, max_per_symbol=5)

        assert len(stock_news['AAPL']) == 5

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_handles_fetch_error(self, mock_fetch, mock_sleep):
        """Finnhub 조회 실패 시 기존 뉴스 유지"""
        mock_fetch.side_effect = Exception("API error")

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {
            'AAPL': [
                {'title': 'Existing', 'source': 'Google', 'published': '', 'link': ''},
            ],
        }

        collector._enrich_with_finnhub(['AAPL'], stock_news, max_per_symbol=5)

        # 기존 뉴스 유지
        assert len(stock_news['AAPL']) == 1

    @patch('trading_bot.news_collector.time.sleep')
    @patch.object(NewsCollector, '_fetch_finnhub_news')
    def test_empty_finnhub_response_no_change(self, mock_fetch, mock_sleep):
        """Finnhub 빈 응답 시 변경 없음"""
        mock_fetch.return_value = []

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        stock_news = {
            'AAPL': [
                {'title': 'Existing', 'source': 'Google', 'published': '', 'link': ''},
            ],
        }

        collector._enrich_with_finnhub(['AAPL'], stock_news, max_per_symbol=5)

        assert len(stock_news['AAPL']) == 1


class TestCollectWithFinnhub:
    """collect() Finnhub 통합 테스트"""

    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_collect_without_finnhub_key(self, mock_sleep, mock_parse):
        """API 키 없으면 Finnhub 건너뛰기"""
        mock_parse.return_value = MagicMock(entries=[], bozo=False)

        collector = NewsCollector(request_delay=0.0, finnhub_api_key=None)
        # 환경변수도 없도록 보장
        with patch.dict('os.environ', {}, clear=True):
            collector.finnhub_api_key = None
            result = collector.collect(['AAPL'])

        assert 'stock_news' in result
        # Finnhub 호출이 없어야 함 (feedparser만 호출됨)

    @patch.object(NewsCollector, '_enrich_with_finnhub')
    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_collect_calls_finnhub_enrichment(self, mock_sleep, mock_parse, mock_enrich):
        """API 키 있으면 Finnhub 보강 호출"""
        mock_parse.return_value = MagicMock(entries=[], bozo=False)

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        collector.collect(['AAPL', 'MSFT'])

        mock_enrich.assert_called_once()
        call_args = mock_enrich.call_args
        assert call_args[0][0] == ['AAPL', 'MSFT']  # symbols

    @patch('trading_bot.news_collector.requests.get')
    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_collect_end_to_end_with_finnhub(self, mock_sleep, mock_parse, mock_get):
        """Finnhub 포함 전체 흐름 테스트"""
        # feedparser mock (빈 결과)
        mock_parse.return_value = MagicMock(entries=[], bozo=False)

        # Finnhub mock
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                'headline': 'Finnhub AAPL news',
                'source': 'Reuters',
                'datetime': 1709251200,
                'url': 'http://example.com/finnhub',
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        collector = NewsCollector(request_delay=0.0, finnhub_api_key='test_key')
        result = collector.collect(['AAPL'])

        assert 'AAPL' in result['stock_news']
        assert len(result['stock_news']['AAPL']) == 1
        assert result['stock_news']['AAPL'][0]['title'] == 'Finnhub AAPL news'


class TestInitFinnhubKey:
    """__init__ finnhub_api_key 설정 테스트"""

    def test_explicit_key(self):
        """명시적 키 설정"""
        collector = NewsCollector(finnhub_api_key='explicit_key')
        assert collector.finnhub_api_key == 'explicit_key'

    @patch.dict('os.environ', {'FINNHUB_API_KEY': 'env_key'})
    def test_env_key(self):
        """환경변수에서 키 로드"""
        collector = NewsCollector()
        assert collector.finnhub_api_key == 'env_key'

    @patch.dict('os.environ', {}, clear=True)
    def test_no_key(self):
        """키 없음"""
        collector = NewsCollector()
        assert collector.finnhub_api_key is None

    @patch.dict('os.environ', {'FINNHUB_API_KEY': 'env_key'})
    def test_explicit_overrides_env(self):
        """명시적 키가 환경변수보다 우선"""
        collector = NewsCollector(finnhub_api_key='explicit_key')
        assert collector.finnhub_api_key == 'explicit_key'
