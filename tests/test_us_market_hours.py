"""미국 시장 시간 DST 자동 감지 테스트."""

from datetime import date

import pytest

from trading_bot.us_market_hours import (
    get_market_hours_kst,
    get_schedule_description,
    is_dst,
)


class TestIsDst:
    def test_summer_is_dst(self):
        """7월은 서머타임(EDT)."""
        from datetime import datetime
        import pytz
        et = pytz.timezone('US/Eastern')
        summer = et.localize(datetime(2026, 7, 15, 12, 0))
        assert is_dst(summer) is True

    def test_winter_is_not_dst(self):
        """1월은 윈터타임(EST)."""
        from datetime import datetime
        import pytz
        et = pytz.timezone('US/Eastern')
        winter = et.localize(datetime(2026, 1, 15, 12, 0))
        assert is_dst(winter) is False


class TestGetMarketHoursKst:
    def test_summer_hours(self):
        """서머타임(EDT): 개장 22:30 KST, 마감 05:00 KST."""
        hours = get_market_hours_kst(date(2026, 7, 15))
        assert hours['open'] == {'hour': 22, 'minute': 30}
        assert hours['close'] == {'hour': 5, 'minute': 0}
        assert hours['is_dst'] is True
        assert hours['et_label'] == 'EDT'

    def test_winter_hours(self):
        """윈터타임(EST): 개장 23:30 KST, 마감 06:00 KST."""
        hours = get_market_hours_kst(date(2026, 1, 15))
        assert hours['open'] == {'hour': 23, 'minute': 30}
        assert hours['close'] == {'hour': 6, 'minute': 0}
        assert hours['is_dst'] is False
        assert hours['et_label'] == 'EST'

    def test_close_offsets_summer(self):
        """서머타임 마감 후 오프셋."""
        hours = get_market_hours_kst(date(2026, 7, 15))
        assert hours['close_5m'] == {'hour': 5, 'minute': 5}
        assert hours['close_10m'] == {'hour': 5, 'minute': 10}

    def test_close_offsets_winter(self):
        """윈터타임 마감 후 오프셋."""
        hours = get_market_hours_kst(date(2026, 1, 15))
        assert hours['close_5m'] == {'hour': 6, 'minute': 5}
        assert hours['close_10m'] == {'hour': 6, 'minute': 10}

    def test_dst_transition_march(self):
        """3월 DST 전환 경계 (2026년 3월 8일 전환)."""
        # 전환 전 (EST)
        before = get_market_hours_kst(date(2026, 3, 7))
        assert before['is_dst'] is False
        assert before['open']['hour'] == 23

        # 전환 후 (EDT)
        after = get_market_hours_kst(date(2026, 3, 9))
        assert after['is_dst'] is True
        assert after['open']['hour'] == 22

    def test_dst_transition_november(self):
        """11월 DST 전환 경계 (2026년 11월 1일 전환)."""
        # 전환 전 (EDT)
        before = get_market_hours_kst(date(2026, 10, 31))
        assert before['is_dst'] is True
        assert before['open']['hour'] == 22

        # 전환 후 (EST)
        after = get_market_hours_kst(date(2026, 11, 2))
        assert after['is_dst'] is False
        assert after['open']['hour'] == 23


class TestScheduleDescription:
    def test_contains_kst(self):
        """스케줄 설명에 KST 포함."""
        desc = get_schedule_description()
        assert 'KST' in desc
        assert '페이퍼 트레이딩' in desc
        assert '시장 분석' in desc

    def test_contains_et_label(self):
        """스케줄 설명에 EDT 또는 EST 포함."""
        desc = get_schedule_description()
        assert 'EDT' in desc or 'EST' in desc
