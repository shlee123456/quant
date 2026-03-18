"""Tests for KRNewsCollector"""

import pytest
from unittest.mock import patch, MagicMock

from trading_bot.kr_news_collector import (
    KRNewsCollector,
    KR_STOCK_NAMES,
    KR_MARKET_KEYWORDS,
)


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


class TestKRNewsCollectorInit:
    """KRNewsCollector 초기화 테스트"""

    def test_init_default_delay(self):
        """기본 request_delay 설정"""
        collector = KRNewsCollector()
        assert collector.request_delay == 0.3

    def test_init_custom_delay(self):
        """커스텀 request_delay 설정"""
        collector = KRNewsCollector(request_delay=1.0)
        assert collector.request_delay == 1.0


class TestKRStockNames:
    """KR_STOCK_NAMES 매핑 테스트"""

    def test_samsung_electronics(self):
        """삼성전자 매핑 확인"""
        assert KR_STOCK_NAMES['005930'] == '삼성전자'

    def test_sk_hynix(self):
        """SK하이닉스 매핑 확인"""
        assert KR_STOCK_NAMES['000660'] == 'SK하이닉스'

    def test_naver(self):
        """NAVER 매핑 확인"""
        assert KR_STOCK_NAMES['035420'] == 'NAVER'

    def test_kakao(self):
        """카카오 매핑 확인"""
        assert KR_STOCK_NAMES['035720'] == '카카오'

    def test_stock_count(self):
        """16개 종목 매핑"""
        assert len(KR_STOCK_NAMES) == 16


class TestKRMarketKeywords:
    """KR_MARKET_KEYWORDS 테스트"""

    def test_keywords_count(self):
        """5개 시장 키워드"""
        assert len(KR_MARKET_KEYWORDS) == 5

    def test_contains_kospi(self):
        """코스피 키워드 포함"""
        assert '코스피' in KR_MARKET_KEYWORDS

    def test_contains_bok_rate(self):
        """한국은행 기준금리 키워드 포함"""
        assert '한국은행 기준금리' in KR_MARKET_KEYWORDS


class TestCollect:
    """collect() 메서드 테스트"""

    @pytest.fixture
    def collector(self):
        return KRNewsCollector(request_delay=0.0)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    @patch('trading_bot.kr_news_collector.time.sleep')
    def test_collect_returns_structure(self, mock_sleep, mock_parse, collector):
        """collect()가 올바른 키 구조를 반환하는지 확인"""
        mock_parse.return_value = make_feed(entries=[])

        result = collector.collect(['005930', '035420'])

        assert 'collected_at' in result
        assert 'market_news' in result
        assert 'stock_news' in result
        assert isinstance(result['collected_at'], str)
        assert isinstance(result['market_news'], list)
        assert isinstance(result['stock_news'], dict)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    @patch('trading_bot.kr_news_collector.time.sleep')
    def test_collect_none_symbols(self, mock_sleep, mock_parse, collector):
        """symbols=None이면 시장 전체 뉴스만 수집"""
        mock_parse.return_value = make_feed(entries=[])

        result = collector.collect(symbols=None)

        assert result['stock_news'] == {}
        assert isinstance(result['market_news'], list)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    @patch('trading_bot.kr_news_collector.time.sleep')
    def test_collect_continues_on_symbol_failure(self, mock_sleep, mock_parse, collector):
        """한 종목 실패 시 다른 종목은 정상 수집"""
        good_entry = FeedEntry(
            title='삼성전자 실적 호조 - 한경',
            link='https://example.com',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        good_feed = make_feed(entries=[good_entry])
        empty_feed = make_feed(entries=[])

        def side_effect(url):
            if '주식' not in url:
                return empty_feed
            if 'SK하이닉스' in url:
                raise Exception("Network error")
            return good_feed

        mock_parse.side_effect = side_effect

        result = collector.collect(['000660', '005930'])

        # 005930(삼성전자) 뉴스는 수집되어야 함
        assert '005930' in result['stock_news']
        assert '000660' not in result['stock_news']


class TestFetchStockNews:
    """_fetch_stock_news 테스트"""

    @pytest.fixture
    def collector(self):
        return KRNewsCollector(request_delay=0.0)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_fetch_stock_news_uses_korean_name(self, mock_parse, collector):
        """종목 코드에 해당하는 한글명으로 RSS 검색"""
        mock_parse.return_value = make_feed(entries=[])

        collector._fetch_stock_news('005930', max_items=5)

        call_url = mock_parse.call_args[0][0]
        assert '삼성전자' in call_url
        assert 'hl=ko' in call_url
        assert 'gl=KR' in call_url
        assert 'ceid=KR:ko' in call_url

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_fetch_stock_news_unknown_code_uses_code(self, mock_parse, collector):
        """매핑에 없는 종목 코드는 코드 자체로 검색"""
        mock_parse.return_value = make_feed(entries=[])

        collector._fetch_stock_news('999999', max_items=5)

        call_url = mock_parse.call_args[0][0]
        assert '999999' in call_url

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_fetch_stock_news_parses_entries(self, mock_parse, collector):
        """종목 뉴스 파싱 정상 동작 확인"""
        entry = FeedEntry(
            title='삼성전자 5% 상승 - 한국경제',
            link='https://example.com/samsung',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )

        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._fetch_stock_news('005930', max_items=5)

        assert len(result) == 1
        assert result[0]['title'] == '삼성전자 5% 상승'
        assert result[0]['source'] == '한국경제'
        assert result[0]['published'] == 'Thu, 20 Feb 2026 10:00:00 GMT'

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_max_items_limit(self, mock_parse, collector):
        """max_items가 올바르게 적용되는지 확인"""
        entries = [
            FeedEntry(title=f'뉴스 {i}', link=f'https://example.com/{i}',
                      published='Thu, 20 Feb 2026 10:00:00 GMT')
            for i in range(10)
        ]

        mock_parse.return_value = make_feed(entries=entries)

        result = collector._fetch_stock_news('005930', max_items=3)

        assert len(result) == 3


class TestFetchMarketNews:
    """_fetch_market_news 테스트"""

    @pytest.fixture
    def collector(self):
        return KRNewsCollector(request_delay=0.0)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    @patch('trading_bot.kr_news_collector.time.sleep')
    def test_fetch_market_news_deduplication(self, mock_sleep, mock_parse, collector):
        """시장 뉴스 중복 제거 확인"""
        dup_entry = FeedEntry(
            title='한국은행 기준금리 동결',
            link='https://example.com/bok',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )
        unique_entry = FeedEntry(
            title='코스피 3000 돌파',
            link='https://example.com/kospi',
            published='Thu, 20 Feb 2026 11:00:00 GMT',
        )

        call_count = [0]

        def side_effect(url):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_feed(entries=[dup_entry, unique_entry])
            return make_feed(entries=[dup_entry])

        mock_parse.side_effect = side_effect

        result = collector._fetch_market_news(max_items=5)

        titles = [item['title'] for item in result]
        assert len(titles) == len(set(titles))
        assert len(result) == 2

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    @patch('trading_bot.kr_news_collector.time.sleep')
    def test_fetch_market_news_uses_korean_locale(self, mock_sleep, mock_parse, collector):
        """시장 뉴스 RSS URL이 한국어 로케일 사용"""
        mock_parse.return_value = make_feed(entries=[])

        collector._fetch_market_news(max_items=5)

        for call in mock_parse.call_args_list:
            url = call[0][0]
            assert 'hl=ko' in url
            assert 'gl=KR' in url


class TestParseRss:
    """_parse_rss 테스트"""

    @pytest.fixture
    def collector(self):
        return KRNewsCollector(request_delay=0.0)

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_empty_feed_returns_empty_list(self, mock_parse, collector):
        """빈 피드 반환 시 빈 리스트"""
        mock_parse.return_value = make_feed(entries=[])
        result = collector._parse_rss('https://example.com/rss')
        assert result == []

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_bozo_feed_with_no_entries(self, mock_parse, collector):
        """bozo(에러) 피드에 엔트리 없으면 빈 리스트"""
        mock_parse.return_value = make_feed(entries=[], bozo=True)
        result = collector._parse_rss('https://example.com/rss')
        assert result == []

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_source_extraction_from_title(self, mock_parse, collector):
        """제목에서 ' - Source' 형태의 출처 추출"""
        entry = FeedEntry(
            title='삼성전자 호실적 - 매일경제',
            link='https://example.com/samsung',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )
        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        assert result[0]['source'] == '매일경제'
        assert result[0]['title'] == '삼성전자 호실적'

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_source_extraction_from_source_tag(self, mock_parse, collector):
        """entry.source.title 속성에서 출처 추출"""
        entry = FeedEntry(
            title='코스피 상승 - 한국경제',
            link='https://example.com/kospi',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
            source_title='한국경제',
        )
        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        assert result[0]['source'] == '한국경제'
        assert result[0]['title'] == '코스피 상승'

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_title_without_source_stays_intact(self, mock_parse, collector):
        """출처가 없는 제목은 그대로 유지"""
        entry = FeedEntry(
            title='단순 헤드라인 출처 없음',
            link='https://example.com/simple',
            published='Thu, 20 Feb 2026 10:00:00 GMT',
        )
        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert result[0]['title'] == '단순 헤드라인 출처 없음'
        assert result[0]['source'] == ''

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_parse_rss_exception_returns_empty(self, mock_parse, collector):
        """feedparser.parse가 예외를 발생시키면 빈 리스트 반환"""
        mock_parse.side_effect = Exception("Network error")
        result = collector._parse_rss('https://example.com/rss')
        assert result == []

    @patch('trading_bot.kr_news_collector.feedparser.parse')
    def test_entry_with_updated_instead_of_published(self, mock_parse, collector):
        """published 대신 updated 속성이 있는 엔트리"""
        entry = FeedEntry(
            title='업데이트된 뉴스',
            link='https://example.com/updated',
            updated='Fri, 21 Feb 2026 12:00:00 GMT',
        )
        mock_parse.return_value = make_feed(entries=[entry])

        result = collector._parse_rss('https://example.com/rss')

        assert len(result) == 1
        assert result[0]['published'] == 'Fri, 21 Feb 2026 12:00:00 GMT'


class TestDeduplicateNews:
    """_deduplicate_news 테스트"""

    @pytest.fixture
    def collector(self):
        return KRNewsCollector(request_delay=0.0)

    def test_dedup_removes_duplicates(self, collector):
        """중복 제목 제거"""
        news = [
            {'title': '동일 뉴스', 'link': 'a'},
            {'title': '동일 뉴스', 'link': 'b'},
            {'title': '다른 뉴스', 'link': 'c'},
        ]
        result = collector._deduplicate_news(news)
        assert len(result) == 2

    def test_dedup_preserves_first(self, collector):
        """첫 번째 항목 유지"""
        news = [
            {'title': '동일 뉴스', 'link': 'first'},
            {'title': '동일 뉴스', 'link': 'second'},
        ]
        result = collector._deduplicate_news(news)
        assert result[0]['link'] == 'first'

    def test_dedup_skips_empty_title(self, collector):
        """빈 제목은 무시"""
        news = [
            {'title': '', 'link': 'a'},
            {'title': '유효 뉴스', 'link': 'b'},
        ]
        result = collector._deduplicate_news(news)
        assert len(result) == 1
        assert result[0]['title'] == '유효 뉴스'
