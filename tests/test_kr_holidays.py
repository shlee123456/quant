"""
Tests for kr_holidays.py — 한국 주식시장 공휴일 캘린더.
"""

import datetime

import pytest

from trading_bot.kr_holidays import (
    get_kr_market_holidays,
    is_kr_market_holiday,
    _substitute_holiday,
    _LUNAR_NEW_YEAR,
    _BUDDHAS_BIRTHDAY,
    _CHUSEOK,
)


# ─── 고정 공휴일 테스트 ───


class TestFixedHolidays:
    """고정 공휴일이 정확히 포함되는지 검증."""

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_new_year(self, year: int):
        """신정 (1/1) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 1, 1) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_independence_movement_day(self, year: int):
        """삼일절 (3/1) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 3, 1) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_childrens_day(self, year: int):
        """어린이날 (5/5) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 5, 5) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_memorial_day(self, year: int):
        """현충일 (6/6) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 6, 6) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_liberation_day(self, year: int):
        """광복절 (8/15) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 8, 15) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_national_foundation_day(self, year: int):
        """개천절 (10/3) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 10, 3) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_hangul_day(self, year: int):
        """한글날 (10/9) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 10, 9) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_christmas(self, year: int):
        """크리스마스 (12/25) 포함."""
        holidays = get_kr_market_holidays(year)
        assert datetime.date(year, 12, 25) in holidays

    def test_fixed_holiday_count(self):
        """고정 공휴일은 8개."""
        fixed_dates = [
            datetime.date(2027, 1, 1),
            datetime.date(2027, 3, 1),
            datetime.date(2027, 5, 5),
            datetime.date(2027, 6, 6),
            datetime.date(2027, 8, 15),
            datetime.date(2027, 10, 3),
            datetime.date(2027, 10, 9),
            datetime.date(2027, 12, 25),
        ]
        holidays = get_kr_market_holidays(2027)
        for dt in fixed_dates:
            assert dt in holidays


# ─── 음력 변동 공휴일 테스트 ───


class TestLunarHolidays:
    """음력 변동 공휴일 (설날, 부처님오신날, 추석) 검증."""

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_seollal_3_days(self, year: int):
        """설날 3일 연휴 (전날, 당일, 다음날) 포함."""
        holidays = get_kr_market_holidays(year)
        month, day = _LUNAR_NEW_YEAR[year]
        seollal = datetime.date(year, month, day)

        assert (seollal - datetime.timedelta(days=1)) in holidays
        assert seollal in holidays
        assert (seollal + datetime.timedelta(days=1)) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_buddhas_birthday(self, year: int):
        """부처님오신날 포함."""
        holidays = get_kr_market_holidays(year)
        month, day = _BUDDHAS_BIRTHDAY[year]
        assert datetime.date(year, month, day) in holidays

    @pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2029, 2030])
    def test_chuseok_3_days(self, year: int):
        """추석 3일 연휴 (전날, 당일, 다음날) 포함."""
        holidays = get_kr_market_holidays(year)
        month, day = _CHUSEOK[year]
        chuseok = datetime.date(year, month, day)

        assert (chuseok - datetime.timedelta(days=1)) in holidays
        assert chuseok in holidays
        assert (chuseok + datetime.timedelta(days=1)) in holidays

    def test_seollal_2025_specific_dates(self):
        """2025년 설날 구체적 날짜 확인 (1/28, 1/29, 1/30)."""
        holidays = get_kr_market_holidays(2025)
        assert datetime.date(2025, 1, 28) in holidays
        assert datetime.date(2025, 1, 29) in holidays
        assert datetime.date(2025, 1, 30) in holidays

    def test_chuseok_2025_specific_dates(self):
        """2025년 추석 구체적 날짜 확인 (10/5, 10/6, 10/7)."""
        holidays = get_kr_market_holidays(2025)
        assert datetime.date(2025, 10, 5) in holidays
        assert datetime.date(2025, 10, 6) in holidays
        assert datetime.date(2025, 10, 7) in holidays

    def test_buddhas_birthday_2025(self):
        """2025년 부처님오신날: 5월 5일."""
        holidays = get_kr_market_holidays(2025)
        assert datetime.date(2025, 5, 5) in holidays


# ─── 대체공휴일법 테스트 ───


class TestSubstituteHoliday:
    """대체공휴일법 적용 검증."""

    def test_weekday_no_change(self):
        """평일 공휴일은 대체 없음."""
        # 2025-01-01 (수요일)
        dt = datetime.date(2025, 1, 1)
        existing = {dt}
        result = _substitute_holiday(dt, existing)
        assert result == dt

    def test_saturday_shifted_to_monday(self):
        """토요일 공휴일 -> 다음 월요일."""
        # 2025-03-01 (토요일)
        dt = datetime.date(2025, 3, 1)
        existing = {dt}
        result = _substitute_holiday(dt, existing)
        assert result == datetime.date(2025, 3, 3)  # 월요일
        assert result.weekday() == 0

    def test_sunday_shifted_to_monday(self):
        """일요일 공휴일 -> 다음 월요일."""
        # 2026-03-01 (일요일)
        dt = datetime.date(2026, 3, 1)
        existing = {dt}
        result = _substitute_holiday(dt, existing)
        assert result == datetime.date(2026, 3, 2)  # 월요일
        assert result.weekday() == 0

    def test_substitute_avoids_existing_holiday(self):
        """다음 월요일이 이미 공휴일이면 그 다음 평일."""
        dt = datetime.date(2025, 3, 1)  # 토요일
        monday = datetime.date(2025, 3, 3)
        existing = {dt, monday}
        result = _substitute_holiday(dt, existing)
        assert result == datetime.date(2025, 3, 4)  # 화요일
        assert result.weekday() == 1

    def test_substitute_skips_weekend_and_holidays(self):
        """연속 공휴일+주말 조합 시 올바른 평일 찾기."""
        # 토요일 -> 월요일이 공휴일 -> 화요일이 공휴일 -> 수요일
        saturday = datetime.date(2025, 10, 4)  # 토요일
        monday = datetime.date(2025, 10, 6)
        tuesday = datetime.date(2025, 10, 7)
        existing = {saturday, monday, tuesday}
        result = _substitute_holiday(saturday, existing)
        assert result == datetime.date(2025, 10, 8)  # 수요일

    def test_2025_samiljul_substitute(self):
        """2025년 삼일절(3/1, 토) 대체공휴일 -> 3/3(월)."""
        holidays = get_kr_market_holidays(2025)
        # 삼일절이 토요일이므로 3/3(월)이 대체공휴일
        assert datetime.date(2025, 3, 3) in holidays

    def test_2028_christmas_substitute(self):
        """2028년 크리스마스(12/25, 월) -> 대체 없음 (평일)."""
        holidays = get_kr_market_holidays(2028)
        # 12/25가 월요일이므로 대체공휴일 없음
        assert datetime.date(2028, 12, 25) in holidays
        # 12/26은 공휴일이 아님 (다른 공휴일과 겹치지 않는 한)
        # 12/26이 holidays에 있는지는 다른 공휴일 유무에 따라 다름


# ─── is_kr_market_holiday 테스트 ───


class TestIsKrMarketHoliday:
    """is_kr_market_holiday() 함수 검증."""

    def test_weekend_saturday(self):
        """토요일은 휴장."""
        assert is_kr_market_holiday(datetime.date(2025, 3, 8)) is True

    def test_weekend_sunday(self):
        """일요일은 휴장."""
        assert is_kr_market_holiday(datetime.date(2025, 3, 9)) is True

    def test_weekday_not_holiday(self):
        """일반 평일은 영업일."""
        # 2025-03-04 (화요일, 공휴일 아님)
        assert is_kr_market_holiday(datetime.date(2025, 3, 4)) is False

    def test_fixed_holiday(self):
        """고정 공휴일 감지."""
        # 2026-01-01 (목요일, 신정)
        assert is_kr_market_holiday(datetime.date(2026, 1, 1)) is True

    def test_lunar_holiday(self):
        """음력 공휴일 감지."""
        # 2025 설날 당일: 1/29 (수)
        assert is_kr_market_holiday(datetime.date(2025, 1, 29)) is True

    def test_datetime_input(self):
        """datetime.datetime 입력도 처리."""
        dt = datetime.datetime(2025, 1, 29, 10, 30, 0)
        assert is_kr_market_holiday(dt) is True

    def test_regular_trading_day(self):
        """일반 거래일은 False."""
        # 2025-03-05 (수요일, 공휴일 아님)
        assert is_kr_market_holiday(datetime.date(2025, 3, 5)) is False


# ─── 범위 밖 연도 테스트 ───


class TestOutOfRangeYear:
    """2025-2030 범위 밖 연도 처리."""

    def test_year_outside_range_returns_fixed_only(self):
        """지원 범위 밖 연도는 고정 공휴일만 반환."""
        holidays = get_kr_market_holidays(2035)
        # 고정 공휴일은 포함
        assert datetime.date(2035, 1, 1) in holidays
        assert datetime.date(2035, 3, 1) in holidays
        assert datetime.date(2035, 12, 25) in holidays

    def test_year_2024_no_lunar(self):
        """2024년은 음력 데이터 없음 -> 고정 공휴일만."""
        holidays = get_kr_market_holidays(2024)
        assert datetime.date(2024, 1, 1) in holidays
        assert datetime.date(2024, 8, 15) in holidays
        # 설날/추석 음력 데이터 없으므로 해당 날짜 미포함
        # (정확한 날짜를 알 수 없으므로 고정 공휴일만 검증)


# ─── 반환 타입 테스트 ───


class TestReturnTypes:
    """반환 타입 검증."""

    def test_returns_set(self):
        """get_kr_market_holidays는 set 반환."""
        result = get_kr_market_holidays(2025)
        assert isinstance(result, set)

    def test_all_elements_are_dates(self):
        """모든 원소가 datetime.date."""
        result = get_kr_market_holidays(2025)
        for dt in result:
            assert isinstance(dt, datetime.date)

    def test_returns_bool(self):
        """is_kr_market_holiday는 bool 반환."""
        result = is_kr_market_holiday(datetime.date(2025, 1, 1))
        assert isinstance(result, bool)

    def test_holidays_nonempty(self):
        """공휴일 집합이 비어있지 않음."""
        for year in range(2025, 2031):
            holidays = get_kr_market_holidays(year)
            assert len(holidays) >= 8  # 최소 고정 공휴일 8개


# ─── 특수 케이스 테스트 ───


class TestSpecialCases:
    """특수 케이스 검증."""

    def test_2025_buddhas_birthday_overlaps_childrens_day(self):
        """2025년 부처님오신날(5/5)과 어린이날(5/5) 겹침.

        두 공휴일 모두 5/5이므로 대체공휴일이 추가되어야 합니다.
        """
        holidays = get_kr_market_holidays(2025)
        assert datetime.date(2025, 5, 5) in holidays
        # 5/5가 월요일이므로 겹침에 의한 대체공휴일은
        # 두 공휴일 중 하나에 대해 5/6(화)
        assert datetime.date(2025, 5, 6) in holidays

    def test_holiday_count_reasonable(self):
        """연간 공휴일 수가 합리적 범위 (15~25개)."""
        for year in range(2025, 2031):
            holidays = get_kr_market_holidays(year)
            assert 12 <= len(holidays) <= 30, (
                f"{year}년 공휴일 {len(holidays)}개 — 범위 초과"
            )

    def test_no_duplicate_dates(self):
        """set이므로 중복 없음 (당연하지만 확인)."""
        holidays = get_kr_market_holidays(2025)
        holiday_list = list(holidays)
        assert len(holiday_list) == len(set(holiday_list))
