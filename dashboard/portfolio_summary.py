"""
Portfolio Summary Widget for Sidebar
Displays real-time portfolio status when paper trading is active
"""

import logging
import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def render_portfolio_summary(lang: str = 'ko') -> None:
    """
    Render portfolio summary widget in sidebar

    Args:
        lang: Language code ('ko' or 'en')
    """
    # Check if paper trading is active
    if not st.session_state.get('paper_trading_active', False):
        return

    trader = st.session_state.get('paper_trader')
    if trader is None:
        return

    # Widget title
    title = "포트폴리오 요약" if lang == 'ko' else "Portfolio Summary"
    st.sidebar.markdown(f"### {title}")

    try:
        # Get current prices for portfolio value calculation
        broker = st.session_state.get('broker')
        current_prices = {}

        if broker:
            for symbol in trader.positions.keys():
                try:
                    ticker = broker.fetch_ticker(symbol, overseas=True)
                    if ticker and 'last' in ticker:
                        current_prices[symbol] = ticker['last']
                except (ConnectionError, TimeoutError, ValueError) as e:
                    logger.warning("포트폴리오 시세 조회 실패 (%s): %s", symbol, e)
                except Exception as e:
                    logger.warning("포트폴리오 시세 조회 중 예상치 못한 오류 (%s): %s", symbol, e)

        # Get portfolio metrics
        total_value = trader.get_portfolio_value(current_prices)
        cash_balance = trader.capital  # PaperTrader uses 'capital', not 'cash'
        initial_capital = trader.initial_capital

        # Calculate returns
        total_return = ((total_value - initial_capital) / initial_capital) * 100

        # Display metrics
        col1, col2 = st.sidebar.columns(2)

        with col1:
            st.metric(
                label="총 자산" if lang == 'ko' else "Total Value",
                value=f"${total_value:,.0f}",
                delta=f"{total_return:+.2f}%"
            )

        with col2:
            st.metric(
                label="현금" if lang == 'ko' else "Cash",
                value=f"${cash_balance:,.0f}"
            )

        # Position count
        position_count = len([v for v in trader.positions.values() if v > 0])
        st.sidebar.caption(
            f"보유 종목: {position_count}개" if lang == 'ko'
            else f"Positions: {position_count}"
        )

        # Session info
        if hasattr(trader, 'session_id'):
            st.sidebar.caption(
                f"세션: {trader.session_id[:8]}..." if lang == 'ko'
                else f"Session: {trader.session_id[:8]}..."
            )

    except Exception as e:
        st.sidebar.error(
            f"포트폴리오 정보를 불러올 수 없습니다: {str(e)}" if lang == 'ko'
            else f"Failed to load portfolio: {str(e)}"
        )

    st.sidebar.markdown("---")


def get_portfolio_details(trader: Any, current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Get detailed portfolio information

    Args:
        trader: PaperTrader instance
        current_prices: Optional dict of symbol to current price

    Returns:
        Dictionary with portfolio details
    """
    if trader is None:
        return {}

    if current_prices is None:
        current_prices = {}

    total_value = trader.get_portfolio_value(current_prices)
    cash_balance = trader.capital  # PaperTrader uses 'capital', not 'cash'
    initial_capital = trader.initial_capital

    # Calculate metrics
    total_return = ((total_value - initial_capital) / initial_capital) * 100
    positions_value = total_value - cash_balance
    cash_ratio = (cash_balance / total_value) * 100 if total_value > 0 else 0

    return {
        'total_value': total_value,
        'cash_balance': cash_balance,
        'initial_capital': initial_capital,
        'total_return': total_return,
        'positions_value': positions_value,
        'cash_ratio': cash_ratio,
        'position_count': len([v for v in trader.positions.values() if v > 0])
    }
