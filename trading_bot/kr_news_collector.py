"""
KR News Collector - 한국 시장 Google News RSS 뉴스 수집기

한국 종목별 + 시장 전체 뉴스를 Google News RSS(한국어)로 수집합니다.
feedparser 라이브러리를 사용하여 RSS 피드를 파싱합니다.

Usage:
    from trading_bot.kr_news_collector import KRNewsCollector

    collector = KRNewsCollector()
    news = collector.collect(['005930', '000660', '035420'])
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

try:
    import feedparser
    _has_feedparser = True
except ImportError:
    _has_feedparser = False

logger = logging.getLogger(__name__)


# 한국 시장 주요 종목 한글명 매핑
KR_STOCK_NAMES: Dict[str, str] = {
    '005930': '삼성전자',
    '000660': 'SK하이닉스',
    '005380': '현대차',
    '035420': 'NAVER',
    '035720': '카카오',
    '006400': '삼성SDI',
    '373220': 'LG에너지솔루션',
    '005490': 'POSCO홀딩스',
    '105560': 'KB금융',
    '207940': '삼성바이오로직스',
    '000270': '기아',
    '068270': '셀트리온',
    '012330': '현대모비스',
    '055550': '신한지주',
    '051910': 'LG화학',
    '096770': 'SK이노베이션',
}

# 한국 시장 전체 뉴스 검색 키워드
KR_MARKET_KEYWORDS: List[str] = [
    '한국 주식시장',
    '코스피',
    '한국은행 기준금리',
    '코스닥',
    '원달러 환율',
]


class KRNewsCollector:
    """Google News RSS(한국어)를 통해 한국 종목별/시장 뉴스를 수집하는 클래스"""

    def __init__(self, request_delay: float = 0.3):
        """
        Args:
            request_delay: RSS 요청 간 대기 시간(초), rate limit 방지
        """
        if not _has_feedparser:
            raise ImportError(
                "feedparser 패키지가 필요합니다. 설치: pip install feedparser"
            )
        self.request_delay = request_delay

    def collect(
        self,
        symbols: Optional[List[str]] = None,
        max_per_symbol: int = 5,
    ) -> Dict:
        """
        한국 종목별 + 시장 전체 뉴스 수집

        Args:
            symbols: 종목 코드 리스트 (예: ['005930', '035420']).
                     None이면 시장 전체 뉴스만 수집.
            max_per_symbol: 종목당 최대 뉴스 수

        Returns:
            뉴스 데이터 딕셔너리
        """
        collected_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # 시장 전체 뉴스
        market_news = self._fetch_market_news(max_items=5)

        # 종목별 뉴스
        stock_news: Dict[str, List[Dict]] = {}
        if symbols:
            for symbol in symbols:
                try:
                    news = self._fetch_stock_news(symbol, max_items=max_per_symbol)
                    if news:
                        stock_news[symbol] = news
                    time.sleep(self.request_delay)
                except Exception as e:
                    logger.warning(f"{symbol} 뉴스 수집 실패: {e}")
                    continue

        logger.info(
            f"한국 뉴스 수집 완료: 시장 {len(market_news)}건, "
            f"종목 {sum(len(v) for v in stock_news.values())}건"
        )

        return {
            'collected_at': collected_at,
            'market_news': market_news,
            'stock_news': stock_news,
        }

    def _fetch_stock_news(self, symbol: str, max_items: int = 5) -> List[Dict]:
        """종목 코드에 해당하는 한글 회사명으로 Google News RSS에서 뉴스 수집"""
        company_name = KR_STOCK_NAMES.get(symbol)
        if not company_name:
            # 매핑에 없는 종목은 코드로 검색
            company_name = symbol

        query = company_name.replace(' ', '+')
        url = (
            f"https://news.google.com/rss/search?"
            f"q={query}+주식&hl=ko&gl=KR&ceid=KR:ko"
        )
        return self._parse_rss(url, max_items)

    def _fetch_market_news(self, max_items: int = 5) -> List[Dict]:
        """한국 시장 전체 뉴스 수집"""
        all_news: List[Dict] = []
        for keyword in KR_MARKET_KEYWORDS:
            try:
                query = keyword.replace(' ', '+')
                url = (
                    f"https://news.google.com/rss/search?"
                    f"q={query}&hl=ko&gl=KR&ceid=KR:ko"
                )
                news = self._parse_rss(url, max_items=2)
                all_news.extend(news)
                time.sleep(self.request_delay)
            except Exception as e:
                logger.warning(f"한국 시장 뉴스 수집 실패 ({keyword}): {e}")
                continue

        return self._deduplicate_news(all_news)[:max_items]

    def _parse_rss(self, url: str, max_items: int = 5) -> List[Dict]:
        """RSS 피드를 파싱하여 뉴스 리스트 반환"""
        try:
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                logger.warning(f"RSS 파싱 실패: {url}")
                return []

            results: List[Dict] = []
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

    def _deduplicate_news(self, news_list: List[Dict]) -> List[Dict]:
        """제목 기반 중복 제거"""
        seen_titles: set = set()
        unique: List[Dict] = []
        for item in news_list:
            title = item.get('title', '')
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique.append(item)
        return unique
