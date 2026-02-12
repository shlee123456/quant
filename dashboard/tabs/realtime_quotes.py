"""
실시간 시세 탭 - 미국 주식 실시간 시세 조회 및 차트 표시
"""
import streamlit as st
import pandas as pd
import time

from dashboard.translations import get_text
from dashboard.stock_symbols import StockSymbolDB


def realtime_quotes_tab():
    """Real-time stock quotes interface"""
    lang = st.session_state.language

    st.header(get_text('tab_quotes', lang))

    # Initialize stock symbol database
    stock_db = StockSymbolDB()

    # Initialize session state for selected symbol
    if 'selected_quote_symbol' not in st.session_state:
        st.session_state.selected_quote_symbol = 'AAPL'  # Default to Apple

    # Initialize session state for auto-refresh
    if 'auto_refresh_enabled' not in st.session_state:
        st.session_state.auto_refresh_enabled = False

    if 'last_refresh_time' not in st.session_state:
        st.session_state.last_refresh_time = None

    # Stock selection UI
    st.subheader(get_text('select_stock', lang))

    col1, col2 = st.columns([2, 1])

    with col1:
        # Selection method: List or Direct Input
        selection_method = st.radio(
            "종목 선택 방법" if lang == 'ko' else "Selection Method",
            ["목록에서 선택" if lang == 'ko' else "Select from List",
             "직접 입력 (모든 미국 주식)" if lang == 'ko' else "Direct Input (All US Stocks)"],
            horizontal=True,
            key='quote_selection_method'
        )

        # Get all stocks for dropdown
        all_stocks = stock_db.stocks

        # Create display format: "SYMBOL - Company Name"
        stock_options = [f"{stock['symbol']} - {stock['name']}" for stock in all_stocks]
        stock_symbols = [stock['symbol'] for stock in all_stocks]

        if "목록" in selection_method or "Select from" in selection_method:
            # List selection mode
            # Find current selection index
            try:
                default_idx = stock_symbols.index(st.session_state.selected_quote_symbol)
            except ValueError:
                default_idx = 0

            # Stock selectbox
            selected_option = st.selectbox(
                get_text('stock_symbol', lang),
                stock_options,
                index=default_idx,
                help=get_text('select_stock_help', lang)
            )

            # Extract symbol from selection
            selected_symbol = selected_option.split(' - ')[0]

        else:
            # Direct input mode (yfinance)
            st.info("PLTR, SHOP, COIN, UBER, ABNB, RBLX 등 모든 미국 주식 심볼을 입력하세요." if lang == 'ko' else "Enter any US stock symbol: PLTR, SHOP, COIN, UBER, ABNB, RBLX, etc.")

            # Text input for custom symbol
            custom_symbol = st.text_input(
                "종목 심볼 입력" if lang == 'ko' else "Enter Symbol",
                value=st.session_state.get('selected_quote_symbol', 'PLTR'),
                placeholder="예: PLTR, SHOP, COIN" if lang == 'ko' else "e.g., PLTR, SHOP, COIN",
                help="미국 주식 심볼을 입력하세요 (대소문자 무관)" if lang == 'ko' else "Enter US stock symbol (case insensitive)",
                key='custom_quote_symbol'
            ).strip().upper()

            # Validate symbol
            if custom_symbol:
                from dashboard.yfinance_helper import validate_symbol

                with st.spinner(f"'{custom_symbol}' 종목 확인 중..." if lang == 'ko' else f"Validating '{custom_symbol}'..."):
                    is_valid = validate_symbol(custom_symbol)

                if is_valid:
                    selected_symbol = custom_symbol
                    st.success(f"✅ {selected_symbol} " + ("종목을 찾았습니다!" if lang == 'ko' else "found!"))
                else:
                    st.error(f"❌ '{custom_symbol}' " + ("종목을 찾을 수 없습니다. 다른 심볼을 입력하세요." if lang == 'ko' else "not found. Please enter a valid symbol."))
                    selected_symbol = st.session_state.get('selected_quote_symbol', 'AAPL')
            else:
                selected_symbol = st.session_state.get('selected_quote_symbol', 'AAPL')

        # Update session state
        st.session_state.selected_quote_symbol = selected_symbol

    with col2:
        # Display selected stock info
        stock_info = stock_db.get_by_symbol(selected_symbol)
        if stock_info:
            st.info(f"**{get_text('sector', lang)}:** {stock_info['sector']}\n\n"
                   f"**{get_text('industry', lang)}:** {stock_info['industry']}")

    # Display selected symbol
    st.success(f"{get_text('selected_symbol', lang)}: **{selected_symbol}** - {stock_info['name'] if stock_info else ''}")

    # Auto-refresh controls (US-007)
    st.divider()

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        # Auto-refresh toggle checkbox
        auto_refresh = st.checkbox(
            get_text('enable_auto_refresh', lang),
            value=st.session_state.auto_refresh_enabled,
            help=get_text('auto_refresh_help', lang),
            key='auto_refresh_checkbox'
        )
        st.session_state.auto_refresh_enabled = auto_refresh

    with col2:
        # Manual refresh button
        manual_refresh = st.button(
            get_text('refresh_now', lang),
            type='primary',
            use_container_width=True
        )

    with col3:
        # Display auto-refresh status and countdown
        if st.session_state.auto_refresh_enabled:
            import datetime

            current_time = time.time()

            # Initialize last refresh time if needed
            if st.session_state.last_refresh_time is None or manual_refresh:
                st.session_state.last_refresh_time = current_time

            # Calculate elapsed time since last refresh
            elapsed = current_time - st.session_state.last_refresh_time
            refresh_interval = 60  # 60 seconds
            remaining = max(0, refresh_interval - int(elapsed))

            # Display countdown
            if remaining > 0:
                st.info(f"{get_text('next_refresh_in', lang)} **{remaining}s**")
            else:
                st.info(get_text('refreshing_now', lang))

            # Auto-refresh logic
            if elapsed >= refresh_interval:
                st.session_state.last_refresh_time = current_time
                time.sleep(0.5)  # Brief pause for visual feedback
                st.rerun()

            # Schedule next update
            time.sleep(1)
            st.rerun()
        else:
            st.info(get_text('auto_refresh_disabled', lang))

    # Reset last refresh time if manually refreshed
    if manual_refresh:
        st.session_state.last_refresh_time = time.time()

    # Real-time quote display (US-005)
    st.divider()
    st.subheader(get_text('current_price', lang))

    # Try KIS broker first, fallback to yfinance
    ticker = None
    data_source = None

    # Import helpers
    from dashboard.kis_broker import get_kis_broker
    from dashboard.yfinance_helper import fetch_ticker_yfinance

    # Try KIS broker first (for list selection)
    if "목록" in selection_method or "Select from" in selection_method:
        broker = get_kis_broker()

        if broker is not None:
            try:
                with st.spinner(get_text('fetching_quote', lang)):
                    ticker = broker.fetch_ticker(selected_symbol, overseas=True, market='NASDAQ')
                    data_source = "KIS API"
            except Exception as e:
                st.warning(f"⚠️ KIS API 조회 실패, yfinance로 시도합니다..." if lang == 'ko' else f"⚠️ KIS API failed, trying yfinance...")
                ticker = None

    # Fallback to yfinance or Direct input mode
    if ticker is None:
        try:
            with st.spinner(("yfinance로 조회 중..." if lang == 'ko' else "Fetching from yfinance...") if data_source is None else get_text('fetching_quote', lang)):
                ticker = fetch_ticker_yfinance(selected_symbol)
                data_source = "Yahoo Finance (yfinance)"

                if ticker is None:
                    st.error(f"❌ '{selected_symbol}' " + ("시세를 조회할 수 없습니다." if lang == 'ko' else "quote not available."))
                    return

        except Exception as e:
            st.error(f"❌ " + ("시세 조회 실패:" if lang == 'ko' else "Quote fetch failed:") + f" {str(e)}")
            return

    # Show data source
    if data_source:
        st.caption(("데이터 소스:" if lang == 'ko' else "Data source:") + f" {data_source}")

    # Display metrics in columns
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        # Current price with change rate
        change_rate = ticker.get('rate', 0.0)
        delta_color = "normal" if change_rate >= 0 else "inverse"
        st.metric(
            label=get_text('current_price', lang),
            value=f"${ticker['last']:.2f}",
            delta=f"{change_rate:+.2f}%",
            delta_color=delta_color
        )

    with col2:
        st.metric(
            label=get_text('open_price', lang),
            value=f"${ticker['open']:.2f}"
        )

    with col3:
        st.metric(
            label=get_text('high_price', lang),
            value=f"${ticker['high']:.2f}"
        )

    with col4:
        st.metric(
            label=get_text('low_price', lang),
            value=f"${ticker['low']:.2f}"
        )

    with col5:
        # Format volume with commas
        volume = ticker.get('volume', 0)
        st.metric(
            label=get_text('volume', lang),
            value=f"{int(volume):,}"
        )

    # Additional info: Change amount
    change_amount = ticker.get('change', 0.0)
    change_sign = "+" if change_amount >= 0 else ""

    st.info(f"{get_text('change_amount', lang)}: {change_sign}${change_amount:.2f} ({change_rate:+.2f}%)")

    # OHLCV Chart (US-006)
    st.divider()
    st.subheader(get_text('historical_chart', lang))

    # Period selection
    col1, col2 = st.columns([1, 3])

    with col1:
        # Period selector
        period_options = {
            get_text('days_30', lang): 30,
            get_text('days_90', lang): 90,
            get_text('days_180', lang): 180
        }

        selected_period_label = st.selectbox(
            get_text('select_period', lang),
            list(period_options.keys()),
            index=0
        )

        selected_period = period_options[selected_period_label]

    try:
        # Fetch OHLCV data
        ohlcv_df = None

        # Import yfinance helper
        from dashboard.yfinance_helper import fetch_ohlcv_yfinance

        # Try KIS broker first (for list selection)
        if "목록" in selection_method or "Select from" in selection_method:
            broker = get_kis_broker()

            if broker is not None:
                try:
                    with st.spinner(get_text('loading_chart', lang)):
                        ohlcv_df = broker.fetch_ohlcv(
                            selected_symbol,
                            timeframe='1d',
                            limit=selected_period,
                            overseas=True,
                            market='NASDAQ'
                        )
                except Exception as e:
                    st.warning(f"⚠️ KIS API OHLCV 조회 실패, yfinance로 시도합니다..." if lang == 'ko' else f"⚠️ KIS API OHLCV failed, trying yfinance...")
                    ohlcv_df = None

        # Fallback to yfinance or Direct input mode
        if ohlcv_df is None:
            # Convert days to yfinance period format
            period_map = {
                30: '1mo',
                90: '3mo',
                180: '6mo'
            }
            yf_period = period_map.get(selected_period, '3mo')

            with st.spinner(("yfinance로 OHLCV 조회 중..." if lang == 'ko' else "Fetching OHLCV from yfinance...") if ohlcv_df is None else get_text('loading_chart', lang)):
                ohlcv_df = fetch_ohlcv_yfinance(
                    selected_symbol,
                    period=yf_period,
                    interval='1d'
                )

                if ohlcv_df is None or ohlcv_df.empty:
                    st.error(f"❌ '{selected_symbol}' " + ("OHLCV 데이터를 조회할 수 없습니다." if lang == 'ko' else "OHLCV data not available."))
                    return

        # Ensure index is set to timestamp column for charting
        if 'timestamp' in ohlcv_df.columns:
            ohlcv_df = ohlcv_df.set_index('timestamp')

        # Create candlestick chart with volume subplot
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=(f'{selected_symbol} - Price', 'Volume')
        )

        # Candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=ohlcv_df.index,
                open=ohlcv_df['open'],
                high=ohlcv_df['high'],
                low=ohlcv_df['low'],
                close=ohlcv_df['close'],
                name='Price',
                increasing_line_color='#00c853',  # Green for up
                decreasing_line_color='#ff1744'   # Red for down
            ),
            row=1, col=1
        )

        # Volume bars with color based on price direction
        colors = ['#00c853' if close >= open_price else '#ff1744'
                 for close, open_price in zip(ohlcv_df['close'], ohlcv_df['open'])]

        fig.add_trace(
            go.Bar(
                x=ohlcv_df.index,
                y=ohlcv_df['volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.5
            ),
            row=2, col=1
        )

        # Update layout
        fig.update_layout(
            height=600,
            showlegend=False,
            xaxis_rangeslider_visible=False,
            hovermode='x unified'
        )

        fig.update_xaxes(title_text="Date", row=2, col=1)
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)

        # Display chart
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        # Use centralized error handler (US-009)
        from dashboard.error_handler import handle_kis_broker_error
        context = f"{get_text('historical_chart', lang)}"
        handle_kis_broker_error(e, lang=lang, symbol=selected_symbol)
