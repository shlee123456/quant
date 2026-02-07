"""
Market Hours Utility for US Stock Market
Displays market status and trading hours in both EST and KST
"""

from datetime import datetime, time, timedelta
from typing import Dict, Tuple
import pytz


class MarketHours:
    """US Stock Market Hours Manager"""

    def __init__(self):
        self.est_tz = pytz.timezone('US/Eastern')
        self.kst_tz = pytz.timezone('Asia/Seoul')

        # US Market Hours (EST)
        self.pre_market_start = time(4, 0)  # 4:00 AM EST
        self.pre_market_end = time(9, 30)   # 9:30 AM EST
        self.regular_start = time(9, 30)     # 9:30 AM EST
        self.regular_end = time(16, 0)       # 4:00 PM EST
        self.after_hours_start = time(16, 0) # 4:00 PM EST
        self.after_hours_end = time(20, 0)   # 8:00 PM EST

        # Weekend days
        self.weekend_days = [5, 6]  # Saturday, Sunday

    def get_current_est_time(self) -> datetime:
        """Get current time in EST"""
        return datetime.now(self.est_tz)

    def get_current_kst_time(self) -> datetime:
        """Get current time in KST"""
        return datetime.now(self.kst_tz)

    def is_weekend(self, dt: datetime = None) -> bool:
        """Check if it's weekend"""
        if dt is None:
            dt = self.get_current_est_time()
        return dt.weekday() in self.weekend_days

    def is_holiday(self, dt: datetime = None) -> bool:
        """
        Check if it's a US market holiday
        TODO: Implement actual holiday calendar
        """
        # For now, just return False
        # In production, use pandas_market_calendars or similar
        return False

    def get_market_status(self) -> Dict[str, any]:
        """
        Get current market status

        Returns:
            dict with keys:
                - status: 'pre_market', 'regular', 'after_hours', 'closed'
                - is_trading_day: bool
                - current_time_est: datetime
                - current_time_kst: datetime
                - next_open: datetime (EST)
                - next_close: datetime (EST)
        """
        now_est = self.get_current_est_time()
        now_kst = self.get_current_kst_time()
        current_time = now_est.time()

        # Check if weekend or holiday
        is_trading_day = not (self.is_weekend(now_est) or self.is_holiday(now_est))

        if not is_trading_day:
            status = 'closed'
            # Next open is Monday 9:30 AM EST
            days_until_monday = (7 - now_est.weekday()) % 7
            if days_until_monday == 0 and current_time >= self.regular_end:
                days_until_monday = 1
            next_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
            next_open = next_open + timedelta(days=days_until_monday)
            next_close = next_open.replace(hour=16, minute=0)
        else:
            # Determine current market session
            if self.pre_market_start <= current_time < self.pre_market_end:
                status = 'pre_market'
                next_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
                next_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
            elif self.regular_start <= current_time < self.regular_end:
                status = 'regular'
                next_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
                next_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
            elif self.after_hours_start <= current_time < self.after_hours_end:
                status = 'after_hours'
                # Next open is tomorrow 9:30 AM
                next_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
                next_open = next_open + timedelta(days=1)
                next_close = now_est.replace(hour=20, minute=0, second=0, microsecond=0)
            else:
                # Between midnight and 4 AM, or after 8 PM
                status = 'closed'
                if current_time < self.pre_market_start:
                    # Before 4 AM - next open is today 4 AM
                    next_open = now_est.replace(hour=4, minute=0, second=0, microsecond=0)
                else:
                    # After 8 PM - next open is tomorrow 4 AM
                    next_open = now_est.replace(hour=4, minute=0, second=0, microsecond=0)
                    next_open = next_open + timedelta(days=1)
                next_close = next_open.replace(hour=20, minute=0)

        return {
            'status': status,
            'is_trading_day': is_trading_day,
            'current_time_est': now_est,
            'current_time_kst': now_kst,
            'next_open': next_open,
            'next_close': next_close
        }

    def get_market_hours_display(self) -> Dict[str, str]:
        """
        Get market hours for display in dashboard

        Returns:
            dict with formatted time strings in both EST and KST
        """
        # Create a reference datetime for today
        now_est = self.get_current_est_time()

        # Pre-market
        pre_start_est = now_est.replace(hour=4, minute=0, second=0, microsecond=0)
        pre_end_est = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
        pre_start_kst = pre_start_est.astimezone(self.kst_tz)
        pre_end_kst = pre_end_est.astimezone(self.kst_tz)

        # Regular hours
        reg_start_est = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
        reg_end_est = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
        reg_start_kst = reg_start_est.astimezone(self.kst_tz)
        reg_end_kst = reg_end_est.astimezone(self.kst_tz)

        # After hours
        after_start_est = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
        after_end_est = now_est.replace(hour=20, minute=0, second=0, microsecond=0)
        after_start_kst = after_start_est.astimezone(self.kst_tz)
        after_end_kst = after_end_est.astimezone(self.kst_tz)

        return {
            'pre_market_est': f"{pre_start_est.strftime('%H:%M')} - {pre_end_est.strftime('%H:%M')} EST",
            'pre_market_kst': f"{pre_start_kst.strftime('%H:%M')} - {pre_end_kst.strftime('%H:%M')} KST",
            'regular_est': f"{reg_start_est.strftime('%H:%M')} - {reg_end_est.strftime('%H:%M')} EST",
            'regular_kst': f"{reg_start_kst.strftime('%H:%M')} - {reg_end_kst.strftime('%H:%M')} KST",
            'after_hours_est': f"{after_start_est.strftime('%H:%M')} - {after_end_est.strftime('%H:%M')} EST",
            'after_hours_kst': f"{after_start_kst.strftime('%H:%M')} - {after_end_kst.strftime('%H:%M')} KST"
        }

    def format_status_message(self, lang: str = 'en') -> Tuple[str, str]:
        """
        Format market status message for display

        Args:
            lang: 'en' or 'ko'

        Returns:
            (status_text, color) tuple
        """
        status_info = self.get_market_status()
        status = status_info['status']
        current_est = status_info['current_time_est']
        current_kst = status_info['current_time_kst']

        status_messages = {
            'en': {
                'pre_market': (f"🟡 Pre-Market Open | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'regular': (f"🟢 Market Open | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'after_hours': (f"🟠 After Hours | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'closed': (f"🔴 Market Closed | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "inverse")
            },
            'ko': {
                'pre_market': (f"🟡 프리마켓 | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'regular': (f"🟢 정규장 개장 | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'after_hours': (f"🟠 애프터아워 | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "normal"),
                'closed': (f"🔴 장 마감 | {current_est.strftime('%H:%M')} EST / {current_kst.strftime('%H:%M')} KST", "inverse")
            }
        }

        return status_messages.get(lang, status_messages['en']).get(status, ("Unknown", "normal"))
