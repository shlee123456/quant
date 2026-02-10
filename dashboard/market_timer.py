"""
Market Hours & Timer Widget for Sidebar
Displays current market status and countdown to next open/close
"""

import streamlit as st
from datetime import datetime, timedelta
from dashboard.market_hours import MarketHours
from typing import Tuple


def render_market_timer(lang: str = 'ko') -> None:
    """
    Render market timer widget in sidebar

    Args:
        lang: Language code ('ko' or 'en')
    """
    # Widget title
    title = "🕐 시장 시간" if lang == 'ko' else "🕐 Market Hours"
    st.sidebar.markdown(f"### {title}")

    try:
        market_hours = MarketHours()
        status_info = market_hours.get_market_status()

        # Display current market status
        status_text, status_color = market_hours.format_status_message(lang)
        st.sidebar.markdown(f"**{status_text}**")

        # Calculate time until next event
        current_time = status_info['current_time_est']
        status = status_info['status']

        if status == 'closed':
            # Show time until next open
            next_open = status_info['next_open']
            time_diff = next_open - current_time
            label = "다음 개장까지" if lang == 'ko' else "Until Market Opens"
        else:
            # Show time until next close
            next_close = status_info['next_close']
            time_diff = next_close - current_time

            if status == 'pre_market':
                label = "정규장 개장까지" if lang == 'ko' else "Until Regular Hours"
            elif status == 'regular':
                label = "정규장 마감까지" if lang == 'ko' else "Until Market Closes"
            elif status == 'after_hours':
                label = "애프터아워 종료까지" if lang == 'ko' else "Until After Hours End"
            else:
                label = "다음 이벤트까지" if lang == 'ko' else "Until Next Event"

        # Format countdown
        countdown = format_timedelta(time_diff, lang)
        st.sidebar.markdown(f"⏱️ **{label}**: {countdown}")

        # Show market hours info (collapsible)
        with st.sidebar.expander("📅 " + ("거래 시간표" if lang == 'ko' else "Trading Hours")):
            hours_display = market_hours.get_market_hours_display()

            if lang == 'ko':
                st.markdown(f"""
                **프리마켓**
                - {hours_display['pre_market_est']}
                - {hours_display['pre_market_kst']}

                **정규장**
                - {hours_display['regular_est']}
                - {hours_display['regular_kst']}

                **애프터아워**
                - {hours_display['after_hours_est']}
                - {hours_display['after_hours_kst']}
                """)
            else:
                st.markdown(f"""
                **Pre-Market**
                - {hours_display['pre_market_est']}
                - {hours_display['pre_market_kst']}

                **Regular Hours**
                - {hours_display['regular_est']}
                - {hours_display['regular_kst']}

                **After Hours**
                - {hours_display['after_hours_est']}
                - {hours_display['after_hours_kst']}
                """)

    except Exception as e:
        st.sidebar.error(
            f"시장 시간을 불러올 수 없습니다: {str(e)}" if lang == 'ko'
            else f"Failed to load market hours: {str(e)}"
        )

    st.sidebar.markdown("---")


def format_timedelta(td: timedelta, lang: str = 'ko') -> str:
    """
    Format timedelta for display

    Args:
        td: timedelta object
        lang: Language code ('ko' or 'en')

    Returns:
        Formatted string (e.g., "5시간 30분" or "5h 30m")
    """
    total_seconds = int(td.total_seconds())

    # Handle negative timedelta (should not happen, but just in case)
    if total_seconds < 0:
        return "00:00:00"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if lang == 'ko':
        if hours > 0:
            return f"{hours}시간 {minutes}분"
        elif minutes > 0:
            return f"{minutes}분 {seconds}초"
        else:
            return f"{seconds}초"
    else:
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


def get_market_status_emoji(status: str) -> str:
    """
    Get emoji for market status

    Args:
        status: Market status ('pre_market', 'regular', 'after_hours', 'closed')

    Returns:
        Emoji string
    """
    emoji_map = {
        'pre_market': '🟡',
        'regular': '🟢',
        'after_hours': '🟠',
        'closed': '🔴'
    }
    return emoji_map.get(status, '❓')
