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
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, StochasticStrategy, RSIMACDComboStrategy
from trading_bot.backtester import Backtester
from trading_bot.paper_trader import PaperTrader
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.database import TradingDatabase
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.custom_combo_strategy import CustomComboStrategy
from dashboard.charts import ChartGenerator
import plotly.graph_objects as go
from dashboard.translations import get_text, get_strategy_name, get_strategy_desc
from dashboard.market_hours import MarketHours
from dashboard.stock_symbols import StockSymbolDB
from dashboard.scheduler_manager import SchedulerManager
from dashboard.portfolio_summary import render_portfolio_summary
from dashboard.market_timer import render_market_timer
from dashboard.favorites import render_favorites_widget
from dashboard.session_manager import render_session_manager
import time
from datetime import datetime, time as time_type
from typing import Dict, Any, Optional, List
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
    },
    'RSI+MACD Combo': {
        'class': RSIMACDComboStrategy,
        'params': {
            'rsi_period': {'min': 5, 'max': 30, 'default': 14, 'label': 'RSI Period'},
            'rsi_oversold': {'min': 20, 'max': 40, 'default': 35, 'label': 'RSI Oversold'},
            'rsi_overbought': {'min': 60, 'max': 85, 'default': 70, 'label': 'RSI Overbought'},
            'macd_fast': {'min': 8, 'max': 20, 'default': 12, 'label': 'MACD Fast'},
            'macd_slow': {'min': 20, 'max': 40, 'default': 26, 'label': 'MACD Slow'},
            'macd_signal': {'min': 5, 'max': 15, 'default': 9, 'label': 'MACD Signal'}
        },
        'description': '🔥 기술주 반등 전략: RSI 과매도(35 이하) + MACD 골든크로스 시 BUY, RSI 과매수(70 이상) 또는 MACD 데드크로스 시 SELL'
    }
}


def init_session_state():
    """Initialize session state variables"""
    # Recover zombie sessions on first load
    if 'zombie_recovered' not in st.session_state:
        try:
            db = TradingDatabase()
            recovered = db.recover_zombie_sessions()
            if recovered > 0:
                st.toast(f"⚠️ 비정상 종료된 세션 {recovered}개를 감지하여 'interrupted' 처리했습니다.")
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


def create_strategy(strategy_name: str, params: Dict[str, Any]):
    """Create strategy instance with given parameters"""
    strategy_config = STRATEGY_CONFIGS[strategy_name]
    strategy_class = strategy_config['class']
    return strategy_class(**params)  # type: ignore[operator]


def start_paper_trading(
    strategy_name: str,
    symbols: list,
    initial_capital: float,
    position_size: float,
    strategy_params: Dict[str, Any],
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    enable_stop_loss: bool = True,
    enable_take_profit: bool = True,
    use_custom_combo: bool = False,
    combo_strategies: List[str] = None,
    combo_strategy_params: Dict[str, Dict] = None,
    combo_logic: str = 'MAJORITY',
    combo_weights: List[float] = None
) -> Optional[str]:
    """
    Start paper trading session in background thread

    Args:
        strategy_name: Name of the strategy to use
        symbols: List of stock symbols to trade
        initial_capital: Starting capital
        position_size: Position size fraction (0.1 to 1.0)
        strategy_params: Dictionary of strategy parameters
        stop_loss_pct: Stop loss percentage (0.05 = 5%)
        take_profit_pct: Take profit percentage (0.10 = 10%)
        enable_stop_loss: Enable stop loss feature
        enable_take_profit: Enable take profit feature
        use_custom_combo: Use custom combo strategy
        combo_strategies: List of strategy names for combo
        combo_strategy_params: Parameters for each combo strategy
        combo_logic: Combination logic (AND, OR, MAJORITY, WEIGHTED)
        combo_weights: Weights for each strategy (for WEIGHTED mode)

    Returns:
        session_id if successful, None if failed
    """
    try:
        # Create strategy instance
        strategy: Any

        if use_custom_combo and combo_strategies and len(combo_strategies) >= 2:
            # Create custom combo strategy
            strategy_instances = []
            for strat_name in combo_strategies:
                params = combo_strategy_params.get(strat_name, {})
                if strat_name == 'RSI Strategy':
                    strategy_instances.append(RSIStrategy(**params))
                elif strat_name == 'MACD Strategy':
                    strategy_instances.append(MACDStrategy(**params))
                elif strat_name == 'Moving Average Crossover':
                    strategy_instances.append(MovingAverageCrossover(**params))
                elif strat_name == 'Bollinger Bands':
                    strategy_instances.append(BollingerBandsStrategy(**params))
                elif strat_name == 'Stochastic Oscillator':
                    strategy_instances.append(StochasticStrategy(**params))

            strategy = CustomComboStrategy(
                strategies=strategy_instances,
                strategy_names=combo_strategies,
                combination_logic=combo_logic,
                weights=combo_weights
            )
        else:
            # Create single strategy instance with user-provided parameters
            if strategy_name == 'RSI Strategy':
                strategy = RSIStrategy(**strategy_params)
            elif strategy_name == 'MACD Strategy':
                strategy = MACDStrategy(**strategy_params)
            elif strategy_name == 'Moving Average Crossover':
                strategy = MovingAverageCrossover(**strategy_params)
            elif strategy_name == 'Bollinger Bands':
                strategy = BollingerBandsStrategy(**strategy_params)
            elif strategy_name == 'Stochastic Oscillator':
                strategy = StochasticStrategy(**strategy_params)
            elif strategy_name == 'RSI+MACD Combo':
                strategy = RSIMACDComboStrategy(**strategy_params)
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
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
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


def stop_paper_trading(session_id: Optional[str] = None):
    """
    Stop paper trading session

    Args:
        session_id: Optional session ID to stop. If None, stops current session.
    """
    if session_id:
        # Stop specific session by ID
        db = TradingDatabase()
        db.update_session(session_id, {
            'status': 'stopped',
            'end_time': datetime.now().isoformat()
        })
        st.success(f"✅ 세션 {session_id[:16]}...이 중지되었습니다.")
    elif st.session_state.paper_trader:
        # Stop current session
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


def stop_all_active_sessions():
    """Stop all active paper trading sessions"""
    db = TradingDatabase()
    all_sessions = db.get_all_sessions()

    # Filter active sessions
    active_sessions = [s for s in all_sessions if s['status'] == 'active']

    if not active_sessions:
        st.info("ℹ️ 활성화된 세션이 없습니다.")
        return

    # Stop all active sessions
    stopped_count = 0
    for session in active_sessions:
        db.update_session(session['session_id'], {
            'status': 'stopped',
            'end_time': datetime.now().isoformat()
        })
        stopped_count += 1

    # Also stop current session in session state
    if st.session_state.paper_trader:
        st.session_state.paper_trading_active = False
        st.session_state.paper_trader = None

    st.success(f"✅ {stopped_count}개의 활성 세션이 중지되었습니다.")


def create_equity_comparison_chart(session_ids: list, db: TradingDatabase) -> Optional[go.Figure]:
    """
    Create equity curve comparison chart for selected sessions

    Args:
        session_ids: List of session IDs to compare
        db: TradingDatabase instance

    Returns:
        Plotly figure or None if no data
    """
    if not session_ids:
        return None

    fig = go.Figure()

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    sessions_with_data = 0

    for idx, session_id in enumerate(session_ids):
        # Fetch portfolio snapshots
        snapshots = db.get_session_snapshots(session_id)

        if not snapshots:
            continue

        # Extract data for plotting
        timestamps = [pd.to_datetime(s['timestamp']) for s in snapshots]
        total_values = [s['total_value'] for s in snapshots]

        # Get session info for label
        session = db.get_session_summary(session_id)
        strategy_name = session['strategy_name'] if session else 'Unknown'

        # Plot equity curve
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=total_values,
            mode='lines',
            name=f"{strategy_name} ({session_id[:8]})",
            line=dict(color=colors[idx % len(colors)], width=2),
            hovertemplate='%{y:$,.2f}<br>%{x}<extra></extra>'
        ))

        sessions_with_data += 1

    if sessions_with_data == 0:
        return None

    # Update layout
    fig.update_layout(
        title='수익 곡선 비교 (Equity Curve Comparison)',
        xaxis_title='시간 (Time)',
        yaxis_title='포트폴리오 가치 (Portfolio Value, $)',
        hovermode='x unified',
        template='plotly_white',
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        height=500
    )

    fig.update_yaxes(tickprefix="$", tickformat=",.0f")

    return fig


def sidebar_config():
    """Render configuration sidebar"""
    lang = st.session_state.language

    # ============================================================================
    # SIMPLIFIED SIDEBAR - Only Language and Quick Info
    # ============================================================================
    st.sidebar.title("⚙️ 설정" if lang == 'ko' else "⚙️ Settings")

    # Language Selection - Only thing that stays in sidebar
    st.sidebar.subheader("🌐 " + get_text('language', lang))

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

    # ============================================================================
    # QUICK GUIDE
    # ============================================================================

    # Quick info section
    st.sidebar.subheader("📌 빠른 안내" if lang == 'ko' else "📌 Quick Guide")

    if lang == 'ko':
        st.sidebar.info("""
        **주요 기능**

        🎮 **모의투자**
        실시간 시장 데이터로 모의투자를 실행하세요.

        📊 **전략 & 세션 비교**
        여러 전략과 세션의 성과를 비교하세요.

        📈 **실시간 시세**
        미국 주식의 실시간 시세를 확인하세요.

        📉 **백테스팅**
        과거 데이터로 전략을 테스트하세요.

        🔴 **라이브 모니터**
        실시간 전략 신호를 모니터링하세요.
        """)
    else:
        st.sidebar.info("""
        **Main Features**

        🎮 **Paper Trading**
        Run simulated trading with real market data.

        📊 **Strategy & Session Comparison**
        Compare performance of strategies and sessions.

        📈 **Real-time Quotes**
        Check live quotes for US stocks.

        📉 **Backtesting**
        Test strategies on historical data.

        🔴 **Live Monitor**
        Monitor real-time strategy signals.
        """)

    st.sidebar.markdown("---")

    # Market status (minimal info)
    if lang == 'ko':
        st.sidebar.caption("💡 각 탭에서 필요한 설정을 직접 구성할 수 있습니다.")
    else:
        st.sidebar.caption("💡 Configure settings in each tab as needed.")

    # Initialize market type if not set
    if 'market_type' not in st.session_state:
        st.session_state.market_type = 'stock'

    # Initialize use_simulation if not set
    if 'use_simulation' not in st.session_state:
        st.session_state.use_simulation = False


def backtest_tab():
    """Enhanced backtesting interface"""
    lang = st.session_state.language

    st.header(get_text('backtest_title', lang))

    st.markdown("""
    시뮬레이션 데이터 또는 실제 종목의 과거 데이터로 전략을 테스트하고 성능을 분석합니다.
    """)

    # 프리셋이 적용된 후 다음 렌더링에서 플래그 초기화
    # (사용자가 UI에서 값을 변경할 때 프리셋 값으로 되돌아가지 않도록)
    if st.session_state.get('backtest_preset_just_loaded'):
        st.session_state.backtest_preset_just_loaded = False
        st.session_state.backtest_preset_loaded = False

    # Preset selection section
    st.markdown("---")
    st.subheader("💾 전략 프리셋")

    preset_manager = StrategyPresetManager()
    preset_names = [p['name'] for p in preset_manager.list_presets()]

    if preset_names:
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            selected_preset = st.selectbox(
                "저장된 프리셋 선택",
                ["(새 설정)"] + preset_names,
                key="backtest_preset_select",
                help="Paper Trading에서 저장한 프리셋을 불러옵니다"
            )

        with col2:
            load_preset_btn = st.button(
                "📥 불러오기",
                disabled=(selected_preset == "(새 설정)"),
                key="backtest_load_preset",
                use_container_width=True
            )

        with col3:
            if selected_preset != "(새 설정)":
                preset = preset_manager.load_preset(selected_preset)
                with st.expander("ℹ️ 프리셋 정보"):
                    st.markdown(f"**전략**: {preset['strategy']}")
                    st.markdown(f"**종목**: {', '.join(preset['symbols'][:3])}..." if len(preset['symbols']) > 3 else f"**종목**: {', '.join(preset['symbols'])}")
                    st.markdown(f"**초기 자본**: ${preset['initial_capital']:,.0f}")
                    if preset.get('description'):
                        st.caption(preset['description'])

        # Load preset when button clicked
        if load_preset_btn and selected_preset != "(새 설정)":
            preset = preset_manager.load_preset(selected_preset)

            # 세션 상태에 프리셋 데이터 저장
            st.session_state.backtest_preset_loaded = True
            st.session_state.backtest_preset_just_loaded = True
            st.session_state.backtest_preset_strategy = preset['strategy']
            st.session_state.backtest_preset_params = preset['strategy_params']
            st.session_state.backtest_preset_capital = preset['initial_capital']
            st.session_state.backtest_preset_symbols = preset['symbols']

            st.success(f"✅ 프리셋 '{selected_preset}' 불러오기 완료!")
            st.rerun()

    else:
        st.info("💡 Paper Trading 탭에서 전략을 저장하면 여기서 불러올 수 있습니다.")

    # Configuration section - all in one tab
    st.markdown("---")
    st.subheader("⚙️ 백테스팅 설정")

    col1, col2 = st.columns(2)

    with col1:
        # Strategy selection
        strategy_options = list(STRATEGY_CONFIGS.keys())

        # 프리셋이 로드되었으면 해당 전략을 기본값으로 설정
        default_strategy_index = 0
        if st.session_state.get('backtest_preset_loaded'):
            preset_strategy = st.session_state.backtest_preset_strategy
            if preset_strategy in strategy_options:
                default_strategy_index = strategy_options.index(preset_strategy)

        selected_strategy = st.selectbox(
            "전략 선택",
            options=strategy_options,
            index=default_strategy_index,
            key="backtest_strategy_select"
        )

        # Display strategy description
        st.info(f"ℹ️ {STRATEGY_CONFIGS[selected_strategy]['description']}")

    with col2:
        # Initial capital
        # 프리셋이 로드되었으면 해당 초기 자본을 기본값으로 설정
        default_capital = 10000.0
        if st.session_state.get('backtest_preset_loaded'):
            default_capital = st.session_state.backtest_preset_capital

        initial_capital = st.number_input(
            "초기 자본 ($)",
            min_value=100.0,
            max_value=1000000.0,
            value=default_capital,
            step=1000.0,
            key="backtest_capital"
        )

    # Strategy parameters
    st.markdown("---")
    st.subheader("📐 전략 파라미터")

    strategy_params = {}
    param_config = STRATEGY_CONFIGS[selected_strategy]['params']
    param_cols = st.columns(min(len(param_config), 3))

    # 프리셋 파라미터 가져오기
    preset_params = {}
    if st.session_state.get('backtest_preset_loaded'):
        preset_params = st.session_state.get('backtest_preset_params', {})

    for idx, (param_name, config) in enumerate(param_config.items()):
        with param_cols[idx % 3]:
            # 프리셋에 해당 파라미터가 있으면 그 값을 사용, 없으면 기본값 사용
            default_value = preset_params.get(param_name, config['default'])

            # 범위 내로 제한
            default_value = max(config['min'], min(config['max'], default_value))

            if config.get('step'):
                strategy_params[param_name] = st.slider(
                    config['label'],
                    min_value=config['min'],
                    max_value=config['max'],
                    value=default_value,
                    step=config['step'],
                    key=f"backtest_{param_name}"
                )
            else:
                strategy_params[param_name] = st.slider(
                    config['label'],
                    min_value=config['min'],
                    max_value=config['max'],
                    value=default_value,
                    key=f"backtest_{param_name}"
                )

    # Data configuration
    st.markdown("---")
    st.subheader("📊 데이터 설정")

    # Data source selection
    data_source = st.radio(
        "데이터 소스",
        ["🎲 시뮬레이션 데이터", "📈 실제 종목 (yfinance)"],
        key="backtest_data_source",
        help="시뮬레이션: 빠른 테스트용 가상 데이터 | 실제 종목: Yahoo Finance에서 실제 과거 데이터 조회"
    )

    if data_source == "🎲 시뮬레이션 데이터":
        # Simulation data configuration
        col1, col2 = st.columns(2)

        with col1:
            num_periods = st.number_input(
                "데이터 포인트 수",
                min_value=100,
                max_value=5000,
                value=1000,
                step=100,
                key="backtest_periods",
                help="시뮬레이션 데이터 생성 시 사용할 데이터 포인트 수"
            )

        with col2:
            trend_type = st.selectbox(
                "시장 트렌드",
                options=['bullish', 'bearish', 'sideways', 'volatile'],
                index=0,
                key="backtest_trend",
                help="시뮬레이션 데이터의 트렌드 방향"
            )

    else:  # 실제 종목
        # Real stock data configuration
        col1, col2 = st.columns(2)

        with col1:
            # 프리셋이 로드되었으면 첫 번째 종목을 기본값으로 사용
            default_symbol = "AAPL"
            if st.session_state.get('backtest_preset_loaded'):
                preset_symbols = st.session_state.get('backtest_preset_symbols', [])
                if preset_symbols:
                    default_symbol = preset_symbols[0]

            symbol = st.text_input(
                "종목 심볼",
                value=default_symbol,
                key="backtest_symbol",
                help="미국 주식 심볼 (예: AAPL, MSFT, GOOGL, TSLA, PLTR)"
            ).upper()

            # Symbol validation
            if symbol:
                from dashboard.yfinance_helper import validate_symbol
                if not validate_symbol(symbol):
                    st.warning(f"⚠️ '{symbol}'은(는) 유효하지 않은 종목 심볼입니다.")

        with col2:
            period_option = st.selectbox(
                "조회 기간",
                options=['1개월', '3개월', '6개월', '1년', '2년', '3년', '5년', '최대'],
                index=4,  # 기본값: 2년
                key="backtest_period",
                help="과거 데이터 조회 기간"
            )

            # Period mapping
            period_mapping = {
                '1개월': '1mo',
                '3개월': '3mo',
                '6개월': '6mo',
                '1년': '1y',
                '2년': '2y',
                '3년': '3y',
                '5년': '5y',
                '최대': 'max'
            }
            yf_period = period_mapping[period_option]

    # Run Backtest Button
    st.markdown("---")

    if st.button("🚀 백테스팅 실행", type="primary", use_container_width=True, key="run_backtest_btn"):
        with st.spinner("백테스팅 실행 중..."):
            try:
                # Create strategy instance
                strategy_instance = create_strategy(selected_strategy, strategy_params)

                # Get data based on source
                if data_source == "🎲 시뮬레이션 데이터":
                    # Generate simulation data
                    generator = SimulationDataGenerator(seed=42)
                    df = generator.generate_trend_data(periods=num_periods, trend=trend_type)
                    data_source_label = f"시뮬레이션 ({trend_type}, {num_periods}개)"

                else:  # 실제 종목
                    # Fetch real stock data
                    from dashboard.yfinance_helper import fetch_ohlcv_yfinance, validate_symbol

                    # Validate symbol first
                    if not validate_symbol(symbol):
                        st.error(f"❌ '{symbol}'은(는) 유효하지 않은 종목 심볼입니다.")
                        return

                    # Fetch OHLCV data
                    with st.spinner(f"{symbol} 데이터 조회 중..."):
                        df = fetch_ohlcv_yfinance(symbol, period=yf_period, interval='1d')

                    if df is None or df.empty:
                        st.error(f"❌ {symbol} 데이터를 조회할 수 없습니다.")
                        return

                    data_source_label = f"{symbol} (yfinance, {period_option})"

                    # Display data info
                    st.info(f"📊 조회된 데이터: {len(df)}개 일봉 ({df['timestamp'].min().date()} ~ {df['timestamp'].max().date()})")

                if df.empty:
                    st.error("데이터 생성/조회에 실패했습니다.")
                    return

                # Run backtest
                backtester = Backtester(
                    strategy=strategy_instance,
                    initial_capital=initial_capital
                )
                results = backtester.run(df)

                # Store results
                st.session_state.backtest_results = {
                    'results': results,
                    'backtester': backtester,
                    'data': df,
                    'strategy_name': selected_strategy,
                    'strategy_instance': strategy_instance,  # 전략 인스턴스 저장
                    'data_source': data_source_label  # 데이터 소스 저장
                }

                st.success("✅ 백테스팅이 완료되었습니다!")

            except Exception as e:
                st.error(f"❌ 백테스팅 실행 중 오류 발생: {e}")
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
    strategy_instance = backtest_data.get('strategy_instance', backtester.strategy)  # 전략 인스턴스 가져오기
    data_source = backtest_data.get('data_source', '알 수 없음')  # 데이터 소스

    # Data source info
    st.info(f"📊 **데이터 소스**: {data_source}")

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
    data_with_indicators = strategy_instance.calculate_indicators(data)

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


def paper_trading_comparison_tab():
    """Paper trading sessions comparison interface"""
    lang = st.session_state.language

    st.header("📊 Strategy Comparison")

    st.markdown("""
    과거 모의투자 세션들의 성과를 비교합니다. 여러 전략과 종목 조합의 결과를 한눈에 확인하세요.
    """)

    # Initialize database
    try:
        db = TradingDatabase()
        all_sessions = db.get_all_sessions()
    except Exception as e:
        st.error(f"❌ 데이터베이스 연결 실패: {e}")
        return

    if not all_sessions:
        st.info("ℹ️ 아직 완료된 모의투자 세션이 없습니다. Paper Trading 탭에서 모의투자를 시작해보세요!")
        return

    # Session selection
    st.subheader("📋 세션 선택")

    # Create session display names
    session_options = {}
    for session in all_sessions:
        session_id = session['session_id']
        strategy = session['strategy_name']
        start_time = session['start_time'][:16] if session['start_time'] else 'N/A'
        status = session['status']

        display_name = f"{session_id} | {strategy} | {start_time} | {status}"
        session_options[display_name] = session_id

    selected_displays = st.multiselect(
        "비교할 세션을 선택하세요 (여러 개 선택 가능)",
        options=list(session_options.keys()),
        default=list(session_options.keys())[:min(3, len(session_options))],
        help="최대 10개까지 선택 가능합니다"
    )

    if not selected_displays:
        st.warning("⚠️ 비교할 세션을 최소 1개 이상 선택해주세요.")
        return

    # Get selected session IDs
    selected_session_ids = [session_options[display] for display in selected_displays]

    # Filter sessions
    selected_sessions = [s for s in all_sessions if s['session_id'] in selected_session_ids]

    # Comparison table
    st.markdown("---")
    st.subheader("📊 성과 비교")

    comparison_data = []
    for session in selected_sessions:
        # Get detailed session info
        summary = db.get_session_summary(session['session_id'])

        if summary:
            comparison_data.append({
                'Session ID': session['session_id'],
                'Strategy': session['strategy_name'],
                'Start Time': session['start_time'][:16] if session['start_time'] else 'N/A',
                'End Time': session['end_time'][:16] if session['end_time'] else 'Running',
                'Initial Capital': f"${session['initial_capital']:,.2f}",
                'Final Capital': f"${session['final_capital']:,.2f}" if session['final_capital'] else 'N/A',
                'Return %': f"{session['total_return']:.2f}%" if session['total_return'] is not None else 'N/A',
                'Sharpe Ratio': f"{session['sharpe_ratio']:.2f}" if session['sharpe_ratio'] is not None else 'N/A',
                'Max Drawdown %': f"{session['max_drawdown']:.2f}%" if session['max_drawdown'] is not None else 'N/A',
                'Win Rate %': f"{session['win_rate']:.2f}%" if session['win_rate'] is not None else 'N/A',
                'Status': session['status']
            })

    if comparison_data:
        comparison_df = pd.DataFrame(comparison_data)

        # Display table
        st.dataframe(comparison_df, use_container_width=True)

        # Find best strategy by win rate
        st.markdown("---")
        st.subheader("🏆 최고 성과")

        completed_sessions = [s for s in selected_sessions if s['status'] == 'completed' and s['win_rate'] is not None]

        if completed_sessions:
            best_by_return = max(completed_sessions, key=lambda x: x['total_return'] if x['total_return'] is not None else -float('inf'))
            best_by_win_rate = max(completed_sessions, key=lambda x: x['win_rate'] if x['win_rate'] is not None else 0)
            best_by_sharpe = max(completed_sessions, key=lambda x: x['sharpe_ratio'] if x['sharpe_ratio'] is not None else -float('inf'))

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "최고 수익률",
                    f"{best_by_return['total_return']:.2f}%" if best_by_return['total_return'] else 'N/A',
                    delta=f"{best_by_return['strategy_name']}"
                )

            with col2:
                st.metric(
                    "최고 승률",
                    f"{best_by_win_rate['win_rate']:.2f}%" if best_by_win_rate['win_rate'] else 'N/A',
                    delta=f"{best_by_win_rate['strategy_name']}"
                )

            with col3:
                st.metric(
                    "최고 샤프 비율",
                    f"{best_by_sharpe['sharpe_ratio']:.2f}" if best_by_sharpe['sharpe_ratio'] else 'N/A',
                    delta=f"{best_by_sharpe['strategy_name']}"
                )
        else:
            st.info("ℹ️ 완료된 세션이 없어 최고 성과를 표시할 수 없습니다.")

        # Equity curve comparison chart
        st.markdown("---")
        st.subheader("📈 수익 곡선 비교")

        fig = create_equity_comparison_chart(selected_session_ids, db)

        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("ℹ️ 선택한 세션에 포트폴리오 스냅샷 데이터가 없습니다. 모의투자를 실행하면 데이터가 생성됩니다.")

    else:
        st.warning("⚠️ 선택한 세션에 대한 데이터가 없습니다.")


def strategy_comparison_tab():
    """Strategy comparison interface (legacy - for backtesting)"""
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

    # Strategy Preset Management Section
    st.markdown("---")
    st.subheader("💾 전략 프리셋 관리")

    # Initialize preset manager
    preset_manager = StrategyPresetManager()

    # Initialize session state for loaded preset
    if 'loaded_preset' not in st.session_state:
        st.session_state.loaded_preset = None

    col_preset1, col_preset2 = st.columns([2, 1])

    with col_preset1:
        # Load existing presets
        st.write("**📂 저장된 프리셋 불러오기**")

        all_presets = preset_manager.list_presets()

        if all_presets:
            preset_options = {p['name']: p for p in all_presets}
            preset_names = list(preset_options.keys())

            selected_preset_name = st.selectbox(
                "프리셋 선택",
                options=["-- 선택하세요 --"] + preset_names,
                key="preset_selector"
            )

            if selected_preset_name != "-- 선택하세요 --":
                col_load, col_delete = st.columns([1, 1])

                with col_load:
                    if st.button("📥 불러오기", key="load_preset_btn", use_container_width=True):
                        loaded = preset_manager.load_preset(selected_preset_name)
                        if loaded:
                            st.session_state.loaded_preset = loaded
                            st.success(f"✅ '{selected_preset_name}' 프리셋을 불러왔습니다!")
                            st.rerun()

                with col_delete:
                    if st.button("🗑️ 삭제", key="delete_preset_btn", type="secondary", use_container_width=True):
                        if preset_manager.delete_preset(selected_preset_name):
                            st.success(f"✅ '{selected_preset_name}' 프리셋이 삭제되었습니다!")
                            st.session_state.loaded_preset = None
                            st.rerun()

                # Show preset details
                if selected_preset_name in preset_options:
                    preset = preset_options[selected_preset_name]
                    with st.expander("📋 프리셋 상세 정보", expanded=False):
                        st.write(f"**전략:** {preset['strategy']}")
                        st.write(f"**종목:** {', '.join(preset['symbols']) if preset['symbols'] else '없음'}")
                        st.write(f"**초기 자본:** ${preset['initial_capital']:,.2f}")
                        st.write(f"**포지션 크기:** {preset['position_size']:.0%}")
                        st.write(f"**손절매:** {preset['stop_loss_pct']:.0%} ({'활성' if preset['enable_stop_loss'] else '비활성'})")
                        st.write(f"**익절매:** {preset['take_profit_pct']:.0%} ({'활성' if preset['enable_take_profit'] else '비활성'})")
                        st.write(f"**파라미터:** {preset['strategy_params']}")
                        if preset.get('description'):
                            st.write(f"**설명:** {preset['description']}")
                        st.caption(f"생성일: {preset.get('created_at', 'N/A')[:19]}")
                        if preset.get('last_used'):
                            st.caption(f"최근 사용: {preset['last_used'][:19]}")
        else:
            st.info("💡 저장된 프리셋이 없습니다. 설정을 구성한 후 저장해보세요!")

    with col_preset2:
        # Save current settings as preset
        st.write("**💾 현재 설정 저장**")

        preset_name = st.text_input(
            "프리셋 이름",
            placeholder="예: 보수적 RSI 전략",
            key="new_preset_name"
        )

        preset_description = st.text_area(
            "설명 (선택사항)",
            placeholder="이 프리셋에 대한 간단한 설명을 입력하세요",
            key="preset_description",
            height=100
        )

        # Note: Save button will be added after configuration section
        # so we can capture all the current settings
        st.info("ℹ️ 아래 설정을 완료한 후 이 섹션으로 돌아와서 프리셋을 저장하세요")

    st.markdown("---")

    # Configuration Section
    st.subheader("⚙️ 모의투자 설정")

    col1, col2 = st.columns(2)

    with col1:
        # Strategy selector - use all strategies from STRATEGY_CONFIGS
        strategy_options = list(STRATEGY_CONFIGS.keys())

        # Check if preset is loaded and use its strategy
        default_strategy_index = 0
        if st.session_state.loaded_preset:
            preset_strategy = st.session_state.loaded_preset.get('strategy')
            if preset_strategy in strategy_options:
                default_strategy_index = strategy_options.index(preset_strategy)

        selected_strategy = st.selectbox(
            "전략 선택",
            options=strategy_options,
            index=default_strategy_index,
            help="모의투자에 사용할 전략을 선택하세요"
        )

    # Custom Combo Strategy Builder
    st.markdown("---")
    use_custom_combo = st.checkbox(
        "🎨 커스텀 콤보 전략 만들기",
        value=False,
        help="여러 전략을 조합하여 나만의 전략을 만들 수 있습니다"
    )

    # Initialize combo variables
    selected_combo_strategies = []
    combo_logic_name = 'MAJORITY'
    combo_weights = []
    combo_strategy_params = {}

    if use_custom_combo:
        with st.expander("⚙️ 커스텀 콤보 전략 설정", expanded=True):
            st.info("💡 여러 전략을 선택하고 조합 로직을 설정하여 커스텀 전략을 만드세요!")

            # Strategy selection for combo
            combo_col1, combo_col2 = st.columns(2)

            with combo_col1:
                selected_combo_strategies = st.multiselect(
                    "조합할 전략 선택 (최소 2개)",
                    options=[s for s in strategy_options if s != 'RSI+MACD Combo'],  # Exclude existing combo
                    default=['RSI Strategy', 'MACD Strategy'],
                    help="최소 2개 이상의 전략을 선택하세요"
                )

            with combo_col2:
                combo_logic = st.selectbox(
                    "조합 로직",
                    options=['AND (모두 동의)', 'OR (하나라도)', 'MAJORITY (과반수)', 'WEIGHTED (가중치)'],
                    index=2,
                    help="전략 신호를 어떻게 조합할지 선택하세요"
                )

            # Extract logic name
            combo_logic_name = combo_logic.split()[0]

            # Weights for WEIGHTED mode
            combo_weights = []
            if combo_logic_name == 'WEIGHTED' and len(selected_combo_strategies) > 0:
                st.markdown("**가중치 설정**")
                weight_cols = st.columns(len(selected_combo_strategies))
                for idx, strat_name in enumerate(selected_combo_strategies):
                    with weight_cols[idx]:
                        weight = st.slider(
                            strat_name.split()[0],
                            min_value=0.0,
                            max_value=1.0,
                            value=1.0 / len(selected_combo_strategies),
                            step=0.05,
                            key=f"combo_weight_{idx}"
                        )
                        combo_weights.append(weight)

                # Show normalized weights
                total_weight = sum(combo_weights)
                if total_weight > 0:
                    normalized_weights = [w / total_weight for w in combo_weights]
                    st.caption(f"정규화된 가중치: {', '.join([f'{w:.2f}' for w in normalized_weights])}")

            # Parameters for each strategy
            if len(selected_combo_strategies) >= 2:
                st.markdown("---")
                st.markdown("**각 전략의 파라미터 설정**")

                combo_strategy_params = {}
                for strat_name in selected_combo_strategies:
                    with st.expander(f"📐 {strat_name}", expanded=False):
                        strat_config = STRATEGY_CONFIGS[strat_name]
                        params = {}

                        param_cols = st.columns(min(len(strat_config['params']), 3))
                        for idx, (param_name, param_config) in enumerate(strat_config['params'].items()):
                            with param_cols[idx % 3]:
                                if param_config.get('step'):
                                    params[param_name] = st.slider(
                                        param_config['label'],
                                        min_value=param_config['min'],
                                        max_value=param_config['max'],
                                        value=float(param_config['default']),
                                        step=param_config['step'],
                                        key=f"combo_{strat_name}_{param_name}"
                                    )
                                else:
                                    params[param_name] = st.slider(
                                        param_config['label'],
                                        min_value=param_config['min'],
                                        max_value=param_config['max'],
                                        value=int(param_config['default']),
                                        key=f"combo_{strat_name}_{param_name}"
                                    )

                        combo_strategy_params[strat_name] = params

                # Preview combo strategy name
                strategy_short = '+'.join([name.split()[0][:3] for name in selected_combo_strategies])
                logic_short = {'AND': 'ALL', 'OR': 'ANY', 'MAJORITY': 'MAJ', 'WEIGHTED': 'WGT'}
                combo_name = f"Custom_{logic_short.get(combo_logic_name, 'CMB')}_{strategy_short}"
                st.success(f"✅ 커스텀 전략 이름: **{combo_name}**")

            elif len(selected_combo_strategies) < 2:
                st.warning("⚠️ 최소 2개 이상의 전략을 선택해주세요")

    st.markdown("---")

    with col2:
        # Initialize favorites in session state
        if 'favorite_stocks' not in st.session_state:
            st.session_state.favorite_stocks = ['AAPL', 'MSFT', 'GOOGL']  # Default favorites

        # Load preset symbols into favorites if available
        if st.session_state.loaded_preset:
            preset_symbols = st.session_state.loaded_preset.get('symbols', [])
            if preset_symbols:
                # Add preset symbols to favorites if not already there
                for symbol in preset_symbols:
                    if symbol not in st.session_state.favorite_stocks:
                        st.session_state.favorite_stocks.append(symbol)

        # Stock Symbol Database
        stock_db = StockSymbolDB()

        # Stock selection - Tab Style (Simple & Clean)
        st.write("**종목 선택**")

        # Initialize temporary selection state
        if 'temp_selected_stocks' not in st.session_state:
            st.session_state.temp_selected_stocks = []

        # Create tabs for different categories
        tab1, tab2, tab3, tab4 = st.tabs(["인기 종목", "섹터별", "ETF", "전체 검색"])

        # Tab 1: Popular stocks
        with tab1:
            st.caption("자주 거래되는 인기 종목")

            # Popular stock presets
            popular_presets = {
                'FAANG': stock_db.get_preset('FAANG'),
                'Magnificent 7': stock_db.get_preset('Magnificent 7'),
                'Tech Giants': stock_db.get_preset('Tech Giants'),
                'Semiconductors': stock_db.get_preset('Semiconductors'),
            }

            for preset_name, symbols in popular_presets.items():
                with st.expander(f"{preset_name} ({len(symbols)}개)", expanded=(preset_name == 'FAANG')):
                    for symbol in symbols:
                        stock_info = stock_db.get_by_symbol(symbol)
                        if stock_info:
                            is_checked = symbol in st.session_state.temp_selected_stocks
                            if st.checkbox(
                                f"{symbol} - {stock_info['name']}",
                                value=is_checked,
                                key=f"pop_{preset_name}_{symbol}"
                            ):
                                if symbol not in st.session_state.temp_selected_stocks:
                                    st.session_state.temp_selected_stocks.append(symbol)
                            else:
                                if symbol in st.session_state.temp_selected_stocks:
                                    st.session_state.temp_selected_stocks.remove(symbol)

        # Tab 2: By sector
        with tab2:
            st.caption("섹터별로 종목 선택")

            sectors = [s for s in stock_db.get_all_sectors() if s != 'ETF']
            selected_sector = st.selectbox(
                "섹터 선택",
                options=sectors,
                key="sector_select_tab"
            )

            if selected_sector:
                sector_stocks = stock_db.get_by_sector(selected_sector)
                st.caption(f"{len(sector_stocks)}개 종목")

                # Add "Select All" button
                col_a, col_b = st.columns([1, 4])
                with col_a:
                    if st.button("전체 선택", key=f"select_all_{selected_sector}"):
                        for stock in sector_stocks:
                            if stock['symbol'] not in st.session_state.temp_selected_stocks:
                                st.session_state.temp_selected_stocks.append(stock['symbol'])
                        st.rerun()

                st.markdown("---")

                for stock in sector_stocks:
                    is_checked = stock['symbol'] in st.session_state.temp_selected_stocks
                    if st.checkbox(
                        f"{stock['symbol']} - {stock['name']}",
                        value=is_checked,
                        key=f"sector_{stock['symbol']}"
                    ):
                        if stock['symbol'] not in st.session_state.temp_selected_stocks:
                            st.session_state.temp_selected_stocks.append(stock['symbol'])
                    else:
                        if stock['symbol'] in st.session_state.temp_selected_stocks:
                            st.session_state.temp_selected_stocks.remove(stock['symbol'])

        # Tab 3: ETFs
        with tab3:
            st.caption("주요 ETF 선택")

            etf_categories = {
                'Index ETFs': stock_db.get_preset('Index ETFs'),
                'Sector ETFs': stock_db.get_preset('Sector ETFs'),
            }

            # Also get all ETFs from database
            all_etfs = stock_db.get_by_sector('ETF')
            etf_symbols = [e['symbol'] for e in all_etfs]

            for category_name, symbols in etf_categories.items():
                with st.expander(f"{category_name} ({len(symbols)}개)", expanded=True):
                    for symbol in symbols:
                        stock_info = stock_db.get_by_symbol(symbol)
                        if stock_info:
                            is_checked = symbol in st.session_state.temp_selected_stocks
                            if st.checkbox(
                                f"{symbol} - {stock_info['name']}",
                                value=is_checked,
                                key=f"etf_{category_name}_{symbol}"
                            ):
                                if symbol not in st.session_state.temp_selected_stocks:
                                    st.session_state.temp_selected_stocks.append(symbol)
                            else:
                                if symbol in st.session_state.temp_selected_stocks:
                                    st.session_state.temp_selected_stocks.remove(symbol)

        # Tab 4: Search all stocks
        with tab4:
            st.caption("전체 종목에서 검색")

            search_query = st.text_input(
                "검색",
                placeholder="심볼 또는 회사명 입력 (예: AAPL, Apple, Tesla...)",
                key="paper_stock_search_tab"
            )

            if search_query:
                search_results = stock_db.search(search_query)

                if search_results:
                    st.caption(f"{len(search_results)}개 종목 발견")

                    for stock in search_results[:20]:  # Show up to 20 results
                        is_checked = stock['symbol'] in st.session_state.temp_selected_stocks
                        if st.checkbox(
                            f"{stock['symbol']} - {stock['name']} ({stock['sector']})",
                            value=is_checked,
                            key=f"search_{stock['symbol']}"
                        ):
                            if stock['symbol'] not in st.session_state.temp_selected_stocks:
                                st.session_state.temp_selected_stocks.append(stock['symbol'])
                        else:
                            if stock['symbol'] in st.session_state.temp_selected_stocks:
                                st.session_state.temp_selected_stocks.remove(stock['symbol'])
                else:
                    st.caption("검색 결과가 없습니다")
            else:
                st.info("심볼이나 회사명을 입력하여 검색하세요")

        # Add selected stocks to favorites
        st.markdown("---")
        col_add, col_clear = st.columns([3, 1])
        with col_add:
            if st.session_state.temp_selected_stocks:
                st.caption(f"선택됨: {len(st.session_state.temp_selected_stocks)}개")
                if st.button("선택한 종목 즐겨찾기에 추가", type="primary"):
                    added_count = 0
                    for symbol in st.session_state.temp_selected_stocks:
                        if symbol not in st.session_state.favorite_stocks:
                            st.session_state.favorite_stocks.append(symbol)
                            added_count += 1

                    st.session_state.temp_selected_stocks = []

                    if added_count > 0:
                        st.success(f"{added_count}개 종목을 즐겨찾기에 추가했습니다")
                        st.rerun()
                    else:
                        st.info("모든 종목이 이미 즐겨찾기에 있습니다")
            else:
                st.caption("선택된 종목이 없습니다")

        with col_clear:
            if st.session_state.temp_selected_stocks:
                if st.button("선택 초기화"):
                    st.session_state.temp_selected_stocks = []
                    st.rerun()

        # Favorites section
        st.markdown("---")
        st.write("**즐겨찾기**")

        col_fav1, col_fav2 = st.columns([3, 1])
        with col_fav1:
            if st.session_state.favorite_stocks:
                st.caption(f"{len(st.session_state.favorite_stocks)}개 종목")
            else:
                st.caption("즐겨찾기가 비어있습니다")
        with col_fav2:
            if st.button("전체 삭제", key="clear_favorites", disabled=not st.session_state.favorite_stocks):
                st.session_state.favorite_stocks = []
                st.rerun()

        # Select stocks for trading from favorites
        if st.session_state.favorite_stocks:
            # Use preset symbols as default if available
            default_symbols = [st.session_state.favorite_stocks[0]] if st.session_state.favorite_stocks else []
            if st.session_state.loaded_preset:
                preset_symbols = st.session_state.loaded_preset.get('symbols', [])
                # Only use symbols that exist in favorites
                default_symbols = [s for s in preset_symbols if s in st.session_state.favorite_stocks]
                if not default_symbols and st.session_state.favorite_stocks:
                    default_symbols = [st.session_state.favorite_stocks[0]]

            selected_symbols = st.multiselect(
                "거래할 종목 선택",
                options=st.session_state.favorite_stocks,
                default=default_symbols,
                help="즐겨찾기에서 거래할 종목을 선택하세요 (최대 7개 권장)",
                format_func=lambda x: f"{x} - {stock_db.get_by_symbol(x)['name'][:25] if stock_db.get_by_symbol(x) else x}"
            )
        else:
            st.info("위의 탭에서 종목을 선택한 후 '즐겨찾기에 추가' 버튼을 클릭하세요")
            selected_symbols = []

    # Additional configuration column
    st.markdown("---")
    col3, col4 = st.columns(2)

    with col3:
        # Initial capital input - use preset value if available
        default_capital = 10000.0
        if st.session_state.loaded_preset:
            default_capital = st.session_state.loaded_preset.get('initial_capital', 10000.0)

        initial_capital = st.number_input(
            "초기 자본 ($)",
            min_value=1000.0,
            max_value=1000000.0,
            value=default_capital,
            step=1000.0,
            help="모의투자 시작 자본금"
        )

    with col4:
        # Position size slider - use preset value if available
        default_position = 0.95
        if st.session_state.loaded_preset:
            default_position = st.session_state.loaded_preset.get('position_size', 0.95)

        position_size = st.slider(
            "포지션 크기",
            min_value=0.1,
            max_value=1.0,
            value=default_position,
            step=0.05,
            help="각 거래에 사용할 자본 비율 (0.1 = 10%, 1.0 = 100%)"
        )

    # Risk Management Section
    st.markdown("---")
    st.subheader("🛡️ 리스크 관리")

    col1, col2, col3, col4 = st.columns(4)

    # Load risk management defaults from preset if available
    default_enable_stop_loss = True
    default_stop_loss_pct = 5.0
    default_enable_take_profit = True
    default_take_profit_pct = 10.0

    if st.session_state.loaded_preset:
        default_enable_stop_loss = st.session_state.loaded_preset.get('enable_stop_loss', True)
        default_stop_loss_pct = st.session_state.loaded_preset.get('stop_loss_pct', 0.05) * 100
        default_enable_take_profit = st.session_state.loaded_preset.get('enable_take_profit', True)
        default_take_profit_pct = st.session_state.loaded_preset.get('take_profit_pct', 0.10) * 100

    with col1:
        enable_stop_loss = st.checkbox(
            "손절매 활성화",
            value=default_enable_stop_loss,
            help="일정 손실 시 자동 매도"
        )

    with col2:
        stop_loss_pct = st.slider(
            "손절매 (%)",
            min_value=1.0,
            max_value=10.0,
            value=default_stop_loss_pct,
            step=0.5,
            disabled=not enable_stop_loss,
            help="손실이 이 비율에 도달하면 자동 매도 (예: 5% = -5% 손실 시 매도)"
        ) / 100.0  # Convert to decimal

    with col3:
        enable_take_profit = st.checkbox(
            "익절매 활성화",
            value=default_enable_take_profit,
            help="일정 수익 시 자동 매도"
        )

    with col4:
        take_profit_pct = st.slider(
            "익절매 (%)",
            min_value=2.0,
            max_value=20.0,
            value=default_take_profit_pct,
            step=1.0,
            disabled=not enable_take_profit,
            help="수익이 이 비율에 도달하면 자동 매도 (예: 10% = +10% 수익 시 매도)"
        ) / 100.0  # Convert to decimal

    # Show risk/reward ratio
    if enable_stop_loss and enable_take_profit:
        risk_reward_ratio = take_profit_pct / stop_loss_pct
        st.info(f"📊 리스크/보상 비율: 1:{risk_reward_ratio:.1f} (손실 ${stop_loss_pct*100:.1f}% 대비 수익 ${take_profit_pct*100:.1f}%)")

    # Strategy Parameters Section
    st.markdown("---")
    st.subheader("📐 전략 파라미터")

    # Get strategy config
    strategy_config = STRATEGY_CONFIGS.get(selected_strategy, {})
    strategy_params_config = strategy_config.get('params', {})

    # Create parameters input dynamically
    strategy_params = {}
    if strategy_params_config:
        # Get preset strategy params if available
        preset_params = {}
        if st.session_state.loaded_preset:
            preset_params = st.session_state.loaded_preset.get('strategy_params', {})

        # Create columns for parameter inputs
        param_cols = st.columns(min(len(strategy_params_config), 3))

        for idx, (param_name, param_config) in enumerate(strategy_params_config.items()):
            # Use preset value if available, otherwise use default
            default_value = preset_params.get(param_name, param_config['default'])

            with param_cols[idx % 3]:
                if param_config.get('step'):
                    # Float parameter
                    strategy_params[param_name] = st.slider(
                        param_config['label'],
                        min_value=param_config['min'],
                        max_value=param_config['max'],
                        value=float(default_value),
                        step=param_config['step'],
                        key=f"paper_{param_name}"
                    )
                else:
                    # Integer parameter
                    strategy_params[param_name] = st.slider(
                        param_config['label'],
                        min_value=param_config['min'],
                        max_value=param_config['max'],
                        value=int(default_value),
                        key=f"paper_{param_name}"
                    )

        # Display strategy description
        st.info(f"ℹ️ {strategy_config.get('description', '')}")
    else:
        st.warning("⚠️ 선택한 전략의 파라미터 설정이 없습니다.")

    # Save Preset Button
    st.markdown("---")
    st.subheader("💾 현재 설정을 프리셋으로 저장")

    col_save1, col_save2 = st.columns([3, 1])

    with col_save1:
        # Retrieve preset name and description from earlier inputs
        preset_name_input = st.session_state.get('new_preset_name', '')
        preset_desc_input = st.session_state.get('preset_description', '')

        if preset_name_input:
            st.info(f"📝 프리셋 이름: **{preset_name_input}**")
            if preset_desc_input:
                st.caption(f"설명: {preset_desc_input}")
        else:
            st.warning("⚠️ 위 '전략 프리셋 관리' 섹션에서 프리셋 이름을 입력하세요")

    with col_save2:
        save_preset_btn = st.button(
            "💾 프리셋 저장",
            type="primary",
            use_container_width=True,
            disabled=not preset_name_input
        )

        if save_preset_btn:
            # Save current configuration as preset
            success = preset_manager.save_preset(
                name=preset_name_input,
                strategy=selected_strategy,
                strategy_params=strategy_params,
                initial_capital=initial_capital,
                position_size=position_size,
                symbols=selected_symbols,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                enable_stop_loss=enable_stop_loss,
                enable_take_profit=enable_take_profit,
                description=preset_desc_input
            )

            if success:
                st.success(f"✅ '{preset_name_input}' 프리셋이 저장되었습니다!")
                # Clear the input fields
                st.session_state.new_preset_name = ""
                st.session_state.preset_description = ""
                st.rerun()
            else:
                st.error("❌ 프리셋 저장에 실패했습니다.")

    # Validation
    if not selected_symbols:
        st.warning("⚠️ 최소 1개 이상의 종목을 선택해주세요.")
        return

    st.markdown("---")

    # Session Management Section
    with st.expander("📊 실행 중인 세션 관리", expanded=False):
        db = TradingDatabase()
        all_sessions = db.get_all_sessions()
        active_sessions = [s for s in all_sessions if s['status'] == 'active']

        if active_sessions:
            st.write(f"**활성 세션: {len(active_sessions)}개**")

            for session in active_sessions:
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    session_info = f"**{session['strategy_name']}** | "
                    session_info += f"시작: {session['start_time'][11:19]} | "
                    session_info += f"자본: ${session['initial_capital']:,.0f}"
                    st.write(session_info)
                    st.caption(f"Session ID: {session['session_id']}")

                with col2:
                    if st.button("📈 상세", key=f"detail_{session['session_id']}"):
                        # Show session details
                        summary = db.get_session_summary(session['session_id'])
                        trades = db.get_session_trades(session['session_id'])
                        st.write(f"거래 수: {len(trades)}")
                        if summary.get('final_capital'):
                            st.write(f"현재 자본: ${summary['final_capital']:,.2f}")

                with col3:
                    if st.button("⏹️ 중지", key=f"stop_{session['session_id']}", type="secondary"):
                        stop_paper_trading(session['session_id'])
                        st.rerun()

                st.markdown("---")

            # Bulk stop button
            if st.button("🗑️ 모든 세션 중지", type="secondary", use_container_width=True):
                stop_all_active_sessions()
                st.rerun()
        else:
            st.info("ℹ️ 현재 활성화된 세션이 없습니다.")

    st.markdown("---")

    # Control Section
    st.subheader("🎮 모의투자 제어")

    # Initialize session state for paper trading
    if 'paper_trading_active' not in st.session_state:
        st.session_state.paper_trading_active = False
    if 'paper_trader' not in st.session_state:
        st.session_state.paper_trader = None
    if 'paper_auto_refresh' not in st.session_state:
        st.session_state.paper_auto_refresh = False

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
        # Prepare custom combo parameters
        combo_strats = selected_combo_strategies if use_custom_combo else None
        combo_params = combo_strategy_params if use_custom_combo else None
        combo_log = combo_logic_name if use_custom_combo else 'MAJORITY'
        combo_wts = combo_weights if (use_custom_combo and combo_logic_name == 'WEIGHTED') else None

        session_id = start_paper_trading(
            strategy_name=selected_strategy,
            symbols=selected_symbols,
            initial_capital=initial_capital,
            position_size=position_size,
            strategy_params=strategy_params,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
            use_custom_combo=use_custom_combo,
            combo_strategies=combo_strats,
            combo_strategy_params=combo_params,
            combo_logic=combo_log,
            combo_weights=combo_wts
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

        # Auto-refresh control
        col1, col2 = st.columns([1, 3])
        with col1:
            auto_refresh = st.checkbox(
                "자동 새로고침",
                value=st.session_state.paper_auto_refresh,
                help="10초마다 포트폴리오를 자동으로 업데이트합니다",
                key="paper_auto_refresh_checkbox"
            )
            st.session_state.paper_auto_refresh = auto_refresh
        with col2:
            if st.button("🔄 수동 새로고침", key="manual_refresh_portfolio"):
                st.rerun()

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

                # Auto-refresh trigger (only if enabled)
                if st.session_state.paper_auto_refresh:
                    st.markdown("---")
                    st.caption("🔄 자동 새로고침 활성화: 10초마다 업데이트")
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

    st.markdown("""
    시뮬레이션 데이터로 전략 신호를 실시간으로 모니터링합니다.
    실제 시장 데이터 모니터링은 '모의투자' 탭을 사용하세요.
    """)

    # Configuration section
    st.markdown("---")
    st.subheader("⚙️ 모니터링 설정")

    col1, col2 = st.columns(2)

    with col1:
        # Strategy selection
        strategy_options = list(STRATEGY_CONFIGS.keys())
        selected_strategy = st.selectbox(
            "전략 선택",
            options=strategy_options,
            index=0,
            key="monitor_strategy_select"
        )

    with col2:
        # Number of data points
        num_points = st.number_input(
            "데이터 포인트 수",
            min_value=50,
            max_value=500,
            value=100,
            key="monitor_points"
        )

    # Strategy parameters
    strategy_params = {}
    param_config = STRATEGY_CONFIGS[selected_strategy]['params']
    param_cols = st.columns(min(len(param_config), 3))

    for idx, (param_name, config) in enumerate(param_config.items()):
        with param_cols[idx % 3]:
            if config.get('step'):
                strategy_params[param_name] = st.slider(
                    config['label'],
                    min_value=config['min'],
                    max_value=config['max'],
                    value=config['default'],
                    step=config['step'],
                    key=f"monitor_{param_name}"
                )
            else:
                strategy_params[param_name] = st.slider(
                    config['label'],
                    min_value=config['min'],
                    max_value=config['max'],
                    value=config['default'],
                    key=f"monitor_{param_name}"
                )

    st.markdown("---")

    # Generate and display signal
    if st.button("🔄 신호 생성", type="primary", use_container_width=True, key="generate_signal_btn"):
        with st.spinner("신호 생성 중..."):
            try:
                # Create strategy instance
                strategy_instance = create_strategy(selected_strategy, strategy_params)

                # Generate simulation data
                generator = SimulationDataGenerator(seed=42)
                df = generator.generate_ohlcv(periods=num_points)

                if df.empty:
                    st.error("데이터 생성에 실패했습니다.")
                    return

                # Calculate indicators and signals
                data = strategy_instance.calculate_indicators(df)
                signal, info = strategy_instance.get_current_signal(df)

                # Display current signal
                st.subheader(f"📊 현재 신호 - {selected_strategy}")

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("현재가", f"${info.get('close', 0):.2f}")

                with col2:
                    signal_text = "🟢 BUY" if signal == 1 else "🔴 SELL" if signal == -1 else "⚪ HOLD"
                    st.metric("신호", signal_text)

                with col3:
                    position = info.get('position', 0)
                    position_text = "LONG" if position == 1 else "FLAT"
                    st.metric("포지션", position_text)

                with col4:
                    st.metric("타임스탬프", pd.Timestamp.now().strftime('%H:%M:%S'))

                # Display strategy-specific indicators
                st.markdown("---")
                st.subheader("📈 지표 상세")
                display_strategy_indicators(info)

                # Price chart
                st.markdown("---")
                st.subheader("📉 차트")
                chart_gen = ChartGenerator()
                fig = chart_gen.plot_strategy_chart(data, pd.DataFrame(), selected_strategy)
                st.plotly_chart(fig, use_container_width=True)

                # Recent data table
                st.markdown("---")
                st.subheader("📊 최근 데이터")
                display_cols = ['open', 'high', 'low', 'close', 'volume']
                st.dataframe(data[display_cols].tail(20), use_container_width=True)

            except Exception as e:
                st.error(f"❌ 신호 생성 중 오류 발생: {e}")
                import traceback
                st.code(traceback.format_exc())


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
            ["📋 목록에서 선택" if lang == 'ko' else "📋 Select from List",
             "⌨️ 직접 입력 (모든 미국 주식)" if lang == 'ko' else "⌨️ Direct Input (All US Stocks)"],
            horizontal=True,
            key='quote_selection_method'
        )

        # Get all stocks for dropdown
        all_stocks = stock_db.stocks

        # Create display format: "SYMBOL - Company Name"
        stock_options = [f"{stock['symbol']} - {stock['name']}" for stock in all_stocks]
        stock_symbols = [stock['symbol'] for stock in all_stocks]

        if selection_method.startswith("📋"):
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
            st.info("💡 " + ("PLTR, SHOP, COIN, UBER, ABNB, RBLX 등 모든 미국 주식 심볼을 입력하세요." if lang == 'ko' else "Enter any US stock symbol: PLTR, SHOP, COIN, UBER, ABNB, RBLX, etc."))

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

    # Try KIS broker first, fallback to yfinance
    ticker = None
    data_source = None

    # Import helpers
    from dashboard.kis_broker import get_kis_broker
    from dashboard.yfinance_helper import fetch_ticker_yfinance

    # Try KIS broker first (for list selection)
    if selection_method.startswith("📋"):
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
        st.caption(f"📊 " + ("데이터 소스:" if lang == 'ko' else "Data source:") + f" {data_source}")

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
        if selection_method.startswith("📋"):
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


def scheduler_tab():
    """
    자동 스케줄러 탭

    대시보드 내부에서 실행되는 스케줄러를 관리합니다.
    - 스케줄 시작/중지
    - 스케줄 시간 설정
    - 실시간 로그 표시
    - 전략 설정
    """
    lang = st.session_state.language

    st.header("⏰ 자동 스케줄러")
    st.markdown("""
    미국 시장 시간에 맞춰 자동으로 전략 최적화, 페이퍼 트레이딩 시작/중지를 실행합니다.
    """)

    # 세션 상태에 스케줄러 매니저 초기화
    if 'scheduler_manager' not in st.session_state:
        st.session_state.scheduler_manager = SchedulerManager()

    manager = st.session_state.scheduler_manager

    # 상태 조회
    status = manager.get_status()

    st.markdown("---")

    # 스케줄러 상태 표시
    col1, col2, col3 = st.columns(3)

    with col1:
        if status['running']:
            st.success("✅ 스케줄러 실행 중")
        else:
            st.error("⏸️ 스케줄러 중지됨")

    with col2:
        if status['trading_active']:
            st.info("🔄 트레이딩 세션 활성")
        else:
            st.info("💤 트레이딩 세션 없음")

    with col3:
        if status['running'] and status['next_run_time']:
            st.metric("다음 실행", status['next_run_time'][:16])
        else:
            st.metric("다음 실행", "없음")

    st.markdown("---")

    # 제어 버튼
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("▶️ 스케줄러 시작", disabled=status['running'], use_container_width=True):
            result = manager.start()
            if result['success']:
                st.success(result['message'])
                st.rerun()
            else:
                st.error(f"{result['message']}: {result['error']}")

    with col2:
        if st.button("⏹️ 스케줄러 중지", disabled=not status['running'], use_container_width=True):
            result = manager.stop()
            if result['success']:
                st.success(result['message'])
                st.rerun()
            else:
                st.error(f"{result['message']}: {result['error']}")

    with col3:
        if st.button("🗑️ 로그 초기화", use_container_width=True):
            manager.clear_logs()
            st.success("로그가 초기화되었습니다.")
            st.rerun()

    st.markdown("---")

    # 스케줄 설정
    with st.expander("⚙️ 스케줄 시간 설정", expanded=False):
        st.markdown("**스케줄 시간 (Asia/Seoul - KST)**")

        col1, col2, col3 = st.columns(3)

        with col1:
            optimize_time = st.time_input(
                "전략 최적화",
                value=manager.schedule_config['optimize_time'],
                help="장 시작 전 전략 파라미터 최적화"
            )

        with col2:
            start_time = st.time_input(
                "트레이딩 시작",
                value=manager.schedule_config['start_time'],
                help="미국 시장 개장 시각 (23:30 KST)"
            )

        with col3:
            stop_time = st.time_input(
                "트레이딩 종료",
                value=manager.schedule_config['stop_time'],
                help="미국 시장 마감 시각 (06:00 KST)"
            )

        if st.button("스케줄 시간 업데이트"):
            result = manager.update_schedule(optimize_time, start_time, stop_time)
            if result['success']:
                st.success(result['message'])
                st.rerun()
            else:
                st.error(f"{result['message']}: {result['error']}")

    # 프리셋 불러오기
    with st.expander("💾 프리셋 불러오기", expanded=True):
        preset_mgr = StrategyPresetManager()
        all_presets = preset_mgr.list_presets()
        preset_names = [p['name'] for p in all_presets]

        if preset_names:
            col_p1, col_p2 = st.columns([3, 1])

            with col_p1:
                selected_preset = st.selectbox(
                    "저장된 프리셋 선택",
                    ["(수동 설정)"] + preset_names,
                    key="scheduler_preset_select",
                    help="Paper Trading에서 저장한 프리셋을 불러와 스케줄러에 적용합니다"
                )

            with col_p2:
                load_preset_btn = st.button(
                    "📥 불러오기",
                    disabled=(selected_preset == "(수동 설정)"),
                    key="scheduler_load_preset",
                    use_container_width=True
                )

            if load_preset_btn and selected_preset != "(수동 설정)":
                if manager.load_from_preset(selected_preset):
                    st.success(f"✅ 프리셋 '{selected_preset}' → 스케줄러에 적용 완료!")
                    st.rerun()
                else:
                    st.error(f"프리셋 '{selected_preset}' 불러오기 실패")

            # 현재 로드된 프리셋 표시
            if manager.loaded_preset_name:
                st.info(f"📌 현재 적용된 프리셋: **{manager.loaded_preset_name}**")

            # 프리셋 상세 정보 표시
            if selected_preset != "(수동 설정)":
                preset_data = next((p for p in all_presets if p['name'] == selected_preset), None)
                if preset_data:
                    with st.expander("ℹ️ 프리셋 정보"):
                        st.markdown(f"**전략**: {preset_data['strategy']}")
                        st.markdown(f"**종목**: {', '.join(preset_data['symbols'][:5])}")
                        st.markdown(f"**초기 자본**: ${preset_data['initial_capital']:,.0f}")
                        st.markdown(f"**포지션**: {preset_data['position_size']:.0%}")
                        st.markdown(f"**손절/익절**: {preset_data['stop_loss_pct']:.0%} / {preset_data['take_profit_pct']:.0%}")
                        if preset_data.get('description'):
                            st.caption(preset_data['description'])
                        st.markdown(f"**파라미터**: `{preset_data['strategy_params']}`")
        else:
            st.info("💡 저장된 프리셋이 없습니다. Paper Trading 탭에서 프리셋을 먼저 저장하세요!")

    # 전략 설정
    with st.expander("🎯 전략 설정 (수동)", expanded=False):
        st.markdown("**자동 트레이딩 전략 설정** (프리셋 대신 수동으로 설정)")

        col1, col2 = st.columns(2)

        with col1:
            # 현재 매니저 전략에 맞는 기본 인덱스 찾기
            scheduler_strategy_options = ["RSI+MACD Combo Strategy", "RSI Strategy", "MACD Strategy", "Bollinger Bands"]
            default_idx = 0
            if manager.strategy_name in scheduler_strategy_options:
                default_idx = scheduler_strategy_options.index(manager.strategy_name)

            strategy_name = st.selectbox(
                "전략",
                scheduler_strategy_options,
                index=default_idx,
                help="자동 실행할 전략 선택"
            )

            # 종목 선택
            from dashboard.stock_symbols import StockSymbolDB
            symbol_db = StockSymbolDB()

            # DataFrame에서 직접 가져오기
            all_symbols_df = symbol_db.df[['symbol', 'name', 'sector']].copy()
            symbol_options = [f"{row['symbol']} - {row['name']}" for _, row in all_symbols_df.iterrows()]

            # 기본 종목 찾기
            default_indices = []
            for sym in manager.symbols:
                matching = all_symbols_df[all_symbols_df['symbol'] == sym].index.tolist()
                if matching:
                    default_indices.append(matching[0])

            selected_indices = st.multiselect(
                "종목 선택 (최대 7개)",
                range(len(all_symbols_df)),
                default=default_indices[:5],
                format_func=lambda i: symbol_options[i],
                help="자동 트레이딩 종목 (최대 7개)"
            )

            symbols = [all_symbols_df.iloc[i]['symbol'] for i in selected_indices]

        with col2:
            initial_capital = st.number_input(
                "초기 자본 ($)",
                min_value=1000.0,
                max_value=1000000.0,
                value=manager.initial_capital,
                step=1000.0
            )

            position_size = st.slider(
                "포지션 크기",
                min_value=0.1,
                max_value=0.5,
                value=manager.position_size,
                step=0.05,
                format="%.0f%%",
                help="종목당 투자 비율"
            )

            stop_loss_pct = st.slider(
                "손절 (%)",
                min_value=1.0,
                max_value=10.0,
                value=manager.stop_loss_pct * 100,
                step=0.5,
                help="손실률"
            ) / 100

            take_profit_pct = st.slider(
                "익절 (%)",
                min_value=2.0,
                max_value=20.0,
                value=manager.take_profit_pct * 100,
                step=0.5,
                help="수익률"
            ) / 100

        if st.button("전략 설정 저장"):
            manager.update_strategy_config(
                strategy_name=strategy_name,
                symbols=symbols,
                initial_capital=initial_capital,
                position_size=position_size,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct
            )
            st.success("전략 설정이 저장되었습니다.")

    st.markdown("---")

    # 스케줄 정보 표시
    st.subheader("📅 스케줄 정보")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**현재 스케줄 (KST)**")
        schedule_data = [
            {"시간": manager.schedule_config['optimize_time'].strftime('%H:%M'), "작업": "전략 최적화", "설명": "장 시작 전 파라미터 최적화"},
            {"시간": manager.schedule_config['start_time'].strftime('%H:%M'), "작업": "트레이딩 시작", "설명": "미국 시장 개장"},
            {"시간": manager.schedule_config['stop_time'].strftime('%H:%M'), "작업": "트레이딩 종료", "설명": "미국 시장 마감, 리포트 생성"}
        ]
        st.dataframe(schedule_data, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("**미국 시장 시간**")
        market_info = [
            {"구분": "정규장 개장", "시간": "23:30 KST (09:30 EST)"},
            {"구분": "정규장 마감", "시간": "06:00 KST (16:00 EST)"},
            {"구분": "타임존", "시간": "US/Eastern"}
        ]
        st.dataframe(market_info, use_container_width=True, hide_index=True)

    # 현재 실행 중인 작업
    if status['running'] and status['jobs']:
        st.markdown("**등록된 작업**")
        jobs_data = []
        for job in status['jobs']:
            jobs_data.append({
                "작업 이름": job['name'],
                "다음 실행 시간": job['next_run_time'][:19] if job['next_run_time'] else "없음"
            })
        st.dataframe(jobs_data, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 실시간 로그 표시
    st.subheader("📋 실시간 로그")

    # 로그 줄 수 선택
    log_lines = st.slider("표시할 로그 줄 수", min_value=10, max_value=500, value=100, step=10)

    # 자동 새로고침 체크박스
    auto_refresh = st.checkbox("자동 새로고침 (5초)", value=False)

    # 로그 표시
    logs = manager.get_logs(lines=log_lines)

    if logs:
        log_text = "\n".join(logs)
        st.code(log_text, language="log", line_numbers=False)
    else:
        st.info("로그가 없습니다. 스케줄러를 시작하면 로그가 표시됩니다.")

    # 자동 새로고침
    if auto_refresh:
        time.sleep(5)
        st.rerun()

    st.markdown("---")

    # 세션 관리 섹션
    render_session_manager(lang)


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
    # Reordered tabs - Paper Trading is the main feature, so it comes first
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🎮 " + get_text('tab_paper', lang),           # Main feature: Paper Trading
        "📊 전략 & 세션 비교",                          # Combined comparison
        "⏰ 자동 스케줄러",                             # Automated Scheduler
        "📈 " + get_text('tab_quotes', lang),          # Real-time quotes
        "📉 " + get_text('tab_backtest', lang),        # Advanced: Backtesting
        "🔴 " + get_text('tab_live', lang),            # Advanced: Live Monitor
    ])

    with tab1:
        paper_trading_tab()

    with tab2:
        # Combined tab: Strategy Comparison + Session Comparison
        st.header("📊 전략 & 세션 비교")

        comparison_type = st.radio(
            "비교 유형 선택",
            ["세션 비교 (Paper Trading)", "전략 비교 (시뮬레이션)"],
            horizontal=True,
            help="Paper Trading 세션을 비교하거나, 시뮬레이션 데이터로 여러 전략을 비교할 수 있습니다"
        )

        st.markdown("---")

        if comparison_type == "세션 비교 (Paper Trading)":
            paper_trading_comparison_tab()
        else:
            strategy_comparison_tab()

    with tab3:
        scheduler_tab()

    with tab4:
        realtime_quotes_tab()

    with tab5:
        backtest_tab()

    with tab6:
        live_monitor_tab()

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
