"""
Quant Trading Lab - 메인 대시보드 애플리케이션

라우팅 전용 파일: 각 탭의 UI 로직은 dashboard/pages/ 모듈에 분리되어 있습니다.
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.config import Config
from trading_bot.database import TradingDatabase
from dashboard.translations import get_text
from dashboard.portfolio_summary import render_portfolio_summary
from dashboard.market_timer import render_market_timer
from dashboard.favorites import render_favorites_widget
from dashboard.session_manager import render_session_manager

# Page modules
from dashboard.tabs.paper_trading import paper_trading_tab
from dashboard.tabs.backtest import backtest_tab
from dashboard.tabs.strategy_comparison import paper_trading_comparison_tab, strategy_comparison_tab
from dashboard.tabs.realtime_quotes import realtime_quotes_tab
from dashboard.tabs.scheduler import scheduler_tab


# Page configuration
st.set_page_config(
    page_title="Quant Trading Lab",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-container {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .positive {
        color: #00c853;
    }
    .negative {
        color: #ff1744;
    }
    .strategy-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #1f77b4;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables"""
    # Recover zombie sessions on first load
    if 'zombie_recovered' not in st.session_state:
        try:
            db = TradingDatabase()
            recovered = db.recover_zombie_sessions()
            if recovered > 0:
                st.toast(f"비정상 종료된 세션 {recovered}개를 감지하여 'interrupted' 처리했습니다.")
        except Exception:
            pass
        st.session_state.zombie_recovered = True

    if 'config' not in st.session_state:
        st.session_state.config = Config()
    if 'data_handler' not in st.session_state:
        st.session_state.data_handler = None
    if 'selected_strategy' not in st.session_state:
        st.session_state.selected_strategy = 'Moving Average Crossover'
    if 'strategy_params' not in st.session_state:
        st.session_state.strategy_params = {}
    if 'strategy_instance' not in st.session_state:
        st.session_state.strategy_instance = None
    if 'paper_trader' not in st.session_state:
        st.session_state.paper_trader = None
    if 'backtest_results' not in st.session_state:
        st.session_state.backtest_results = None
    if 'comparison_results' not in st.session_state:
        st.session_state.comparison_results = None
    if 'live_mode' not in st.session_state:
        st.session_state.live_mode = False
    if 'use_simulation' not in st.session_state:
        st.session_state.use_simulation = False
    if 'language' not in st.session_state:
        st.session_state.language = 'ko'  # Default to Korean
    if 'market_type' not in st.session_state:
        st.session_state.market_type = 'stock'  # Default to Foreign Stocks
    if 'paper_trading_active' not in st.session_state:
        st.session_state.paper_trading_active = False
    if 'enable_verification' not in st.session_state:
        st.session_state.enable_verification = True


def sidebar_config():
    """Render configuration sidebar"""
    lang = st.session_state.language

    # ============================================================================
    # SIMPLIFIED SIDEBAR - Only Language and Quick Info
    # ============================================================================
    st.sidebar.title("설정" if lang == 'ko' else "Settings")

    # Language Selection
    st.sidebar.subheader(get_text('language', lang))

    previous_lang = st.session_state.language
    language = st.sidebar.selectbox(
        "Language Selection",
        options=['한국어', 'English'],
        index=0 if st.session_state.language == 'ko' else 1,
        label_visibility="collapsed",
        key="language_selector"
    )

    new_lang = 'ko' if language == '한국어' else 'en'

    # Trigger rerun if language changed
    if new_lang != previous_lang:
        st.session_state.language = new_lang
        st.rerun()

    lang = st.session_state.language  # Update lang after selection

    st.sidebar.markdown("---")

    # ============================================================================
    # CONVENIENCE WIDGETS
    # ============================================================================

    # 1. Portfolio Summary (only when paper trading is active)
    render_portfolio_summary(lang)

    # 2. Market Hours & Timer (for stock market)
    if st.session_state.get('market_type') == 'stock':
        render_market_timer(lang)

    # 3. Favorites (quick access to frequently traded stocks)
    if st.session_state.get('market_type') == 'stock':
        render_favorites_widget(lang)

    # Minimal footer caption
    if lang == 'ko':
        st.sidebar.caption("각 탭에서 필요한 설정을 직접 구성할 수 있습니다.")
    else:
        st.sidebar.caption("Configure settings in each tab as needed.")

    # Initialize market type if not set
    if 'market_type' not in st.session_state:
        st.session_state.market_type = 'stock'

    # Initialize use_simulation if not set
    if 'use_simulation' not in st.session_state:
        st.session_state.use_simulation = False


def main():
    """Main application"""
    init_session_state()

    lang = st.session_state.language

    # Title
    st.title(get_text('page_title', lang))
    st.markdown(f"**{get_text('page_subtitle', lang)}**")
    st.markdown("---")

    # Sidebar
    sidebar_config()

    # Main tabs - ordered by trading workflow
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        get_text('tab_paper', lang),           # Main: Paper Trading
        get_text('tab_quotes', lang),          # Market data
        get_text('tab_backtest', lang),        # Strategy validation
        get_text('tab_analysis', lang),        # Performance analysis
        get_text('tab_scheduler', lang),       # Automation
    ])

    with tab1:
        paper_trading_tab()

    with tab2:
        realtime_quotes_tab()

    with tab3:
        backtest_tab()

    with tab4:
        # Combined tab: Strategy Comparison + Session Comparison
        st.header(get_text('tab_analysis', lang))

        comparison_type = st.radio(
            "비교 유형 선택" if lang == 'ko' else "Comparison Type",
            ["세션 비교 (Paper Trading)", "전략 비교 (시뮬레이션)"],
            horizontal=True,
            help="Paper Trading 세션을 비교하거나, 시뮬레이션 데이터로 여러 전략을 비교할 수 있습니다"
        )

        st.markdown("---")

        if comparison_type == "세션 비교 (Paper Trading)":
            paper_trading_comparison_tab()
        else:
            strategy_comparison_tab()

    with tab5:
        scheduler_tab()

    # Footer
    st.markdown("---")
    st.markdown(
        f"""
        <div style='text-align: center; color: #666;'>
        <small>{get_text('footer', lang)}</small>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
