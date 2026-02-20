"""
News Collector - Google News RSS 뉴스 수집기

종목별 + 시장 전체 뉴스를 Google News RSS로 수집합니다.
feedparser 라이브러리를 사용하여 RSS 피드를 파싱합니다.

Usage:
    from trading_bot.news_collector import NewsCollector

    collector = NewsCollector()
    news = collector.collect(['AAPL', 'MSFT', 'NVDA'])
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import feedparser

logger = logging.getLogger(__name__)


class NewsCollector:
    """Google News RSS를 통해 종목별/시장 뉴스를 수집하는 클래스"""

    # 시장 전체 뉴스 검색 키워드
    MARKET_KEYWORDS = [
        "US stock market today",
        "S&P 500",
        "Federal Reserve interest rate",
    ]

    def __init__(self, request_delay: float = 0.3):
        """
        Args:
            request_delay: RSS 요청 간 대기 시간(초), rate limit 방지
        """
        self.request_delay = request_delay

    def collect(self, symbols: List[str], max_per_symbol: int = 5) -> Dict:
        """
        종목별 + 시장 전체 뉴스 수집

        Args:
            symbols: 종목 코드 리스트 (예: ['AAPL', 'MSFT'])
            max_per_symbol: 종목당 최대 뉴스 수

        Returns:
            뉴스 데이터 딕셔너리
        """
        collected_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # 시장 전체 뉴스
        market_news = self._fetch_market_news(max_items=5)

        # 종목별 뉴스
        stock_news = {}
        for symbol in symbols:
            try:
                news = self._fetch_stock_news(symbol, max_items=max_per_symbol)
                if news:
                    stock_news[symbol] = news
                time.sleep(self.request_delay)
            except Exception as e:
                logger.warning(f"{symbol} 뉴스 수집 실패: {e}")
                continue

        logger.info(f"뉴스 수집 완료: 시장 {len(market_news)}건, 종목 {sum(len(v) for v in stock_news.values())}건")

        return {
            'collected_at': collected_at,
            'market_news': market_news,
            'stock_news': stock_news,
        }

    def _fetch_stock_news(self, symbol: str, max_items: int = 5) -> List[Dict]:
        """종목별 Google News RSS에서 뉴스 수집"""
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        return self._parse_rss(url, max_items)

    def _fetch_market_news(self, max_items: int = 5) -> List[Dict]:
        """시장 전체 뉴스 수집"""
        all_news = []
        for keyword in self.MARKET_KEYWORDS:
            try:
                query = keyword.replace(' ', '+')
                url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
                news = self._parse_rss(url, max_items=2)
                all_news.extend(news)
                time.sleep(self.request_delay)
            except Exception as e:
                logger.warning(f"시장 뉴스 수집 실패 ({keyword}): {e}")
                continue

        # 중복 제거 (제목 기준) + max_items 제한
        seen_titles = set()
        unique_news = []
        for item in all_news:
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                unique_news.append(item)

        return unique_news[:max_items]

    def _parse_rss(self, url: str, max_items: int = 5) -> List[Dict]:
        """RSS 피드를 파싱하여 뉴스 리스트 반환"""
        try:
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(f"RSS 파싱 실패: {url}")
                return []

            results = []
            for entry in feed.entries[:max_items]:
                # 출처 추출 (Google News는 source 태그 또는 title에 " - Source" 형태)
                source = ''
                if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                    source = entry.source.title
                elif ' - ' in entry.get('title', ''):
                    source = entry['title'].rsplit(' - ', 1)[-1]

                # 발행일 파싱
                published = ''
                if hasattr(entry, 'published'):
                    published = entry.published
                elif hasattr(entry, 'updated'):
                    published = entry.updated

                # 제목에서 출처 제거 (클린 타이틀)
                title = entry.get('title', '')
                if source and title.endswith(f' - {source}'):
                    title = title[: -(len(source) + 3)]

                results.append({
                    'title': title,
                    'source': source,
                    'published': published,
                    'link': entry.get('link', ''),
                })

            return results

        except Exception as e:
            logger.warning(f"RSS 파싱 예외: {e}")
            return []
