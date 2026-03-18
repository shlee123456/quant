"""
한국 주식시장 공휴일 캘린더

KRX(한국거래소) 공휴일을 판별합니다.
고정 공휴일, 음력 변동 공휴일, 대체공휴일법을 모두 지원합니다.

외부 패키지 의존 없이 2025-2030년 음력 공휴일 날짜를 하드코딩합니다.
"""

import datetime
from typing import Dict, List, Set, Tuple


# ─── 음력 공휴일 하드코딩 (2025-2030) ───

# 설날: 음력 1/1 기준 (±1일 포함하여 3일 연휴)
_LUNAR_NEW_YEAR: Dict[int, Tuple[int, int]] = {
    2025: (1, 29),   # 2025-01-29 (음력 1/1)
    2026: (2, 17),   # 2026-02-17
    2027: (2, 7),    # 2027-02-07
    2028: (1, 27),   # 2028-01-27
    2029: (2, 13),   # 2029-02-13
    2030: (2, 3),    # 2030-02-03
}

# 부처님오신날: 음력 4/8
_BUDDHAS_BIRTHDAY: Dict[int, Tuple[int, int]] = {
    2025: (5, 5),    # 2025-05-05
    2026: (5, 24),   # 2026-05-24
    2027: (5, 13),   # 2027-05-13
    2028: (5, 2),    # 2028-05-02
    2029: (5, 20),   # 2029-05-20
    2030: (5, 9),    # 2030-05-09
}

# 추석: 음력 8/15 기준 (±1일 포함하여 3일 연휴)
_CHUSEOK: Dict[int, Tuple[int, int]] = {
    2025: (10, 6),   # 2025-10-06 (음력 8/15)
    2026: (9, 25),   # 2026-09-25
    2027: (9, 15),   # 2027-09-15
    2028: (10, 3),   # 2028-10-03
    2029: (9, 22),   # 2029-09-22
    2030: (9, 12),   # 2030-09-12
}

# 대체공휴일 적용 대상 공휴일 이름
_SUBSTITUTE_ELIGIBLE = frozenset({
    '신정', '삼일절', '어린이날', '광복절', '개천절', '한글날', '크리스마스',
    '설날', '부처님오신날', '추석',
})


def _substitute_holiday(
    holiday_date: datetime.date,
    all_holidays: Set[datetime.date],
) -> datetime.date:
    """
    대체공휴일법 적용.

    공휴일이 토요일 또는 일요일과 겹치면 그 다음 첫 번째 비공휴일 평일을 대체공휴일로 지정합니다.
    여러 공휴일이 연속으로 겹칠 경우에도 겹치지 않는 첫 평일을 찾습니다.

    Args:
        holiday_date: 원래 공휴일 날짜
        all_holidays: 이미 등록된 모든 공휴일 집합

    Returns:
        대체공휴일 날짜 (주말이 아닌 경우 원래 날짜 그대로)
    """
    weekday = holiday_date.weekday()
    if weekday < 5:
        # 평일이면 대체 불필요
        return holiday_date

    # 주말과 겹침 -> 다음 월요일부터 탐색
    candidate = holiday_date + datetime.timedelta(days=(7 - weekday))
    while candidate in all_holidays or candidate.weekday() >= 5:
        candidate += datetime.timedelta(days=1)
    return candidate


def get_kr_market_holidays(year: int) -> Set[datetime.date]:
    """
    지정된 연도의 한국 주식시장 공휴일 집합을 반환합니다.

    고정 공휴일, 음력 변동 공휴일, 대체공휴일을 모두 포함합니다.
    2025-2030년 범위 밖의 연도는 고정 공휴일만 반환합니다.

    Args:
        year: 연도

    Returns:
        datetime.date 집합
    """
    holidays: Set[datetime.date] = set()

    # === 고정 공휴일 ===
    fixed_holidays: List[Tuple[str, datetime.date]] = [
        ('신정', datetime.date(year, 1, 1)),
        ('삼일절', datetime.date(year, 3, 1)),
        ('어린이날', datetime.date(year, 5, 5)),
        ('현충일', datetime.date(year, 6, 6)),
        ('광복절', datetime.date(year, 8, 15)),
        ('개천절', datetime.date(year, 10, 3)),
        ('한글날', datetime.date(year, 10, 9)),
        ('크리스마스', datetime.date(year, 12, 25)),
    ]

    for _, dt in fixed_holidays:
        holidays.add(dt)

    # === 음력 변동 공휴일 ===
    lunar_holidays: List[Tuple[str, datetime.date]] = []

    # 설날 (3일 연휴: 전날, 당일, 다음날)
    if year in _LUNAR_NEW_YEAR:
        month, day = _LUNAR_NEW_YEAR[year]
        seollal = datetime.date(year, month, day)
        lunar_holidays.append(('설날', seollal - datetime.timedelta(days=1)))
        lunar_holidays.append(('설날', seollal))
        lunar_holidays.append(('설날', seollal + datetime.timedelta(days=1)))

    # 부처님오신날
    if year in _BUDDHAS_BIRTHDAY:
        month, day = _BUDDHAS_BIRTHDAY[year]
        lunar_holidays.append(('부처님오신날', datetime.date(year, month, day)))

    # 추석 (3일 연휴: 전날, 당일, 다음날)
    if year in _CHUSEOK:
        month, day = _CHUSEOK[year]
        chuseok = datetime.date(year, month, day)
        lunar_holidays.append(('추석', chuseok - datetime.timedelta(days=1)))
        lunar_holidays.append(('추석', chuseok))
        lunar_holidays.append(('추석', chuseok + datetime.timedelta(days=1)))

    for _, dt in lunar_holidays:
        holidays.add(dt)

    # === 대체공휴일법 적용 ===
    # 1) 주말과 겹치는 공휴일에 대해 대체공휴일 추가
    # 2) 서로 다른 공휴일이 같은 날짜에 겹치는 경우에도 대체공휴일 추가
    all_named: List[Tuple[str, datetime.date]] = fixed_holidays + lunar_holidays

    for name, dt in all_named:
        if name in _SUBSTITUTE_ELIGIBLE:
            substitute = _substitute_holiday(dt, holidays)
            if substitute != dt:
                holidays.add(substitute)

    # 공휴일 간 겹침 처리: 같은 날짜에 서로 다른 이름의 공휴일이 있으면
    # 겹치는 수만큼 대체공휴일 추가 (이미 주말 대체가 된 날은 제외)
    from collections import Counter
    date_counts: Counter = Counter()
    for name, dt in all_named:
        if name in _SUBSTITUTE_ELIGIBLE:
            date_counts[dt] += 1

    for dt, count in date_counts.items():
        if count > 1:
            # count - 1개의 대체공휴일 필요 (1개는 원래 날짜에 유지)
            for _ in range(count - 1):
                substitute = _substitute_holiday(dt, holidays)
                if substitute == dt:
                    # 평일이면 다음 평일 찾기
                    candidate = dt + datetime.timedelta(days=1)
                    while candidate in holidays or candidate.weekday() >= 5:
                        candidate += datetime.timedelta(days=1)
                    substitute = candidate
                holidays.add(substitute)

    return holidays


def is_kr_market_holiday(date: datetime.date) -> bool:
    """
    주어진 날짜가 한국 주식시장 공휴일인지 확인합니다.

    주말(토, 일)도 휴장일로 판별합니다.

    Args:
        date: 확인할 날짜 (datetime.date 또는 datetime.datetime)

    Returns:
        공휴일 또는 주말이면 True, 아니면 False
    """
    if isinstance(date, datetime.datetime):
        date = date.date()

    # 주말 체크
    if date.weekday() >= 5:
        return True

    holidays = get_kr_market_holidays(date.year)

    # 설날 연휴가 전년도 12월에 걸칠 수 있으므로 다음 해도 확인
    holidays |= get_kr_market_holidays(date.year + 1)

    return date in holidays
