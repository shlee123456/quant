"""
Favorites Widget for Sidebar
Quick access to frequently traded stocks
"""

import logging
import streamlit as st
from typing import List, Optional, Dict, Any
from dashboard.stock_symbols import StockSymbolDB
from dashboard.kis_broker import get_kis_broker

logger = logging.getLogger(__name__)


def initialize_favorites():
    """Initialize favorites in session state"""
    if 'favorite_symbols' not in st.session_state:
        # Default favorites (can be customized)
        st.session_state.favorite_symbols = []


def add_to_favorites(symbol: str):
    """
    Add a symbol to favorites

    Args:
        symbol: Stock symbol to add
    """
    if 'favorite_symbols' not in st.session_state:
        st.session_state.favorite_symbols = []

    symbol = symbol.upper().strip()
    if symbol not in st.session_state.favorite_symbols:
        st.session_state.favorite_symbols.append(symbol)


def remove_from_favorites(symbol: str):
    """
    Remove a symbol from favorites

    Args:
        symbol: Stock symbol to remove
    """
    if 'favorite_symbols' not in st.session_state:
        return

    symbol = symbol.upper().strip()
    if symbol in st.session_state.favorite_symbols:
        st.session_state.favorite_symbols.remove(symbol)


def is_favorite(symbol: str) -> bool:
    """
    Check if a symbol is in favorites

    Args:
        symbol: Stock symbol to check

    Returns:
        True if symbol is in favorites
    """
    if 'favorite_symbols' not in st.session_state:
        return False

    return symbol.upper().strip() in st.session_state.favorite_symbols


def render_favorites_widget(lang: str = 'ko') -> None:
    """
    Render favorites widget in sidebar

    Args:
        lang: Language code ('ko' or 'en')
    """
    initialize_favorites()

    # Widget title
    title = "⭐ 즐겨찾기" if lang == 'ko' else "⭐ Favorites"
    st.sidebar.markdown(f"### {title}")

    # Add new favorite
    stock_db = StockSymbolDB()
    all_symbols = stock_db.get_all_symbols()

    # Create search box for adding favorites
    col1, col2 = st.sidebar.columns([3, 1])

    with col1:
        new_favorite = st.selectbox(
            label="종목 추가" if lang == 'ko' else "Add Stock",
            options=[""] + all_symbols,
            key="favorites_add_selectbox",
            label_visibility="collapsed"
        )

    with col2:
        if st.button("➕", key="add_favorite_btn", help="Add to favorites"):
            if new_favorite and new_favorite != "":
                add_to_favorites(new_favorite)
                st.rerun()

    # Display favorites
    favorites = st.session_state.get('favorite_symbols', [])

    if not favorites:
        st.sidebar.caption(
            "즐겨찾기가 비어있습니다" if lang == 'ko'
            else "No favorites yet"
        )
    else:
        # Show favorites with current price (if available)
        for symbol in favorites:
            render_favorite_item(symbol, stock_db, lang)

    st.sidebar.markdown("---")


def render_favorite_item(symbol: str, stock_db: StockSymbolDB, lang: str):
    """
    Render a single favorite item

    Args:
        symbol: Stock symbol
        stock_db: StockSymbolDB instance
        lang: Language code
    """
    # Get stock info
    stock_info = stock_db.get_by_symbol(symbol)

    if stock_info:
        stock_name = stock_info['name']
        # Truncate long names
        if len(stock_name) > 20:
            stock_name = stock_name[:17] + "..."
    else:
        stock_name = symbol

    # Create columns for symbol and remove button
    col1, col2 = st.sidebar.columns([4, 1])

    with col1:
        # Try to get current price if broker is available and market is stock
        price_text = ""
        if st.session_state.get('market_type') == 'stock':
            broker = get_kis_broker()
            if broker:
                try:
                    # Get ticker data
                    ticker = broker.fetch_ticker(symbol, overseas=True)
                    if ticker and 'last' in ticker:
                        price = ticker['last']
                        rate = ticker.get('rate', 0)

                        # Format price display
                        if rate >= 0:
                            price_text = f"${price:.2f} 🔴 +{rate:.2f}%"
                        else:
                            price_text = f"${price:.2f} 🔵 {rate:.2f}%"
                except (ConnectionError, TimeoutError, ValueError) as e:
                    logger.warning("즐겨찾기 시세 조회 실패 (%s): %s", symbol, e)
                except Exception as e:
                    logger.warning("즐겨찾기 시세 조회 중 예상치 못한 오류 (%s): %s", symbol, e)

        # Display symbol and price
        if price_text:
            st.markdown(f"**{symbol}**")
            st.caption(price_text)
        else:
            st.markdown(f"**{symbol}**")
            st.caption(stock_name)

    with col2:
        # Remove button
        if st.button("🗑️", key=f"remove_{symbol}", help="Remove from favorites"):
            remove_from_favorites(symbol)
            st.rerun()


def get_favorites_presets(lang: str = 'ko') -> Dict[str, List[str]]:
    """
    Get preset favorites lists

    Args:
        lang: Language code

    Returns:
        Dictionary of preset names to symbol lists
    """
    stock_db = StockSymbolDB()
    presets = stock_db.get_all_presets()

    # Translate preset names if Korean
    if lang == 'ko':
        translated = {
            'FAANG': 'FAANG',
            'Magnificent 7': '매그니피센트 7',
            'Tech Giants': '테크 거대기업',
            'Semiconductors': '반도체',
            'Dividend Aristocrats': '배당 귀족주',
            'Finance Leaders': '금융 리더',
            'Healthcare Leaders': '헬스케어 리더',
            'Index ETFs': '인덱스 ETF',
            'Sector ETFs': '섹터 ETF'
        }
        return {translated.get(k, k): v for k, v in presets.items()}
    else:
        return presets


def load_favorites_preset(preset_name: str):
    """
    Load a favorites preset

    Args:
        preset_name: Name of the preset to load
    """
    stock_db = StockSymbolDB()
    symbols = stock_db.get_preset(preset_name)

    if symbols:
        # Replace current favorites with preset
        st.session_state.favorite_symbols = symbols.copy()


def clear_favorites():
    """Clear all favorites"""
    st.session_state.favorite_symbols = []
