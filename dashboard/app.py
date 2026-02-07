"""
Enhanced Trading Dashboard with Multiple Strategies
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.config import Config
from trading_bot.data_handler import DataHandler
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, StochasticStrategy
from trading_bot.backtester import Backtester
from trading_bot.paper_trader import PaperTrader
from trading_bot.simulation_data import SimulationDataGenerator
from dashboard.charts import ChartGenerator
from dashboard.translations import get_text, get_strategy_name, get_strategy_desc
from dashboard.market_hours import MarketHours
from dashboard.stock_symbols import StockSymbolDB
import time
from datetime import datetime
from typing import Dict, Any


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


# Strategy configuration
STRATEGY_CONFIGS = {
    'Moving Average Crossover': {
        'class': MovingAverageCrossover,
        'params': {
            'fast_period': {'min': 5, 'max': 50, 'default': 10, 'label': 'Fast MA Period'},
            'slow_period': {'min': 10, 'max': 200, 'default': 30, 'label': 'Slow MA Period'}
        },
        'description': 'Generates BUY when fast MA crosses above slow MA, SELL when fast MA crosses below slow MA'
    },
    'RSI Strategy': {
        'class': RSIStrategy,
        'params': {
            'period': {'min': 5, 'max': 30, 'default': 14, 'label': 'RSI Period'},
            'overbought': {'min': 60, 'max': 90, 'default': 70, 'label': 'Overbought Level'},
            'oversold': {'min': 10, 'max': 40, 'default': 30, 'label': 'Oversold Level'}
        },
        'description': 'Generates BUY when RSI crosses below oversold level, SELL when RSI crosses above overbought level'
    },
    'MACD Strategy': {
        'class': MACDStrategy,
        'params': {
            'fast_period': {'min': 5, 'max': 20, 'default': 12, 'label': 'Fast EMA Period'},
            'slow_period': {'min': 20, 'max': 40, 'default': 26, 'label': 'Slow EMA Period'},
            'signal_period': {'min': 5, 'max': 15, 'default': 9, 'label': 'Signal Period'}
        },
        'description': 'Generates BUY when MACD line crosses above signal line, SELL when MACD line crosses below signal line'
    },
    'Bollinger Bands': {
        'class': BollingerBandsStrategy,
        'params': {
            'period': {'min': 10, 'max': 50, 'default': 20, 'label': 'Period'},
            'num_std': {'min': 1.0, 'max': 3.0, 'default': 2.0, 'step': 0.1, 'label': 'Std Deviations'}
        },
        'description': 'Generates BUY when price crosses below lower band, SELL when price crosses above upper band'
    },
    'Stochastic Oscillator': {
        'class': StochasticStrategy,
        'params': {
            'k_period': {'min': 5, 'max': 30, 'default': 14, 'label': '%K Period'},
            'd_period': {'min': 3, 'max': 10, 'default': 3, 'label': '%D Period'},
            'overbought': {'min': 60, 'max': 90, 'default': 80, 'label': 'Overbought Level'},
            'oversold': {'min': 10, 'max': 40, 'default': 20, 'label': 'Oversold Level'}
        },
        'description': 'Generates BUY when %K crosses above %D in oversold zone, SELL when %K crosses below %D in overbought zone'
    }
}


def init_session_state():
    """Initialize session state variables"""
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


def create_strategy(strategy_name: str, params: Dict[str, Any]):
    """Create strategy instance with given parameters"""
    strategy_config = STRATEGY_CONFIGS[strategy_name]
    strategy_class = strategy_config['class']
    return strategy_class(**params)


def sidebar_config():
    """Render configuration sidebar"""
    lang = st.session_state.language

    st.sidebar.title(get_text('configuration', lang))

    # Language Selection
    st.sidebar.subheader(get_text('language', lang))
    language = st.sidebar.selectbox(
        "",
        options=['한국어', 'English'],
        index=0 if st.session_state.language == 'ko' else 1,
        label_visibility="collapsed"
    )
    st.session_state.language = 'ko' if language == '한국어' else 'en'
    lang = st.session_state.language  # Update lang after selection

    st.sidebar.markdown("---")

    # Market Type Selection
    st.sidebar.subheader(get_text('market_type', lang))
    market_options = {
        get_text('stock_market', lang): 'stock',
        get_text('crypto_market', lang): 'crypto'
    }
    selected_market_display = st.sidebar.radio(
        "",
        options=list(market_options.keys()),
        index=0,  # Default to stocks
        label_visibility="collapsed"
    )
    st.session_state.market_type = market_options[selected_market_display]

    st.sidebar.markdown("---")

    # Data Source Selection
    st.sidebar.subheader(get_text('data_source', lang))
    use_simulation = st.sidebar.checkbox(
        get_text('use_simulation', lang),
        value=st.session_state.use_simulation,
        help=get_text('use_simulation_help', lang)
    )
    st.session_state.use_simulation = use_simulation

    # Market Settings (only for real data)
    if not use_simulation:
        st.sidebar.subheader(get_text('market_settings', lang))

        if st.session_state.market_type == 'stock':
            # Display market status for stocks
            market_hours = MarketHours()
            status_text, status_color = market_hours.format_status_message(lang)
            st.sidebar.info(status_text)

            # Show market hours in expander
            with st.sidebar.expander(get_text('market_hours', lang)):
                hours_display = market_hours.get_market_hours_display()
                st.markdown(f"**{get_text('pre_market', lang)}**")
                st.markdown(f"🇺🇸 {hours_display['pre_market_est']}")
                st.markdown(f"🇰🇷 {hours_display['pre_market_kst']}")
                st.markdown("---")
                st.markdown(f"**{get_text('regular_hours', lang)}**")
                st.markdown(f"🇺🇸 {hours_display['regular_est']}")
                st.markdown(f"🇰🇷 {hours_display['regular_kst']}")
                st.markdown("---")
                st.markdown(f"**{get_text('after_hours', lang)}**")
                st.markdown(f"🇺🇸 {hours_display['after_hours_est']}")
                st.markdown(f"🇰🇷 {hours_display['after_hours_kst']}")

            # Initialize stock database
            if 'stock_db' not in st.session_state:
                st.session_state.stock_db = StockSymbolDB()

            stock_db = st.session_state.stock_db

            # Stock search
            search_query = st.sidebar.text_input(
                get_text('stock_search', lang),
                placeholder='AAPL, Apple, Tesla...',
                key='stock_search_input'
            )

            # Show search results
            if search_query:
                matches = stock_db.search(search_query)
                if matches:
                    st.sidebar.markdown(f"**{len(matches)} {get_text('popular_stocks', lang)}**")
                    for match in matches[:5]:  # Limit to 5 results
                        if st.sidebar.button(
                            f"{match['symbol']} - {match['name'][:30]}",
                            key=f"search_{match['symbol']}"
                        ):
                            symbol = match['symbol']
                            st.session_state.selected_stock = match
                else:
                    st.sidebar.info("No matches found")

            # Symbol input
            symbol = st.sidebar.text_input(
                get_text('stock_symbol', lang),
                value=st.session_state.get('selected_stock', {}).get('symbol', 'AAPL'),
                placeholder='AAPL, TSLA, NVDA...'
            )

            # Show stock info if available
            if symbol:
                stock_info = stock_db.get_by_symbol(symbol)
                if stock_info:
                    st.sidebar.info(
                        f"**{stock_info['name']}**\n\n"
                        f"{get_text('sector', lang)}: {stock_info['sector']}\n\n"
                        f"{get_text('industry', lang)}: {stock_info['industry']}"
                    )

            # Popular stocks by sector
            with st.sidebar.expander(f"{get_text('popular_stocks', lang)} ({get_text('sector', lang)})"):
                sectors = stock_db.get_all_sectors()
                selected_sector = st.selectbox(
                    get_text('sector', lang),
                    sectors,
                    key='sector_filter',
                    label_visibility="collapsed"
                )
                sector_stocks = stock_db.get_by_sector(selected_sector)
                cols = st.columns(2)
                for idx, stock in enumerate(sector_stocks[:10]):
                    if cols[idx % 2].button(
                        stock['symbol'],
                        key=f"sector_{stock['symbol']}"
                    ):
                        symbol = stock['symbol']
                        st.session_state.selected_stock = stock

            timeframe = st.sidebar.selectbox(
                get_text('timeframe', lang),
                ['1m', '5m', '15m', '1h', '1d'],
                index=3
            )
        else:
            # Crypto market settings
            symbol = st.sidebar.text_input(
                get_text('symbol', lang),
                value=st.session_state.config.get('symbol', 'BTC/USDT')
            )
            timeframe = st.sidebar.selectbox(
                get_text('timeframe', lang),
                ['1m', '5m', '15m', '1h', '4h', '1d'],
                index=3
            )

        st.session_state.config['symbol'] = symbol
        st.session_state.config['timeframe'] = timeframe

    # Strategy Selection
    st.sidebar.subheader(get_text('strategy_selection', lang))

    # Translate strategy names for display
    strategy_display_names = {k: get_strategy_name(k, lang) for k in STRATEGY_CONFIGS.keys()}
    reverse_strategy_names = {v: k for k, v in strategy_display_names.items()}

    current_display_name = strategy_display_names[st.session_state.selected_strategy]

    selected_display_name = st.sidebar.selectbox(
        get_text('select_strategy', lang),
        options=list(strategy_display_names.values()),
        index=list(strategy_display_names.values()).index(current_display_name)
    )

    strategy_name = reverse_strategy_names[selected_display_name]
    st.session_state.selected_strategy = strategy_name

    # Display strategy description
    st.sidebar.info(f"ℹ️ {get_strategy_desc(strategy_name, lang)}")

    # Strategy Parameters
    st.sidebar.subheader(get_text('strategy_parameters', lang))
    params = {}
    for param_name, param_config in STRATEGY_CONFIGS[strategy_name]['params'].items():
        # Translate parameter label
        translated_label = get_text(param_config['label'], lang)

        if param_config.get('step'):
            # Float parameter
            params[param_name] = st.sidebar.slider(
                translated_label,
                min_value=param_config['min'],
                max_value=param_config['max'],
                value=param_config['default'],
                step=param_config['step']
            )
        else:
            # Integer parameter
            params[param_name] = st.sidebar.slider(
                translated_label,
                min_value=param_config['min'],
                max_value=param_config['max'],
                value=param_config['default']
            )

    st.session_state.strategy_params = params

    # Trading Parameters
    st.sidebar.subheader(get_text('trading_parameters', lang))
    initial_capital = st.sidebar.number_input(
        get_text('initial_capital', lang),
        min_value=100.0,
        value=st.session_state.config['initial_capital'],
        step=100.0
    )
    st.session_state.config['initial_capital'] = initial_capital

    # Initialize System Button
    if st.sidebar.button(get_text('initialize_system', lang), type="primary"):
        with st.spinner(get_text('running_backtest', lang)):
            if not use_simulation:
                st.session_state.data_handler = DataHandler(
                    exchange_name=st.session_state.config['exchange']
                )
            st.session_state.strategy_instance = create_strategy(strategy_name, params)
            st.sidebar.success(get_text('system_initialized', lang))


def backtest_tab():
    """Enhanced backtesting interface"""
    lang = st.session_state.language

    st.header(get_text('backtest_title', lang))

    if st.session_state.strategy_instance is None:
        st.warning(get_text('init_warning', lang))
        return

    # Data source selection
    col1, col2 = st.columns([2, 1])

    with col1:
        if st.session_state.use_simulation:
            st.info(get_text('using_simulation', lang))
        else:
            start_date = st.date_input(get_text('start_date', lang), value=pd.to_datetime("2024-01-01"))
            end_date = st.date_input(get_text('end_date', lang), value=pd.to_datetime("2024-12-31"))

    with col2:
        if st.session_state.use_simulation:
            num_periods = st.number_input(get_text('num_periods', lang), min_value=100, max_value=5000, value=1000)

    # Run Backtest Button
    if st.button(get_text('run_backtest', lang), type="primary"):
        with st.spinner(get_text('running_backtest', lang)):
            try:
                # Get data
                if st.session_state.use_simulation:
                    generator = SimulationDataGenerator(seed=42)
                    df = generator.generate_ohlcv(periods=num_periods)
                else:
                    if st.session_state.data_handler is None:
                        st.error("Data handler not initialized. Please initialize the system.")
                        return

                    df = st.session_state.data_handler.fetch_historical_data(
                        symbol=st.session_state.config['symbol'],
                        timeframe=st.session_state.config['timeframe'],
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d')
                    )

                if df.empty:
                    st.error("No data retrieved. Please check your parameters.")
                    return

                # Run backtest
                backtester = Backtester(
                    strategy=st.session_state.strategy_instance,
                    initial_capital=st.session_state.config['initial_capital']
                )
                results = backtester.run(df)

                # Store results
                st.session_state.backtest_results = {
                    'results': results,
                    'backtester': backtester,
                    'data': df,
                    'strategy_name': st.session_state.selected_strategy
                }

                st.success(get_text('backtest_completed', lang))

            except Exception as e:
                st.error(f"{get_text('backtest_error', lang)}{e}")
                import traceback
                st.code(traceback.format_exc())
                return

    # Display results
    if st.session_state.backtest_results:
        display_backtest_results(st.session_state.backtest_results)


def display_backtest_results(backtest_data: Dict):
    """Display backtest results with enhanced visualizations"""
    lang = st.session_state.language
    results = backtest_data['results']
    backtester = backtest_data['backtester']
    data = backtest_data['data']
    strategy_name = backtest_data['strategy_name']

    # Performance Metrics
    st.subheader(get_text('performance_metrics', lang))

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        return_pct = results['total_return']
        return_color = "normal" if return_pct >= 0 else "inverse"
        st.metric(
            get_text('total_return', lang),
            f"{return_pct:.2f}%",
            delta=f"${results['final_capital'] - results['initial_capital']:.2f}",
            delta_color=return_color
        )

    with col2:
        st.metric(get_text('sharpe_ratio', lang), f"{results['sharpe_ratio']:.2f}")

    with col3:
        st.metric(get_text('max_drawdown', lang), f"{results['max_drawdown']:.2f}%")

    with col4:
        st.metric(get_text('win_rate', lang), f"{results['win_rate']:.2f}%")

    with col5:
        st.metric(get_text('total_trades', lang), results['total_trades'])

    col1, col2 = st.columns(2)
    with col1:
        st.metric(get_text('initial_capital', lang), f"${results['initial_capital']:,.2f}")
    with col2:
        st.metric(get_text('final_capital', lang), f"${results['final_capital']:,.2f}")

    # Charts
    chart_gen = ChartGenerator()

    # Equity Curve
    st.subheader(get_text('equity_curve', lang))
    equity_df = backtester.get_equity_curve_df()
    fig = chart_gen.plot_equity_curve(equity_df)
    st.plotly_chart(fig, use_container_width=True)

    # Price Chart with Indicators and Signals
    translated_strategy_name = get_strategy_name(strategy_name, lang)
    st.subheader(f"{get_text('price_chart', lang)} - {translated_strategy_name}")
    trades_df = backtester.get_trades_df()
    data_with_indicators = st.session_state.strategy_instance.calculate_indicators(data)

    # Use enhanced chart plotting based on strategy type
    fig = chart_gen.plot_strategy_chart(data_with_indicators, trades_df, strategy_name)
    st.plotly_chart(fig, use_container_width=True)

    # Trade History
    st.subheader(get_text('trade_history', lang))
    if not trades_df.empty:
        # Format the trades dataframe for better display
        display_trades = trades_df.copy()
        if 'timestamp' in display_trades.columns:
            display_trades['timestamp'] = pd.to_datetime(display_trades['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
        if 'price' in display_trades.columns:
            display_trades['price'] = display_trades['price'].apply(lambda x: f"${x:.2f}")
        if 'pnl' in display_trades.columns:
            display_trades['pnl'] = display_trades['pnl'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "")

        st.dataframe(display_trades, use_container_width=True)
    else:
        st.info(get_text('no_trades', lang))


def strategy_comparison_tab():
    """Strategy comparison interface"""
    st.header("🔍 Strategy Comparison")

    st.markdown("""
    Compare the performance of different trading strategies on the same dataset.
    Select multiple strategies and parameters to see which performs best.
    """)

    # Strategy selection
    st.subheader("Select Strategies to Compare")

    selected_strategies = st.multiselect(
        "Choose strategies",
        options=list(STRATEGY_CONFIGS.keys()),
        default=['Moving Average Crossover', 'RSI Strategy']
    )

    if len(selected_strategies) < 2:
        st.info("Please select at least 2 strategies to compare.")
        return

    # Parameter configuration for each strategy
    strategy_instances = {}

    with st.expander("⚙️ Configure Strategy Parameters", expanded=True):
        for strategy_name in selected_strategies:
            st.markdown(f"**{strategy_name}**")
            cols = st.columns(len(STRATEGY_CONFIGS[strategy_name]['params']))
            params = {}

            for idx, (param_name, param_config) in enumerate(STRATEGY_CONFIGS[strategy_name]['params'].items()):
                with cols[idx]:
                    if param_config.get('step'):
                        params[param_name] = st.slider(
                            param_config['label'],
                            min_value=param_config['min'],
                            max_value=param_config['max'],
                            value=param_config['default'],
                            step=param_config['step'],
                            key=f"{strategy_name}_{param_name}"
                        )
                    else:
                        params[param_name] = st.slider(
                            param_config['label'],
                            min_value=param_config['min'],
                            max_value=param_config['max'],
                            value=param_config['default'],
                            key=f"{strategy_name}_{param_name}"
                        )

            strategy_instances[strategy_name] = create_strategy(strategy_name, params)
            st.markdown("---")

    # Data configuration
    col1, col2 = st.columns(2)
    with col1:
        use_simulation = st.checkbox("Use Simulation Data", value=True, key="comparison_sim")
    with col2:
        if use_simulation:
            num_periods = st.number_input("Number of periods", min_value=100, max_value=5000, value=1000, key="comparison_periods")

    # Run comparison
    if st.button("Run Comparison", type="primary"):
        with st.spinner("Running strategy comparison..."):
            try:
                # Generate data
                if use_simulation:
                    generator = SimulationDataGenerator(seed=42)
                    df = generator.generate_ohlcv(periods=num_periods)
                else:
                    st.error("Real data comparison not implemented yet. Please use simulation data.")
                    return

                # Run backtests for all strategies
                comparison_results = []

                for strategy_name, strategy in strategy_instances.items():
                    backtester = Backtester(
                        strategy=strategy,
                        initial_capital=st.session_state.config['initial_capital']
                    )
                    results = backtester.run(df)

                    comparison_results.append({
                        'Strategy': strategy_name,
                        'Total Return (%)': results['total_return'],
                        'Sharpe Ratio': results['sharpe_ratio'],
                        'Max Drawdown (%)': results['max_drawdown'],
                        'Win Rate (%)': results['win_rate'],
                        'Total Trades': results['total_trades'],
                        'Final Capital ($)': results['final_capital']
                    })

                st.session_state.comparison_results = pd.DataFrame(comparison_results)
                st.success("✅ Comparison completed!")

            except Exception as e:
                st.error(f"❌ Error during comparison: {e}")
                import traceback
                st.code(traceback.format_exc())
                return

    # Display comparison results
    if st.session_state.comparison_results is not None:
        st.subheader("📊 Comparison Results")

        # Highlight best performers
        styled_df = st.session_state.comparison_results.style.highlight_max(
            subset=['Total Return (%)', 'Sharpe Ratio', 'Win Rate (%)'],
            color='lightgreen'
        ).highlight_min(
            subset=['Max Drawdown (%)'],
            color='lightgreen'
        ).format({
            'Total Return (%)': '{:.2f}',
            'Sharpe Ratio': '{:.2f}',
            'Max Drawdown (%)': '{:.2f}',
            'Win Rate (%)': '{:.2f}',
            'Final Capital ($)': '${:,.2f}'
        })

        st.dataframe(styled_df, use_container_width=True)

        # Visualization
        st.subheader("📈 Visual Comparison")

        col1, col2 = st.columns(2)

        with col1:
            # Return comparison
            import plotly.express as px
            fig = px.bar(
                st.session_state.comparison_results,
                x='Strategy',
                y='Total Return (%)',
                title='Total Return Comparison',
                color='Total Return (%)',
                color_continuous_scale=['red', 'yellow', 'green']
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Sharpe Ratio comparison
            fig = px.bar(
                st.session_state.comparison_results,
                x='Strategy',
                y='Sharpe Ratio',
                title='Sharpe Ratio Comparison',
                color='Sharpe Ratio',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, use_container_width=True)


def paper_trading_tab():
    """Paper trading interface"""
    st.header("📄 Paper Trading")

    if st.session_state.strategy_instance is None:
        st.warning("⚠️ Please initialize the system from the sidebar first.")
        return

    if st.session_state.use_simulation:
        st.warning("⚠️ Paper trading requires real market data. Please disable 'Use Simulation Data' in the sidebar.")
        return

    col1, col2 = st.columns([1, 3])

    with col1:
        if not st.session_state.live_mode:
            if st.button("Start Paper Trading", type="primary"):
                st.session_state.paper_trader = PaperTrader(
                    strategy=st.session_state.strategy_instance,
                    data_handler=st.session_state.data_handler,
                    initial_capital=st.session_state.config['initial_capital']
                )
                st.session_state.live_mode = True
                st.rerun()
        else:
            if st.button("Stop Paper Trading", type="secondary"):
                st.session_state.live_mode = False
                st.rerun()

    with col2:
        if st.session_state.live_mode:
            st.info(f"🟢 Paper trading is ACTIVE with {st.session_state.selected_strategy} - Updates every 60 seconds")
        else:
            st.info("⚪ Paper trading is STOPPED")

    # Live updates
    if st.session_state.live_mode and st.session_state.paper_trader:
        placeholder = st.empty()

        with placeholder.container():
            st.session_state.paper_trader.update(
                symbol=st.session_state.config['symbol'],
                timeframe=st.session_state.config['timeframe']
            )

            if st.session_state.paper_trader.equity_history:
                latest = st.session_state.paper_trader.equity_history[-1]

                # Metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Current Price", f"${latest['price']:.2f}")

                with col2:
                    portfolio_value = latest['equity']
                    st.metric("Portfolio Value", f"${portfolio_value:.2f}")

                with col3:
                    pnl = portfolio_value - st.session_state.paper_trader.initial_capital
                    pnl_pct = (pnl / st.session_state.paper_trader.initial_capital) * 100
                    st.metric("P&L", f"${pnl:.2f}", f"{pnl_pct:+.2f}%")

                with col4:
                    position = latest['position']
                    st.metric("Position", f"{position:.6f}")

                # Charts
                equity_df = st.session_state.paper_trader.get_equity_df()
                if not equity_df.empty:
                    chart_gen = ChartGenerator()
                    fig = chart_gen.plot_equity_curve(equity_df)
                    st.plotly_chart(fig, use_container_width=True)

                # Trade history
                trades_df = st.session_state.paper_trader.get_trades_df()
                if not trades_df.empty:
                    st.subheader("Trade History")
                    st.dataframe(trades_df, use_container_width=True)

            time.sleep(60)
            st.rerun()


def live_monitor_tab():
    """Live market monitoring with strategy signals"""
    st.header("📡 Live Market Monitor")

    if st.session_state.strategy_instance is None:
        st.warning("⚠️ Please initialize the system from the sidebar first.")
        return

    if st.session_state.use_simulation:
        st.warning("⚠️ Live monitoring requires real market data. Please disable 'Use Simulation Data' in the sidebar.")
        return

    # Auto-refresh toggle
    auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)

    if st.button("Refresh Now") or auto_refresh:
        with st.spinner("Fetching latest data..."):
            try:
                df = st.session_state.data_handler.fetch_ohlcv(
                    symbol=st.session_state.config['symbol'],
                    timeframe=st.session_state.config['timeframe'],
                    limit=100
                )

                if df.empty:
                    st.error("No data retrieved.")
                    return

                # Calculate indicators and signals
                data = st.session_state.strategy_instance.calculate_indicators(df)
                signal, info = st.session_state.strategy_instance.get_current_signal(df)

                # Display current status
                st.subheader(f"Current Signal - {st.session_state.selected_strategy}")

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Current Price", f"${info.get('close', 0):.2f}")

                with col2:
                    signal_text = "🟢 BUY" if signal == 1 else "🔴 SELL" if signal == -1 else "⚪ HOLD"
                    st.metric("Signal", signal_text)

                with col3:
                    position = info.get('position', 0)
                    position_text = "LONG" if position == 1 else "FLAT"
                    st.metric("Position", position_text)

                with col4:
                    st.metric("Timestamp", pd.Timestamp.now().strftime('%H:%M:%S'))

                # Display strategy-specific indicators
                display_strategy_indicators(info)

                # Price chart
                chart_gen = ChartGenerator()
                fig = chart_gen.plot_strategy_chart(data, pd.DataFrame(), st.session_state.selected_strategy)
                st.plotly_chart(fig, use_container_width=True)

                # Recent data table
                st.subheader("Recent Data")
                display_cols = ['open', 'high', 'low', 'close', 'volume']
                st.dataframe(data[display_cols].tail(20), use_container_width=True)

                if auto_refresh:
                    time.sleep(30)
                    st.rerun()

            except Exception as e:
                st.error(f"Error fetching data: {e}")


def realtime_quotes_tab():
    """Real-time stock quotes interface"""
    lang = st.session_state.language

    st.header(get_text('tab_quotes', lang))

    # Placeholder for US-004 onwards
    st.info("Real-time Quotes tab - Coming soon!")
    st.markdown("""
    This tab will display:
    - Stock symbol selection
    - Real-time price quotes
    - OHLCV candlestick charts
    - Auto-refresh functionality
    """)


def display_strategy_indicators(info: Dict):
    """Display strategy-specific indicator values"""
    st.subheader("📊 Indicator Values")

    # Remove common keys
    exclude_keys = {'timestamp', 'close', 'signal', 'position'}
    indicator_info = {k: v for k, v in info.items() if k not in exclude_keys}

    # Display in columns
    cols = st.columns(min(len(indicator_info), 4))
    for idx, (key, value) in enumerate(indicator_info.items()):
        with cols[idx % 4]:
            # Format the key for display
            display_key = key.replace('_', ' ').title()

            # Format the value
            if isinstance(value, (int, float)):
                display_value = f"{value:.2f}"
            else:
                display_value = str(value)

            st.metric(display_key, display_value)


def main():
    """Main application"""
    init_session_state()

    lang = st.session_state.language

    # Title
    st.title(f"📈 {get_text('page_title', lang)}")
    st.markdown(f"**{get_text('page_subtitle', lang)}**")
    st.markdown("---")

    # Sidebar
    sidebar_config()

    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        get_text('tab_comparison', lang),
        get_text('tab_backtest', lang),
        get_text('tab_live', lang),
        get_text('tab_quotes', lang),
        get_text('tab_paper', lang)
    ])

    with tab1:
        strategy_comparison_tab()

    with tab2:
        backtest_tab()

    with tab3:
        live_monitor_tab()

    with tab4:
        realtime_quotes_tab()

    with tab5:
        paper_trading_tab()

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
