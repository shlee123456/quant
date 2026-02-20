"""Tests for NewsCollector"""

import pytest
from unittest.mock import patch, MagicMock

from trading_bot.news_collector import NewsCollector


class FeedEntry:
    """feedparser entry를 모방하는 헬퍼 클래스

    feedparser의 entry는 dict처럼 [] 접근과 .get() 접근을 모두 지원하며,
    published, source 등 속성도 가진다. 이를 테스트에서 재현한다.
    """

    def __init__(self, title: str, link: str = 'https://example.com',
                 published: str = None, updated: str = None,
                 source_title: str = None):
        self._data = {'title': title, 'link': link}
        if published:
            self.published = published
        if updated:
            self.updated = updated
        if source_title:
            self.source = MagicMock()
            self.source.title = source_title

    def get(self, key, default=''):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data


def make_feed(entries=None, bozo=False):
    """Mock feedparser.parse() 결과 생성"""
    feed = MagicMock()
    feed.entries = entries or []
    feed.bozo = bozo
    return feed


class TestNewsCollector:
    """NewsCollector unit tests"""

    @pytest.fixture
    def collector(self):
        return NewsCollector(request_delay=0.0)

    # --- collect tests ---

    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_collect_returns_structure(self, mock_sleep, mock_parse, collector):
        """collect()가 올바른 키 구조를 반환하는지 확인"""
        mock_parse.return_value = make_feed(entries=[])

        result = collector.collect(['AAPL', 'MSFT'])

        assert 'collected_at' in result
        assert 'market_news' in result
        assert 'stock_news' in result
        assert isinstance(result['collected_at'], str)
        assert isinstance(result['market_news'], list)
        assert isinstance(result['stock_news'], dict)

    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_collect_continues_on_symbol_failure(self, mock_sleep, mock_parse, collector):
        """한 종목 실패 시 다른 종목은 정상 수집"""
        good_entry = FeedEntry(
            title='Good News - Reuters',
            link='https://example.com',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        good_feed = make_feed(entries=[good_entry])
        empty_feed = make_feed(entries=[])

        def side_effect(url):
            # Market news calls return empty
            if 'stock' not in url:
                return empty_feed
            # FAIL_SYM raises exception
            if 'FAIL_SYM' in url:
                raise Exception("Network error")
            return good_feed

        mock_parse.side_effect = side_effect

        result = collector.collect(['FAIL_SYM', 'GOOD_SYM'])

        # GOOD_SYM should be collected despite FAIL_SYM failure
        assert 'GOOD_SYM' in result['stock_news']
        assert 'FAIL_SYM' not in result['stock_news']

    # --- _fetch_stock_news tests ---

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_fetch_stock_news_parses_entries(self, mock_parse, collector):
        """종목 뉴스 파싱 정상 동작 확인"""
        entry = FeedEntry(
            title='Apple stock rises 5% - CNBC',
            link='https://example.com/apple',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._fetch_stock_news('AAPL', max_items=5)

        assert len(result) == 1
        assert result[0]['title'] == 'Apple stock rises 5%'
        assert result[0]['source'] == 'CNBC'
        assert result[0]['published'] == 'Thu, 20 Feb 2026 10:00:00 GMT'
        assert result[0]['link'] == 'https://example.com/apple'

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_max_items_limit(self, mock_parse, collector):
        """max_items가 올바르게 적용되는지 확인"""
        entries = [
            FeedEntry(title=f'News {i}', link=f'https://example.com/{i}',
                      published='Thu, 20 Feb 2026 10:00:00 GMT')
            for i in range(10)
        ]

        mock_parse.return_value = make_feed(entries=entries)

        result = collector._fetch_stock_news('AAPL', max_items=3)

        assert len(result) == 3

    # --- _fetch_market_news tests ---

    @patch('trading_bot.news_collector.feedparser.parse')
    @patch('trading_bot.news_collector.time.sleep')
    def test_fetch_market_news_deduplication(self, mock_sleep, mock_parse, collector):
        """시장 뉴스 중복 제거 확인"""
        dup_entry = FeedEntry(
            title='Fed raises rates',
            link='https://example.com/fed',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )
        unique_entry = FeedEntry(
            title='S&P 500 hits record',
            link='https://example.com/sp500',
            published='Thu, 20 Feb 2026 11:00:00 GMT',
        )

        call_count = [0]

        def side_effect(url):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_feed(entries=[dup_entry, unique_entry])
            # Second and third keywords return the same duplicate entry
            return make_feed(entries=[dup_entry])

        mock_parse.side_effect = side_effect

        result = collector._fetch_market_news(max_items=5)

        # Should have 2 unique items, not 4
        titles = [item['title'] for item in result]
        assert len(titles) == len(set(titles))
        assert len(result) == 2

    # --- _parse_rss tests ---

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_empty_feed_returns_empty_list(self, mock_parse, collector):
        """빈 피드 반환 시 빈 리스트"""
        mock_parse.return_value = make_feed(entries=[])

        result = collector._parse_rss('https://example.com/rss')

        assert result == []

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_bozo_feed_with_no_entries(self, mock_parse, collector):
        """bozo(에러) 피드에 엔트리 없으면 빈 리스트"""
        mock_parse.return_value = make_feed(entries=[], bozo=True)

        result = collector._parse_rss('https://example.com/rss')

        assert result == []

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_source_extraction_from_title(self, mock_parse, collector):
        """제목에서 ' - Source' 형태의 출처 추출"""
        entry = FeedEntry(
            title='Tesla stock surges - Bloomberg',
            link='https://example.com/tesla',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        assert result[0]['source'] == 'Bloomberg'
        assert result[0]['title'] == 'Tesla stock surges'

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_source_extraction_from_source_tag(self, mock_parse, collector):
        """entry.source.title 속성에서 출처 추출"""
        entry = FeedEntry(
            title='NVDA earnings beat expectations - Reuters',
            link='https://example.com/nvda',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
            source_title='Reuters',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        # source tag takes priority
        assert result[0]['source'] == 'Reuters'
        assert result[0]['title'] == 'NVDA earnings beat expectations'

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_title_cleanup_removes_source(self, mock_parse, collector):
        """제목에서 출처 접미사 제거 확인"""
        entry = FeedEntry(
            title='Market update for today - WSJ',
            link='https://example.com/market',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert result[0]['title'] == 'Market update for today'
        assert result[0]['source'] == 'WSJ'

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_title_without_source_stays_intact(self, mock_parse, collector):
        """출처가 없는 제목은 그대로 유지"""
        entry = FeedEntry(
            title='Simple headline no source',
            link='https://example.com/simple',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert result[0]['title'] == 'Simple headline no source'
        assert result[0]['source'] == ''

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_parse_rss_exception_returns_empty(self, mock_parse, collector):
        """feedparser.parse가 예외를 발생시키면 빈 리스트 반환"""
        mock_parse.side_effect = Exception("Network error")

        result = collector._parse_rss('https://example.com/rss')

        assert result == []

    @patch('trading_bot.news_collector.feedparser.parse')
    def test_entry_with_updated_instead_of_published(self, mock_parse, collector):
        """published 대신 updated 속성이 있는 엔트리"""
        entry = FeedEntry(
            title='Updated news',
            link='https://example.com/updated',
            updated='Fri, 21 Feb 2026 12:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        assert result[0]['published'] == 'Fri, 21 Feb 2026 12:00:00 GMT'
