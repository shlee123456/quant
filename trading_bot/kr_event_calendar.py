"""한국 이벤트 캘린더 수집기 - 금통위, 경제지표, 옵션만기, 시장구조 일정

한국 시장 관련 주요 일정을 관리합니다:
  - 한국은행 금융통화위원회 (연 8회)
  - 소비자물가지수 (CPI), GDP, 수출입 통계
  - KOSPI200 정기변경 / 옵션만기일
  - KRX 공휴일

Usage:
    from trading_bot.kr_event_calendar import KREventCalendarCollector

    collector = KREventCalendarCollector()
    events = collector.collect()
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class KREventCalendarCollector:
    """한국 시장 고정 일정 기반 이벤트 수집

    수집 대상:
      - 금융통화위원회 (BOK) 회의 (연 8회)
      - 소비자물가 (CPI) 발표
      - GDP 발표 (분기별)
      - 수출입 통계 발표 (매월 1일)
      - KOSPI200 정기변경 (6월/12월 둘째 금요일)
      - 옵션만기일 (매월 둘째 목요일)
      - KRX 공휴일
    """

    # 한국은행 금융통화위원회 일정 (2026년, 연 8회)
    # https://www.bok.or.kr/
    BOK_RATE_DATES_2026: List[str] = [
        '2026-01-16', '2026-02-27', '2026-04-10', '2026-05-29',
        '2026-07-10', '2026-08-28', '2026-10-15', '2026-11-27',
    ]

    # 소비자물가지수 발표일 (매월 초, 통계청)
    KR_CPI_DATES_2026: List[str] = [
        '2026-01-06', '2026-02-04', '2026-03-04', '2026-04-02',
        '2026-05-06', '2026-06-02', '2026-07-02', '2026-08-04',
        '2026-09-01', '2026-10-06', '2026-11-03', '2026-12-01',
    ]

    # GDP 발표일 (분기별, 한국은행 속보 기준)
    KR_GDP_DATES_2026: List[str] = [
        '2026-01-22',   # 2025 Q4 속보
        '2026-04-23',   # 2026 Q1 속보
        '2026-07-23',   # 2026 Q2 속보
        '2026-10-22',   # 2026 Q3 속보
    ]

    # 수출입 통계 발표일 (매월 1일, 산업통상자원부)
    KR_TRADE_DATES_2026: List[str] = [
        '2026-01-01', '2026-02-01', '2026-03-01', '2026-04-01',
        '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01',
        '2026-09-01', '2026-10-01', '2026-11-01', '2026-12-01',
    ]

    # KOSPI200 정기변경 (6월/12월 둘째 금요일)
    KRX_REBALANCE_DATES: List[str] = [
        '2026-06-12', '2026-12-11',
    ]

    # 옵션만기일 (매월 둘째 목요일)
    KR_OPTIONS_EXPIRY: List[str] = [
        '2026-01-08', '2026-02-12', '2026-03-12', '2026-04-09',
        '2026-05-14', '2026-06-11', '2026-07-09', '2026-08-13',
        '2026-09-10', '2026-10-08', '2026-11-12', '2026-12-10',
    ]

    # KRX 공휴일 (2026년)
    KRX_HOLIDAYS_2026: Dict[str, str] = {
        '2026-01-01': '신정',
        '2026-01-27': '설날 연휴',
        '2026-01-28': '설날',
        '2026-01-29': '설날 연휴',
        '2026-03-01': '삼일절',
        '2026-05-05': '어린이날',
        '2026-05-24': '석가탄신일',
        '2026-06-06': '현충일',
        '2026-08-15': '광복절',
        '2026-09-24': '추석 연휴',
        '2026-09-25': '추석',
        '2026-09-26': '추석 연휴',
        '2026-10-03': '개천절',
        '2026-10-09': '한글날',
        '2026-12-25': '크리스마스',
    }

    def __init__(self) -> None:
        pass

    def collect(self) -> Optional[Dict]:
        """한국 이벤트 캘린더 수집

        Returns:
            {
                'collected_at': str,
                'bok_rate': {next_date, days_until, remaining_2026},
                'economic': {cpi, gdp, trade},
                'options': {monthly_expiry: {next_date, days_until}},
                'market_structure': {krx_rebalance: {next_date, days_until}},
                'holidays': {next_holiday: {date, name, days_until}},
            }
        """
        try:
            bok_rate = self._get_bok_rate_schedule()
            economic = self._get_economic_calendar()
            options = self._get_options_expiry()
            market_structure = self._get_market_structure_events()
            holidays = self._get_next_holiday()

            return {
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'bok_rate': bok_rate,
                'economic': economic,
                'options': options,
                'market_structure': market_structure,
                'holidays': holidays,
            }
        except Exception as e:
            logger.warning(f"한국 이벤트 캘린더 수집 실패: {e}")
            return None

    # ==================== 헬퍼 ====================

    @staticmethod
    def _second_weekday_of_month(year: int, month: int, weekday: int) -> date:
        """특정 월의 둘째 특정 요일 반환 (weekday: 0=월~4=금)"""
        first_day = date(year, month, 1)
        offset = (weekday - first_day.weekday()) % 7
        first_weekday = first_day + timedelta(days=offset)
        # 둘째 해당 요일 = 첫째 + 7일
        return first_weekday + timedelta(weeks=1)

    def _next_date_from_list(self, date_list: List[str]) -> Dict:
        """날짜 리스트에서 today 이후 가장 가까운 날짜 + days_until 반환"""
        today = datetime.now().date()
        for date_str in date_list:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
            if d >= today:
                return {
                    'next_date': date_str,
                    'days_until': (d - today).days,
                }
        return {'next_date': None, 'days_until': None}

    # ==================== 금통위 ====================

    def _get_bok_rate_schedule(self) -> Dict:
        """현재 날짜 기준 다음 금통위 + 남은 일정 반환"""
        today = datetime.now().date()
        remaining: List[str] = []
        next_date: Optional[str] = None
        days_until: Optional[int] = None

        for date_str in self.BOK_RATE_DATES_2026:
            bok_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if bok_date >= today:
                remaining.append(date_str)
                if next_date is None:
                    next_date = date_str
                    days_until = (bok_date - today).days

        return {
            'next_date': next_date,
            'days_until': days_until,
            'remaining_2026': remaining,
        }

    # ==================== 경제지표 ====================

    def _get_economic_calendar(self) -> Dict:
        """CPI/GDP/수출입 각각 다음 일정"""
        return {
            'cpi': self._next_date_from_list(self.KR_CPI_DATES_2026),
            'gdp': self._next_date_from_list(self.KR_GDP_DATES_2026),
            'trade': self._next_date_from_list(self.KR_TRADE_DATES_2026),
        }

    # ==================== 옵션만기 ====================

    def _get_options_expiry(self) -> Dict:
        """다음 옵션 만기일 (둘째 목요일)"""
        return {
            'monthly_expiry': self._next_date_from_list(self.KR_OPTIONS_EXPIRY),
        }

    # ==================== 시장 구조 ====================

    def _get_market_structure_events(self) -> Dict:
        """KOSPI200 정기변경 일정"""
        return {
            'krx_rebalance': self._next_date_from_list(self.KRX_REBALANCE_DATES),
        }

    # ==================== KRX 공휴일 ====================

    def _get_next_holiday(self) -> Dict:
        """다음 KRX 공휴일"""
        today = datetime.now().date()

        for date_str, name in sorted(self.KRX_HOLIDAYS_2026.items()):
            holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if holiday_date >= today:
                return {
                    'next_holiday': {
                        'date': date_str,
                        'name': name,
                        'days_until': (holiday_date - today).days,
                    }
                }

        return {'next_holiday': {'date': None, 'name': None, 'days_until': None}}
