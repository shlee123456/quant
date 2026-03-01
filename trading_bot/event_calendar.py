"""이벤트 캘린더 수집기 - 실적발표일, FOMC 일정"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)


class EventCalendarCollector:
    """yfinance Ticker.calendar + 고정 FOMC 일정 기반 이벤트 수집"""

    FOMC_DATES_2026 = [
        '2026-01-28', '2026-03-18', '2026-05-06', '2026-06-17',
        '2026-07-29', '2026-09-16', '2026-11-04', '2026-12-16',
    ]

    def __init__(self, api_delay: float = 0.3):
        self.api_delay = api_delay

    def collect(self, symbols: List[str]) -> Optional[Dict]:
        """이벤트 캘린더 수집

        Returns:
            {
                'collected_at': str,
                'earnings': {symbol: {date, days_until, estimate_eps, estimate_revenue}},
                'fomc': {next_date, days_until, remaining_2026},
            }
        """
        if not symbols:
            return None

        try:
            earnings = self._fetch_earnings(symbols)
            fomc = self._get_fomc_schedule()

            return {
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'earnings': earnings,
                'fomc': fomc,
            }
        except Exception as e:
            logger.warning(f"이벤트 캘린더 수집 실패: {e}")
            return None

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
