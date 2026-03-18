"""미국 시장 시간 유틸리티 — DST 자동 감지.

미국 정규장은 항상 ET(Eastern Time) 09:30~16:00.
DST(서머타임) 여부에 따라 KST 변환 결과가 달라짐:
- EST (11~3월): 09:30 EST = 23:30 KST, 16:00 EST = 06:00 KST
- EDT (3~11월): 09:30 EDT = 22:30 KST, 16:00 EDT = 05:00 KST
"""

from datetime import datetime, date, time, timedelta
from typing import Any, Dict

import pytz

ET = pytz.timezone('US/Eastern')
KST = pytz.timezone('Asia/Seoul')

# 미국 정규장 시간 (ET 기준, 항상 고정)
US_MARKET_OPEN_ET = time(9, 30)
US_MARKET_CLOSE_ET = time(16, 0)


def is_dst(dt: datetime = None) -> bool:
    """현재 미국 동부시간이 서머타임(EDT)인지 확인."""
    if dt is None:
        dt = datetime.now(ET)
    elif dt.tzinfo is None:
        dt = ET.localize(dt)
    return bool(dt.dst())


def get_market_hours_kst(target_date: date = None) -> Dict[str, Any]:
    """미국 시장 개장/마감 시각을 KST로 변환.

    Args:
        target_date: 대상 날짜 (None이면 오늘 ET 기준)

    Returns:
        {
            'open': {'hour': int, 'minute': int},
            'close': {'hour': int, 'minute': int},
            'close_5m': {'hour': int, 'minute': int},
            'close_10m': {'hour': int, 'minute': int},
            'is_dst': bool,
            'et_label': 'EDT' or 'EST',
        }
    """
    if target_date is None:
        target_date = datetime.now(ET).date()

    open_et = ET.localize(datetime.combine(target_date, US_MARKET_OPEN_ET))
    close_et = ET.localize(datetime.combine(target_date, US_MARKET_CLOSE_ET))

    open_kst = open_et.astimezone(KST)
    close_kst = close_et.astimezone(KST)

    dst = is_dst(open_et)

    return {
        'open': {'hour': open_kst.hour, 'minute': open_kst.minute},
        'close': {'hour': close_kst.hour, 'minute': close_kst.minute},
        'close_5m': {
            'hour': (close_kst + timedelta(minutes=5)).hour,
            'minute': (close_kst + timedelta(minutes=5)).minute,
        },
        'close_10m': {
            'hour': (close_kst + timedelta(minutes=10)).hour,
            'minute': (close_kst + timedelta(minutes=10)).minute,
        },
        'is_dst': dst,
        'et_label': 'EDT' if dst else 'EST',
    }


def get_schedule_description() -> str:
    """현재 DST 상태 기반 스케줄 설명 문자열."""
    h = get_market_hours_kst()
    label = h['et_label']
    return (
        f"  {h['open']['hour']:02d}:{h['open']['minute']:02d} KST "
        f"(09:30 {label}) - 페이퍼 트레이딩 시작\n"
        f"  {h['close']['hour']:02d}:{h['close']['minute']:02d} KST "
        f"(16:00 {label}) - 트레이딩 중지 및 리포트\n"
        f"  {h['close_10m']['hour']:02d}:{h['close_10m']['minute']:02d} KST "
        f"- 시장 분석 + 노션 작성"
    )
