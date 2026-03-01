"""이벤트 캘린더 수집기 - 실적발표일, FOMC, 경제지표, 옵션만기, 시장구조 일정"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)


class EventCalendarCollector:
    """yfinance Ticker.calendar + 고정 일정 기반 이벤트 수집

    수집 대상 (15종):
      - FOMC 회의 / FOMC 의사록 (21일 후)
      - CPI, PPI, NFP, PCE, GDP, ISM 제조업, ISM 서비스업, 잭슨홀
      - 월간 옵션 만기 (Quad Witching 포함) / VIX 만기
      - S&P 500 리밸런싱 / Russell 리밸런싱
      - NYSE 공휴일
      - 실적발표 (yfinance)
    """

    # Fed 공식 캘린더: federalreserve.gov/monetarypolicy/fomccalendars.htm
    FOMC_DATES_2026 = [
        '2026-01-28', '2026-03-18', '2026-04-29', '2026-06-17',
        '2026-07-29', '2026-09-16', '2026-10-28', '2026-12-09',
    ]

    # FRED Release Calendar + BLS 확인 (셧다운 지연 반영)
    CPI_DATES_2026 = [
        '2026-01-13', '2026-02-13', '2026-03-11', '2026-04-10',
        '2026-05-12', '2026-06-10', '2026-07-14', '2026-08-12',
        '2026-09-11', '2026-10-14', '2026-11-10', '2026-12-10',
    ]

    NFP_DATES_2026 = [
        '2026-01-09', '2026-02-11', '2026-03-06', '2026-04-03',
        '2026-05-08', '2026-06-05', '2026-07-02', '2026-08-07',
        '2026-09-04', '2026-10-02', '2026-11-06', '2026-12-04',
    ]

    PPI_DATES_2026 = [
        '2026-01-14', '2026-02-27', '2026-03-18', '2026-04-14',
        '2026-05-13', '2026-06-11', '2026-07-15', '2026-08-13',
        '2026-09-10', '2026-10-15', '2026-11-13', '2026-12-15',
    ]

    PCE_DATES_2026 = [
        '2026-02-20', '2026-03-13', '2026-04-09', '2026-04-30',
        '2026-05-28', '2026-06-25', '2026-07-30', '2026-08-26',
        '2026-09-30', '2026-10-29', '2026-11-25', '2026-12-23',
    ]

    GDP_DATES_2026 = [
        '2026-04-30', '2026-05-28', '2026-06-25',
        '2026-07-30', '2026-08-26', '2026-09-30',
        '2026-10-29', '2026-11-25', '2026-12-23',
    ]

    ISM_MFG_DATES_2026 = [
        '2026-01-05', '2026-02-02', '2026-03-02', '2026-04-01',
        '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-03',
        '2026-09-01', '2026-10-01', '2026-11-02', '2026-12-01',
    ]

    ISM_SVC_DATES_2026 = [
        '2026-01-07', '2026-02-05', '2026-03-04', '2026-04-06',
        '2026-05-06', '2026-06-03', '2026-07-08', '2026-08-05',
        '2026-09-04', '2026-10-06', '2026-11-04', '2026-12-03',
    ]

    JACKSON_HOLE_2026 = ['2026-08-20', '2026-08-21', '2026-08-22']

    NYSE_HOLIDAYS_2026 = {
        '2026-01-01': "New Year's Day",
        '2026-01-19': 'MLK Day',
        '2026-02-16': "Presidents' Day",
        '2026-04-03': 'Good Friday',
        '2026-05-25': 'Memorial Day',
        '2026-06-19': 'Juneteenth',
        '2026-07-03': 'Independence Day (observed)',
        '2026-09-07': 'Labor Day',
        '2026-11-26': 'Thanksgiving',
        '2026-12-25': 'Christmas',
    }

    QUAD_WITCHING_MONTHS = {3, 6, 9, 12}

    def __init__(self, api_delay: float = 0.3):
        self.api_delay = api_delay

    def collect(self, symbols: List[str]) -> Optional[Dict]:
        """이벤트 캘린더 수집

        Returns:
            {
                'collected_at': str,
                'earnings': {symbol: {date, days_until, estimate_eps, estimate_revenue}},
                'fomc': {next_date, days_until, remaining_2026},
                'fomc_minutes': {next_date, days_until},
                'economic': {cpi, nfp, pce, ppi, gdp, ism_manufacturing, ism_services, jackson_hole},
                'options': {monthly_expiry: {next_date, days_until}, is_quad_witching},
                'vix_expiry': {next_date, days_until},
                'market_structure': {sp500_rebalance, russell_rebalance},
                'holidays': {next_holiday: {date, name, days_until}},
            }
        """
        if not symbols:
            return None

        try:
            earnings = self._fetch_earnings(symbols)
            fomc = self._get_fomc_schedule()
            fomc_minutes = self._get_fomc_minutes()
            economic = self._get_economic_calendar()
            options = self._get_options_expiry()
            vix_expiry = self._get_vix_expiry()
            market_structure = self._get_market_structure_events()
            holidays = self._get_next_holiday()

            return {
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'earnings': earnings,
                'fomc': fomc,
                'fomc_minutes': fomc_minutes,
                'economic': economic,
                'options': options,
                'vix_expiry': vix_expiry,
                'market_structure': market_structure,
                'holidays': holidays,
            }
        except Exception as e:
            logger.warning(f"이벤트 캘린더 수집 실패: {e}")
            return None

    # ==================== 헬퍼 ====================

    @staticmethod
    def _third_weekday_of_month(year: int, month: int, weekday: int) -> date:
        """특정 월의 셋째 특정 요일 반환 (weekday: 0=월~4=금)"""
        first_day = date(year, month, 1)
        # 해당 월 첫 번째 해당 요일까지의 오프셋
        offset = (weekday - first_day.weekday()) % 7
        first_weekday = first_day + timedelta(days=offset)
        # 셋째 해당 요일 = 첫째 + 14일
        return first_weekday + timedelta(weeks=2)

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

    # ==================== 실적발표 ====================

    def _fetch_earnings(self, symbols: List[str]) -> Dict:
        """yfinance Ticker.calendar로 실적발표 일정 수집"""
        earnings = {}
        today = datetime.now().date()

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                cal = ticker.calendar

                if cal is None or (hasattr(cal, 'empty') and cal.empty):
                    continue

                # calendar can be a dict or DataFrame depending on yfinance version
                if isinstance(cal, dict):
                    earnings_date = cal.get('Earnings Date')
                    if isinstance(earnings_date, list) and earnings_date:
                        earnings_date = earnings_date[0]

                    if earnings_date:
                        if hasattr(earnings_date, 'date'):
                            ed = earnings_date.date()
                        else:
                            ed = datetime.strptime(str(earnings_date)[:10], '%Y-%m-%d').date()

                        days_until = (ed - today).days
                        earnings[symbol] = {
                            'date': ed.strftime('%Y-%m-%d'),
                            'days_until': days_until,
                            'estimate_eps': cal.get('Earnings Average'),
                            'estimate_revenue': cal.get('Revenue Average'),
                        }
                else:
                    # DataFrame format
                    if 'Earnings Date' in cal.index:
                        earnings_date = cal.loc['Earnings Date'].iloc[0] if len(cal.columns) > 0 else None
                        if earnings_date and str(earnings_date) != 'NaT':
                            if hasattr(earnings_date, 'date'):
                                ed = earnings_date.date()
                            else:
                                ed = datetime.strptime(str(earnings_date)[:10], '%Y-%m-%d').date()

                            days_until = (ed - today).days
                            estimate_eps = None
                            estimate_revenue = None

                            if 'Earnings Average' in cal.index:
                                estimate_eps = cal.loc['Earnings Average'].iloc[0]
                            if 'Revenue Average' in cal.index:
                                estimate_revenue = cal.loc['Revenue Average'].iloc[0]

                            earnings[symbol] = {
                                'date': ed.strftime('%Y-%m-%d'),
                                'days_until': days_until,
                                'estimate_eps': float(estimate_eps) if estimate_eps is not None else None,
                                'estimate_revenue': float(estimate_revenue) if estimate_revenue is not None else None,
                            }

                time.sleep(self.api_delay)
            except Exception as e:
                logger.debug(f"실적발표 일정 조회 실패 ({symbol}): {e}")
                continue

        return earnings

    # ==================== FOMC ====================

    def _get_fomc_schedule(self) -> Dict:
        """현재 날짜 기준 다음 FOMC + 남은 일정 반환"""
        today = datetime.now().date()
        remaining = []
        next_date = None
        days_until = None

        for date_str in self.FOMC_DATES_2026:
            fomc_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if fomc_date >= today:
                remaining.append(date_str)
                if next_date is None:
                    next_date = date_str
                    days_until = (fomc_date - today).days

        return {
            'next_date': next_date,
            'days_until': days_until,
            'remaining_2026': remaining,
        }

    def _get_fomc_minutes(self) -> Dict:
        """다음 FOMC 의사록 공개일 (FOMC 회의 21일 후)"""
        today = datetime.now().date()

        for date_str in self.FOMC_DATES_2026:
            fomc_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            minutes_date = fomc_date + timedelta(days=21)
            if minutes_date >= today:
                return {
                    'next_date': minutes_date.strftime('%Y-%m-%d'),
                    'days_until': (minutes_date - today).days,
                }

        return {'next_date': None, 'days_until': None}

    # ==================== 경제지표 ====================

    def _get_economic_calendar(self) -> Dict:
        """CPI/NFP/PCE/PPI/GDP/ISM/잭슨홀 각각 다음 일정"""
        return {
            'cpi': self._next_date_from_list(self.CPI_DATES_2026),
            'nfp': self._next_date_from_list(self.NFP_DATES_2026),
            'ppi': self._next_date_from_list(self.PPI_DATES_2026),
            'pce': self._next_date_from_list(self.PCE_DATES_2026),
            'gdp': self._next_date_from_list(self.GDP_DATES_2026),
            'ism_manufacturing': self._next_date_from_list(self.ISM_MFG_DATES_2026),
            'ism_services': self._next_date_from_list(self.ISM_SVC_DATES_2026),
            'jackson_hole': self._next_date_from_list(self.JACKSON_HOLE_2026),
        }

    # ==================== 옵션/파생 ====================

    def _get_options_expiry(self) -> Dict:
        """다음 옵션 만기일 + Quad Witching 여부"""
        today = datetime.now().date()

        # 향후 12개월 내 셋째 금요일 탐색
        for month_offset in range(13):
            year = today.year + (today.month + month_offset - 1) // 12
            month = (today.month + month_offset - 1) % 12 + 1
            third_friday = self._third_weekday_of_month(year, month, 4)  # 4=금요일
            if third_friday >= today:
                is_quad = month in self.QUAD_WITCHING_MONTHS
                return {
                    'monthly_expiry': {
                        'next_date': third_friday.strftime('%Y-%m-%d'),
                        'days_until': (third_friday - today).days,
                    },
                    'is_quad_witching': is_quad,
                }

        return {
            'monthly_expiry': {'next_date': None, 'days_until': None},
            'is_quad_witching': False,
        }

    def _get_vix_expiry(self) -> Dict:
        """다음 VIX 만기일 (매월 셋째 수요일)"""
        today = datetime.now().date()

        for month_offset in range(13):
            year = today.year + (today.month + month_offset - 1) // 12
            month = (today.month + month_offset - 1) % 12 + 1
            third_wednesday = self._third_weekday_of_month(year, month, 2)  # 2=수요일
            if third_wednesday >= today:
                return {
                    'next_date': third_wednesday.strftime('%Y-%m-%d'),
                    'days_until': (third_wednesday - today).days,
                }

        return {'next_date': None, 'days_until': None}

    # ==================== 시장 구조 ====================

    def _get_market_structure_events(self) -> Dict:
        """S&P 리밸런싱, Russell 리밸런싱"""
        today = datetime.now().date()

        # S&P 500 리밸런싱: 3/6/9/12월 셋째 금요일
        sp500_rebalance = {'next_date': None, 'days_until': None}
        for month_offset in range(13):
            year = today.year + (today.month + month_offset - 1) // 12
            month = (today.month + month_offset - 1) % 12 + 1
            if month in self.QUAD_WITCHING_MONTHS:
                third_friday = self._third_weekday_of_month(year, month, 4)
                if third_friday >= today:
                    sp500_rebalance = {
                        'next_date': third_friday.strftime('%Y-%m-%d'),
                        'days_until': (third_friday - today).days,
                    }
                    break

        # Russell 리밸런싱: 6월 마지막 금요일
        russell_rebalance = {'next_date': None, 'days_until': None}
        for year_offset in range(2):
            year = today.year + year_offset
            # 6월 마지막 금요일: 6/30부터 역으로 탐색
            last_day = date(year, 6, 30)
            offset = (last_day.weekday() - 4) % 7  # 4=금요일
            last_friday = last_day - timedelta(days=offset)
            if last_friday >= today:
                russell_rebalance = {
                    'next_date': last_friday.strftime('%Y-%m-%d'),
                    'days_until': (last_friday - today).days,
                }
                break

        return {
            'sp500_rebalance': sp500_rebalance,
            'russell_rebalance': russell_rebalance,
        }

    # ==================== NYSE 공휴일 ====================

    def _get_next_holiday(self) -> Dict:
        """다음 NYSE 공휴일"""
        today = datetime.now().date()

        for date_str, name in sorted(self.NYSE_HOLIDAYS_2026.items()):
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
