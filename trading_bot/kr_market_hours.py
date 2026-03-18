"""한국 시장 시간 유틸리티 -- DST 없음, KST 고정.

한국 정규장은 항상 KST 09:00~15:30.
미국과 달리 DST(서머타임)가 없으므로 시간이 항상 고정됩니다.
"""

from datetime import datetime, time
from typing import Dict

import pytz

KST = pytz.timezone('Asia/Seoul')

# 한국 정규장 시간 (KST 기준, 항상 고정)
KR_MARKET_OPEN_KST = time(9, 0)
KR_MARKET_CLOSE_KST = time(15, 30)


def get_kr_market_hours() -> Dict[str, Dict[str, int]]:
    """한국 시장 시간 반환 (KST 기준, DST 없음).

    Returns:
        {
            'market_open': {'hour': 9, 'minute': 0},
            'market_close': {'hour': 15, 'minute': 30},
            'analysis_time': {'hour': 15, 'minute': 50},   # 마감 20분 후
            'notion_time': {'hour': 16, 'minute': 0},       # 마감 30분 후
        }
    """
    return {
        'market_open': {'hour': 9, 'minute': 0},
        'market_close': {'hour': 15, 'minute': 30},
        'analysis_time': {'hour': 15, 'minute': 50},
        'notion_time': {'hour': 16, 'minute': 0},
    }


def get_kr_schedule_description() -> str:
    """한국 시장 스케줄 설명 문자열."""
    h = get_kr_market_hours()
    return (
        f"  {h['market_open']['hour']:02d}:{h['market_open']['minute']:02d} KST "
        f"- 한국 정규장 개장\n"
        f"  {h['market_close']['hour']:02d}:{h['market_close']['minute']:02d} KST "
        f"- 한국 정규장 마감\n"
        f"  {h['analysis_time']['hour']:02d}:{h['analysis_time']['minute']:02d} KST "
        f"- 한국 시장 분석 + JSON 저장"
    )


def is_kr_market_open() -> bool:
    """현재 한국 정규장이 열려있는지 확인.

    Returns:
        장 열려있으면 True, 닫혀있으면 False
    """
    now = datetime.now(KST)
    current_time = now.time()

    # 주말 체크
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    return KR_MARKET_OPEN_KST <= current_time <= KR_MARKET_CLOSE_KST
