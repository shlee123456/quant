"""
미국 주식시장 공휴일 캘린더

NYSE/NASDAQ 공휴일을 판별합니다.
고정 공휴일, 변동 공휴일, "observed" 규칙을 모두 지원합니다.
"""

import datetime
from dateutil.easter import easter


def _observed_date(dt: datetime.date) -> datetime.date:
    """
    "Observed" 규칙 적용:
    - 토요일에 해당하면 → 금요일 휴장
    - 일요일에 해당하면 → 월요일 휴장
    """
    weekday = dt.weekday()  # 0=Mon, 5=Sat, 6=Sun
    if weekday == 5:  # Saturday
        return dt - datetime.timedelta(days=1)
    elif weekday == 6:  # Sunday
        return dt + datetime.timedelta(days=1)
    return dt


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """
    특정 월의 n번째 특정 요일 날짜를 반환합니다.

    Args:
        year: 연도
        month: 월 (1-12)
        weekday: 요일 (0=월, 1=화, ..., 6=일)
        n: n번째 (1부터 시작)

    Returns:
        해당 날짜
    """
    first_day = datetime.date(year, month, 1)
    # 첫 번째 해당 요일까지의 오프셋
    offset = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + datetime.timedelta(days=offset)
    return first_occurrence + datetime.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> datetime.date:
    """
    특정 월의 마지막 특정 요일 날짜를 반환합니다.

    Args:
        year: 연도
        month: 월 (1-12)
        weekday: 요일 (0=월, 1=화, ..., 6=일)

    Returns:
        해당 날짜
    """
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    offset = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=offset)


def get_us_market_holidays(year: int) -> set:
    """
    지정된 연도의 미국 주식시장 공휴일 집합을 반환합니다.

    Args:
        year: 연도

    Returns:
        datetime.date 집합
    """
    holidays = set()

    # === 고정 공휴일 (observed 규칙 적용) ===

    # New Year's Day (1월 1일)
    holidays.add(_observed_date(datetime.date(year, 1, 1)))

    # Juneteenth (6월 19일)
    holidays.add(_observed_date(datetime.date(year, 6, 19)))

    # Independence Day (7월 4일)
    holidays.add(_observed_date(datetime.date(year, 7, 4)))

    # Christmas (12월 25일)
    holidays.add(_observed_date(datetime.date(year, 12, 25)))

    # === 변동 공휴일 ===

    # MLK Day (1월 셋째 월요일)
    holidays.add(_nth_weekday(year, 1, 0, 3))  # 0=Monday, 3rd

    # Presidents' Day (2월 셋째 월요일)
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Memorial Day (5월 마지막 월요일)
    holidays.add(_last_weekday(year, 5, 0))

    # Labor Day (9월 첫째 월요일)
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving (11월 넷째 목요일)
    holidays.add(_nth_weekday(year, 11, 3, 4))  # 3=Thursday, 4th

    # Good Friday (부활절 2일 전)
    easter_date = easter(year)
    good_friday = easter_date - datetime.timedelta(days=2)
    holidays.add(good_friday)

    return holidays


def is_us_market_holiday(date: datetime.date) -> bool:
    """
    주어진 날짜가 미국 주식시장 공휴일인지 확인합니다.

    Args:
        date: 확인할 날짜 (datetime.date 또는 datetime.datetime)

    Returns:
        공휴일이면 True, 아니면 False
    """
    if isinstance(date, datetime.datetime):
        date = date.date()

    holidays = get_us_market_holidays(date.year)

    # New Year's Day observed가 전년도 12/31에 해당할 수 있음
    # (1/1이 토요일이면 12/31 금요일이 observed)
    holidays |= get_us_market_holidays(date.year + 1)

    return date in holidays
