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
from trading_bot.database import TradingDatabase
from dashboard.charts import ChartGenerator
from dashboard.translations import get_text, get_strategy_name, get_strategy_desc
from dashboard.market_hours import MarketHours
from dashboard.stock_symbols import StockSymbolDB
import time
from datetime import datetime
from typing import Dict, Any, Optional
import threading


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
    if 'paper_trading_active' not in st.session_state:
        st.session_state.paper_trading_active = False


def create_strategy(strategy_name: str, params: Dict[str, Any]):
    """Create strategy instance with given parameters"""
    strategy_config = STRATEGY_CONFIGS[strategy_name]
    strategy_class = strategy_config['class']
    return strategy_class(**params)  # type: ignore[operator]


def start_paper_trading(
    strategy_name: str,
    symbols: list,
    initial_capital: float,
    position_size: float
) -> Optional[str]:
    """
    Start paper trading session in background thread

    Args:
        strategy_name: Name of the strategy to use
        symbols: List of stock symbols to trade
        initial_capital: Starting capital
        position_size: Position size fraction (0.1 to 1.0)

    Returns:
        session_id if successful, None if failed
    """
    try:
        # Create strategy instance
        strategy: Any
        if strategy_name == 'RSI Strategy':
            strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        elif strategy_name == 'MACD Strategy':
            strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        elif strategy_name == 'Moving Average Crossover':
            strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        elif strategy_name == 'Bollinger Bands':
            strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        elif strategy_name == 'Stochastic Oscillator':
            strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        # Get KIS broker for US stocks
        from dashboard.kis_broker import get_kis_broker
        broker = get_kis_broker()

        if broker is None:
            st.error("❌ KIS 브로커 초기화 실패. 환경 변수를 확인해주세요.")
            return None

        # Initialize database
        db = TradingDatabase()

        # Create paper trader
        paper_trader = PaperTrader(
            strategy=strategy,  # type: ignore[arg-type]
            symbols=symbols,
            broker=broker,
            initial_capital=initial_capital,
            position_size=position_size,
            db=db
        )

        # Store in session state
        st.session_state.paper_trader = paper_trader
        st.session_state.paper_trading_active = True

        # Start paper trading in background thread
        def run_trading():
            try:
                paper_trader.run_realtime(interval_seconds=60, timeframe='1d')
            except Exception as e:
                st.session_state.paper_trading_error = str(e)
                st.session_state.paper_trading_active = False

        trading_thread = threading.Thread(target=run_trading, daemon=True)
        trading_thread.start()

        # Store thread reference
        st.session_state.paper_trading_thread = trading_thread

        # Return session_id
        return paper_trader.session_id

    except Exception as e:
        st.error(f"❌ 모의투자 시작 실패: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None


def stop_paper_trading():
    """Stop paper trading session"""
    if st.session_state.paper_trader:
        st.session_state.paper_trader.stop()
        st.session_state.paper_trading_active = False

        # Wait for thread to finish (with timeout)
        if hasattr(st.session_state, 'paper_trading_thread'):
            thread = st.session_state.paper_trading_thread
            if thread.is_alive():
                thread.join(timeout=5.0)

        st.success("✅ 모의투자가 중지되었습니다.")
    else:
        st.warning("⚠️ 실행 중인 모의투자 세션이 없습니다.")


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
                # Create data handler based on market type
                if st.session_state.market_type == 'stock':
                    # Import and initialize KIS broker for stocks
                    try:
                        from dashboard.kis_broker import get_kis_broker
                        kis_broker = get_kis_broker()
                        
                        if kis_broker:
                            # Create DataHandler with KIS broker
                            st.session_state.data_handler = DataHandler(broker=kis_broker)
                            st.sidebar.success("✅ " + get_text('system_initialized', lang) + " (KIS Broker)")
                        else:
                            st.sidebar.error("❌ KIS Broker initialization failed. Using simulation mode.")
                            st.session_state.use_simulation = True
                            st.session_state.data_handler = None
                            return
                    except Exception as e:
                        st.sidebar.error(f"❌ KIS Broker error: {str(e)}")
                        st.session_state.use_simulation = True
                        st.session_state.data_handler = None
                        return
                else:
                    # Use CCXT for crypto
                    st.session_state.data_handler = DataHandler(
                        exchange_name=st.session_state.config['exchange']
                    )
                    st.sidebar.success("✅ " + get_text('system_initialized', lang) + " (CCXT)")
            else:
                st.session_state.data_handler = None
            
            st.session_state.strategy_instance = create_strategy(strategy_name, params)
            if use_simulation:
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
        return_color = "normal" if return_pct >= 0 else "inverse"  # type: ignore[assignment]
        st.metric(
            get_text('total_return', lang),
            f"{return_pct:.2f}%",
            delta=f"${results['final_capital'] - results['initial_capital']:.2f}",
            delta_color=return_color  # type: ignore[arg-type]
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
    lang = st.session_state.language

    st.header(get_text('tab_paper', lang))

    st.markdown("""
    실시간 모의투자 기능입니다. 전략과 종목을 선택하여 실제 시장 데이터로 모의투자를 실행할 수 있습니다.
    """)

    # Configuration Section
    st.subheader("⚙️ 모의투자 설정")

    col1, col2 = st.columns(2)

    with col1:
        # Strategy selector
        strategy_options = ['RSI Strategy', 'MACD Strategy', 'Moving Average Crossover',
                           'Bollinger Bands', 'Stochastic Oscillator']
        selected_strategy = st.selectbox(
            "전략 선택",
            options=strategy_options,
            index=0,
            help="모의투자에 사용할 전략을 선택하세요"
        )

        # Multi-select for US stocks
        us_stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']
        selected_symbols = st.multiselect(
            "미국 주식 선택",
            options=us_stocks,
            default=['AAPL'],
            help="모의투자할 미국 주식을 선택하세요 (여러 종목 선택 가능)"
        )

    with col2:
        # Initial capital input
        initial_capital = st.number_input(
            "초기 자본 ($)",
            min_value=1000.0,
            max_value=1000000.0,
            value=10000.0,
            step=1000.0,
            help="모의투자 시작 자본금"
        )

        # Position size slider
        position_size = st.slider(
            "포지션 크기",
            min_value=0.1,
            max_value=1.0,
            value=0.95,
            step=0.05,
            help="각 거래에 사용할 자본 비율 (0.1 = 10%, 1.0 = 100%)"
        )

    # Validation
    if not selected_symbols:
        st.warning("⚠️ 최소 1개 이상의 종목을 선택해주세요.")
        return

    st.markdown("---")

    # Control Section
    st.subheader("🎮 모의투자 제어")

    # Initialize session state for paper trading
    if 'paper_trading_active' not in st.session_state:
        st.session_state.paper_trading_active = False
    if 'paper_trader' not in st.session_state:
        st.session_state.paper_trader = None

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        # 모의투자 시작 button
        start_button = st.button(
            "🚀 모의투자 시작",
            type="primary",
            disabled=st.session_state.paper_trading_active,
            use_container_width=True
        )

    with col2:
        # 모의투자 중지 button
        stop_button = st.button(
            "⏹️ 모의투자 중지",
            type="secondary",
            disabled=not st.session_state.paper_trading_active,
            use_container_width=True
        )

    with col3:
        # Status indicator
        if st.session_state.paper_trading_active:
            st.success(f"🟢 모의투자 실행 중 - {selected_strategy}")
        else:
            st.info("⚪ 모의투자 대기 중")

    # Handle button clicks
    if start_button:
        session_id = start_paper_trading(
            strategy_name=selected_strategy,
            symbols=selected_symbols,
            initial_capital=initial_capital,
            position_size=position_size
        )

        if session_id:
            st.success(f"✅ 모의투자가 시작되었습니다! (Session ID: {session_id})")
            st.rerun()
        else:
            st.error("❌ 모의투자 시작에 실패했습니다.")

    if stop_button:
        stop_paper_trading()
        st.rerun()

    # Check for errors in background thread
    if hasattr(st.session_state, 'paper_trading_error'):
        st.error(f"❌ 모의투자 실행 중 오류 발생: {st.session_state.paper_trading_error}")
        del st.session_state.paper_trading_error

    # Display current session info
    if st.session_state.paper_trading_active and st.session_state.paper_trader:
        st.markdown("---")
        st.subheader("📊 현재 세션 정보")

        trader = st.session_state.paper_trader

        # Display session ID if available
        if trader.session_id:
            st.success(f"🔑 Session ID: **{trader.session_id}**")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("전략", trader.strategy.name if hasattr(trader.strategy, 'name') else selected_strategy)

        with col2:
            st.metric("종목 수", len(trader.symbols))

        with col3:
            st.metric("초기 자본", f"${trader.initial_capital:,.2f}")

        with col4:
            st.metric("포지션 크기", f"{trader.position_size:.0%}")

        # Show selected symbols
        st.info(f"📈 선택된 종목: {', '.join(trader.symbols)}")

        # Real-time Portfolio Status
        st.markdown("---")
        st.subheader("💼 실시간 포트폴리오 현황")

        # Auto-refresh every 10 seconds
        time.sleep(0.1)  # Brief pause to allow UI to render

        # Get current prices for all symbols
        try:
            from dashboard.kis_broker import get_kis_broker
            broker = get_kis_broker()

            if broker:
                current_prices = {}
                for symbol in trader.symbols:
                    try:
                        ticker = broker.fetch_ticker(symbol, overseas=True, market='NASDAQ')
                        current_prices[symbol] = ticker['last']
                    except Exception:
                        # If fetching fails for a symbol, use last known price or 0
                        current_prices[symbol] = 0.0

                # Calculate portfolio value
                portfolio_value = trader.get_portfolio_value(current_prices)
                total_pnl = portfolio_value - trader.initial_capital
                total_pnl_pct = (total_pnl / trader.initial_capital) * 100

                # Display summary metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric(
                        "총 포트폴리오 가치",
                        f"${portfolio_value:,.2f}",
                        delta=f"{total_pnl_pct:+.2f}%"
                    )

                with col2:
                    st.metric("현금 잔고", f"${trader.capital:,.2f}")

                with col3:
                    st.metric(
                        "총 손익 (P&L)",
                        f"${total_pnl:,.2f}",
                        delta=f"{total_pnl_pct:+.2f}%"
                    )

                with col4:
                    total_trades = len([t for t in trader.trades if t['type'] == 'SELL'])
                    st.metric("완료된 거래", total_trades)

                # Positions table
                st.markdown("---")
                st.subheader("📊 보유 포지션")

                if any(pos > 0 for pos in trader.positions.values()):
                    positions_data = []

                    for symbol, shares in trader.positions.items():
                        if shares > 0:
                            current_price = current_prices.get(symbol, 0.0)
                            entry_price = trader.entry_prices.get(symbol, 0.0)
                            market_value = shares * current_price
                            pnl = (current_price - entry_price) * shares
                            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

                            positions_data.append({
                                'Symbol': symbol,
                                'Shares': f"{shares:.6f}",
                                'Current Price': f"${current_price:.2f}",
                                'Market Value': f"${market_value:.2f}",
                                'P&L': f"${pnl:.2f}",
                                'P&L %': f"{pnl_pct:+.2f}%"
                            })

                    if positions_data:
                        positions_df = pd.DataFrame(positions_data)
                        st.dataframe(positions_df, use_container_width=True)
                    else:
                        st.info("현재 보유 중인 포지션이 없습니다.")
                else:
                    st.info("현재 보유 중인 포지션이 없습니다.")

                # Auto-refresh trigger
                st.markdown("---")
                st.caption("🔄 자동 새로고침: 10초마다 업데이트")
                time.sleep(10)
                st.rerun()

            else:
                st.warning("⚠️ 브로커 연결 실패. 포트폴리오 정보를 가져올 수 없습니다.")

        except Exception as e:
            st.error(f"❌ 포트폴리오 데이터 로딩 실패: {e}")

    elif not st.session_state.paper_trading_active:
        # No active session message
        st.info("ℹ️ 활성화된 모의투자 세션이 없습니다. '모의투자 시작' 버튼을 눌러 시작하세요.")


def live_monitor_tab():
    """Live market monitoring with strategy signals"""
    lang = st.session_state.language
    st.header(get_text('live_title', lang))

    if st.session_state.strategy_instance is None:
        st.warning(get_text('init_warning', lang))
        return

    # Show data source mode indicator
    if st.session_state.use_simulation:
        st.info(f"📊 {get_text('simulation_mode', lang)} - {get_text('market_data_from', lang)}: {get_text('simulated_data', lang)}")
    else:
        # Determine data source based on market type
        if st.session_state.market_type == 'stock':
            data_source = get_text('kis_broker', lang)
        else:
            data_source = get_text('exchange_data', lang)
        st.success(f"📡 {get_text('real_time_mode', lang)} - {get_text('market_data_from', lang)}: {data_source}")

    # Current Market Price Section (US-008) - Only show for stock market and non-simulation mode
    if st.session_state.market_type == 'stock' and not st.session_state.use_simulation:
        st.markdown("---")
        st.subheader(f"💰 {get_text('current_market_price', lang)}")

        # Try to get KIS broker for real-time quote
        try:
            from dashboard.kis_broker import get_kis_broker
            kis_broker = get_kis_broker()

            if kis_broker:
                # Get the current symbol from config
                symbol = st.session_state.config.get('symbol', 'AAPL')

                # For US stocks, we need to remove the market suffix (e.g., AAPL.US -> AAPL)
                if '.' in symbol:
                    symbol = symbol.split('.')[0]

                # Fetch real-time quote
                with st.spinner(get_text('fetching_quote', lang)):
                    try:
                        ticker = kis_broker.fetch_ticker(symbol, overseas=True, market='NASDAQ')

                        if ticker:
                            # Display current market price with change info
                            col1, col2, col3, col4, col5 = st.columns(5)

                            with col1:
                                st.metric(
                                    get_text('current_price', lang),
                                    f"${ticker['last']:.2f}",
                                    delta=f"{ticker['rate']:.2f}%",
                                    delta_color="normal"
                                )

                            with col2:
                                st.metric(get_text('open_price', lang), f"${ticker['open']:.2f}")

                            with col3:
                                st.metric(get_text('high_price', lang), f"${ticker['high']:.2f}")

                            with col4:
                                st.metric(get_text('low_price', lang), f"${ticker['low']:.2f}")

                            with col5:
                                volume_str = f"{int(ticker['volume']):,}"
                                st.metric(get_text('volume', lang), volume_str)

                            # Display last updated time
                            st.caption(f"⏰ {get_text('last_updated', lang)}: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    except Exception as e:
                        # Use centralized error handler (US-009)
                        from dashboard.error_handler import handle_kis_broker_error
                        handle_kis_broker_error(e, lang=lang, symbol=symbol)
            else:
                st.info(f"ℹ️ {get_text('kis_not_available', lang)}")

        except ImportError:
            st.warning("⚠️ KIS broker module not available")

        st.markdown("---")

    # Strategy Signal Section
    # Auto-refresh toggle
    auto_refresh = st.checkbox(get_text('auto_refresh', lang), value=False)

    if st.button(get_text('refresh_now', lang)) or auto_refresh:
        with st.spinner(get_text('fetching_data', lang)):
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
                st.subheader(f"{get_text('current_signal', lang)} - {get_strategy_name(st.session_state.selected_strategy, lang)}")

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric(get_text('current_price', lang), f"${info.get('close', 0):.2f}")

                with col2:
                    signal_text = "🟢 BUY" if signal == 1 else "🔴 SELL" if signal == -1 else "⚪ HOLD"
                    st.metric(get_text('signal', lang), signal_text)

                with col3:
                    position = info.get('position', 0)
                    position_text = "LONG" if position == 1 else "FLAT"
                    st.metric(get_text('position', lang), position_text)

                with col4:
                    st.metric(get_text('timestamp', lang), pd.Timestamp.now().strftime('%H:%M:%S'))

                # Display strategy-specific indicators
                display_strategy_indicators(info)

                # Price chart
                chart_gen = ChartGenerator()
                fig = chart_gen.plot_strategy_chart(data, pd.DataFrame(), st.session_state.selected_strategy)
                st.plotly_chart(fig, use_container_width=True)

                # Recent data table
                st.subheader(get_text('recent_data', lang))
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
        # Get all stocks for dropdown
        all_stocks = stock_db.stocks

        # Create display format: "SYMBOL - Company Name"
        stock_options = [f"{stock['symbol']} - {stock['name']}" for stock in all_stocks]
        stock_symbols = [stock['symbol'] for stock in all_stocks]

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
            import time
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
        import time
        st.session_state.last_refresh_time = time.time()

    # Real-time quote display (US-005)
    st.divider()
    st.subheader(get_text('current_price', lang))

    # Import KIS broker helper
    from dashboard.kis_broker import get_kis_broker

    # Initialize KIS broker
    broker = get_kis_broker()

    if broker is None:
        # Broker initialization failed (error already shown by get_kis_broker)
        st.warning(get_text('kis_not_available', lang))
        return

    try:
        # Fetch current ticker data
        with st.spinner(get_text('fetching_quote', lang)):
            ticker = broker.fetch_ticker(selected_symbol, overseas=True, market='NASDAQ')

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
        change_color = "🔴" if change_amount >= 0 else "🔵"

        st.info(f"{change_color} {get_text('change_amount', lang)}: {change_sign}${change_amount:.2f} ({change_rate:+.2f}%)")

    except Exception as e:
        # Use centralized error handler (US-009)
        from dashboard.error_handler import handle_kis_broker_error
        handle_kis_broker_error(e, lang=lang, symbol=selected_symbol)

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
        with st.spinner(get_text('loading_chart', lang)):
            ohlcv_df = broker.fetch_ohlcv(
                selected_symbol,
                timeframe='1d',
                limit=selected_period,
                overseas=True,
                market='NASDAQ'
            )

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
