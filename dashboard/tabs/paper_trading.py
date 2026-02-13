"""
Paper Trading 탭 - 실시간 모의투자 인터페이스

app.py에서 분리된 paper_trading_tab() 및 관련 함수:
- paper_trading_tab(): 메인 UI (전략 선택, 종목 선택, 리스크 관리, 세션 제어)
- start_paper_trading(): 백그라운드 스레드로 모의투자 시작
- stop_paper_trading(): 모의투자 세션 중지
- stop_all_active_sessions(): 모든 활성 세션 일괄 중지
"""

import streamlit as st
import pandas as pd
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import (
    RSIStrategy, MACDStrategy, BollingerBandsStrategy,
    StochasticStrategy, RSIMACDComboStrategy
)
from trading_bot.paper_trader import PaperTrader
from trading_bot.database import TradingDatabase, generate_display_name
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.custom_combo_strategy import CustomComboStrategy
from dashboard.components.strategy_selector import (
    STRATEGY_CONFIGS, STRATEGY_PARAM_UI, create_strategy,
    get_strategy_names, render_strategy_params
)
from dashboard.translations import get_text
from dashboard.stock_symbols import StockSymbolDB


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
    combo_weights: List[float] = None,
    preset_name: Optional[str] = None
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
            # Create single strategy instance using registry
            strategy = create_strategy(strategy_name, strategy_params)

        # Get KIS broker for US stocks
        from dashboard.kis_broker import get_kis_broker
        broker = get_kis_broker()

        if broker is None:
            st.error("KIS 브로커 초기화 실패. 환경 변수를 확인해주세요.")
            return None

        # Initialize database
        db = TradingDatabase()

        # Generate display name
        display_name = generate_display_name(
            strategy_name=strategy_name,
            symbols=symbols,
            preset_name=preset_name
        )

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
            db=db,
            display_name=display_name
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
        st.error(f"모의투자 시작 실패: {e}")
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
        st.success(f"세션 {session_id[:16]}...이 중지되었습니다.")
    elif st.session_state.paper_trader:
        # Stop current session
        st.session_state.paper_trader.stop()
        st.session_state.paper_trading_active = False

        # Wait for thread to finish (with timeout)
        if hasattr(st.session_state, 'paper_trading_thread'):
            thread = st.session_state.paper_trading_thread
            if thread.is_alive():
                thread.join(timeout=5.0)

        st.success("모의투자가 중지되었습니다.")
    else:
        st.warning("실행 중인 모의투자 세션이 없습니다.")


def stop_all_active_sessions():
    """Stop all active paper trading sessions"""
    db = TradingDatabase()
    all_sessions = db.get_all_sessions()

    # Filter active sessions
    active_sessions = [s for s in all_sessions if s['status'] == 'active']

    if not active_sessions:
        st.info("활성화된 세션이 없습니다.")
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

    st.success(f"{stopped_count}개의 활성 세션이 중지되었습니다.")


def paper_trading_tab():
    """Paper trading interface"""
    lang = st.session_state.language

    st.header(get_text('tab_paper', lang))

    st.markdown("""
    실시간 모의투자 기능입니다. 전략과 종목을 선택하여 실제 시장 데이터로 모의투자를 실행할 수 있습니다.
    """)

    # Strategy Preset Management Section
    st.markdown("---")
    st.subheader("전략 프리셋 관리")

    # Initialize preset manager
    preset_manager = StrategyPresetManager()

    # Initialize session state for loaded preset
    if 'loaded_preset' not in st.session_state:
        st.session_state.loaded_preset = None

    col_preset1, col_preset2 = st.columns([2, 1])

    with col_preset1:
        # Load existing presets
        st.write("**저장된 프리셋 불러오기**")

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
                col_load, col_run, col_delete = st.columns([1, 1, 1])

                with col_load:
                    if st.button("불러오기", key="load_preset_btn", use_container_width=True):
                        loaded = preset_manager.load_preset(selected_preset_name)
                        if loaded:
                            st.session_state.loaded_preset = loaded
                            st.success(f"'{selected_preset_name}' 프리셋을 불러왔습니다!")
                            st.rerun()

                with col_run:
                    if st.button("▶️ 바로 실행", key="run_preset_btn", type="primary", use_container_width=True):
                        if st.session_state.get('paper_trading_active', False):
                            st.warning("이미 모의투자가 실행 중입니다. 먼저 중지해주세요.")
                        else:
                            preset_data = preset_manager.load_preset(selected_preset_name)
                            if preset_data:
                                session_id = start_paper_trading(
                                    strategy_name=preset_data['strategy'],
                                    symbols=preset_data['symbols'],
                                    initial_capital=preset_data['initial_capital'],
                                    position_size=preset_data['position_size'],
                                    strategy_params=preset_data['strategy_params'],
                                    stop_loss_pct=preset_data.get('stop_loss_pct', 0.05),
                                    take_profit_pct=preset_data.get('take_profit_pct', 0.10),
                                    enable_stop_loss=preset_data.get('enable_stop_loss', True),
                                    enable_take_profit=preset_data.get('enable_take_profit', True),
                                    preset_name=selected_preset_name,
                                )
                                if session_id:
                                    st.session_state.loaded_preset = preset_data
                                    st.success(f"'{selected_preset_name}' 프리셋으로 모의투자가 시작되었습니다! (Session: {session_id})")
                                    st.rerun()
                                else:
                                    st.error("모의투자 시작에 실패했습니다.")
                            else:
                                st.error(f"'{selected_preset_name}' 프리셋을 불러올 수 없습니다.")

                with col_delete:
                    if st.button("삭제", key="delete_preset_btn", type="secondary", use_container_width=True):
                        if preset_manager.delete_preset(selected_preset_name):
                            st.success(f"'{selected_preset_name}' 프리셋이 삭제되었습니다!")
                            st.session_state.loaded_preset = None
                            st.rerun()

                # Show preset details
                if selected_preset_name in preset_options:
                    preset = preset_options[selected_preset_name]
                    with st.expander("프리셋 상세 정보", expanded=False):
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
            st.info("저장된 프리셋이 없습니다. 설정을 구성한 후 저장해보세요.")

    with col_preset2:
        # Save current settings as preset
        st.write("**현재 설정 저장**")

        # Handle clear flag from previous save
        if st.session_state.get('preset_save_clear'):
            st.session_state.preset_save_clear = False
            st.session_state.new_preset_name = ""
            st.session_state.preset_description = ""

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
        st.info("아래 설정을 완료한 후 이 섹션으로 돌아와서 프리셋을 저장하세요")

    st.markdown("---")

    # Configuration Section
    st.subheader("모의투자 설정")

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
        "커스텀 콤보 전략 만들기",
        value=False,
        help="여러 전략을 조합하여 나만의 전략을 만들 수 있습니다"
    )

    # Initialize combo variables
    selected_combo_strategies = []
    combo_logic_name = 'MAJORITY'
    combo_weights = []
    combo_strategy_params = {}

    if use_custom_combo:
        with st.expander("커스텀 콤보 전략 설정", expanded=True):
            st.info("여러 전략을 선택하고 조합 로직을 설정하여 커스텀 전략을 만드세요.")

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
                    with st.expander(f"{strat_name}", expanded=False):
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
                st.success(f"커스텀 전략 이름: **{combo_name}**")

            elif len(selected_combo_strategies) < 2:
                st.warning("최소 2개 이상의 전략을 선택해주세요")

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

            for preset_name_key, symbols in popular_presets.items():
                with st.expander(f"{preset_name_key} ({len(symbols)}개)", expanded=(preset_name_key == 'FAANG')):
                    for symbol in symbols:
                        stock_info = stock_db.get_by_symbol(symbol)
                        if stock_info:
                            is_checked = symbol in st.session_state.temp_selected_stocks
                            if st.checkbox(
                                f"{symbol} - {stock_info['name']}",
                                value=is_checked,
                                key=f"pop_{preset_name_key}_{symbol}"
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
    st.subheader("리스크 관리")

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
        st.info(f"리스크/보상 비율: 1:{risk_reward_ratio:.1f} (손실 {stop_loss_pct*100:.1f}% 대비 수익 {take_profit_pct*100:.1f}%)")

    # Strategy Parameters Section
    st.markdown("---")
    st.subheader("전략 파라미터")

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
        st.info(strategy_config.get('description', ''))
    else:
        st.warning("선택한 전략의 파라미터 설정이 없습니다.")

    # Save Preset Button
    st.markdown("---")
    st.subheader("현재 설정을 프리셋으로 저장")

    col_save1, col_save2 = st.columns([3, 1])

    with col_save1:
        # Retrieve preset name and description from earlier inputs
        preset_name_input = st.session_state.get('new_preset_name', '')
        preset_desc_input = st.session_state.get('preset_description', '')

        if preset_name_input:
            st.info(f"프리셋 이름: **{preset_name_input}**")
            if preset_desc_input:
                st.caption(f"설명: {preset_desc_input}")
        else:
            st.warning("위 '전략 프리셋 관리' 섹션에서 프리셋 이름을 입력하세요")

    with col_save2:
        save_preset_btn = st.button(
            "프리셋 저장",
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
                st.success(f"'{preset_name_input}' 프리셋이 저장되었습니다!")
                # Clear input fields via flag (cannot modify widget keys directly)
                st.session_state.preset_save_clear = True
                st.rerun()
            else:
                st.error("프리셋 저장에 실패했습니다.")

    # Validation
    if not selected_symbols:
        st.warning("최소 1개 이상의 종목을 선택해주세요.")
        return

    st.markdown("---")

    # Session Management Section
    with st.expander("실행 중인 세션 관리", expanded=False):
        db = TradingDatabase()
        all_sessions = db.get_all_sessions()
        active_sessions = [s for s in all_sessions if s['status'] == 'active']

        if active_sessions:
            st.write(f"**활성 세션: {len(active_sessions)}개**")

            for session in active_sessions:
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    display = session.get('display_name') or session['strategy_name']
                    session_info = f"**{display}** | "
                    session_info += f"시작: {session['start_time'][11:19]} | "
                    session_info += f"자본: ${session['initial_capital']:,.0f}"
                    st.write(session_info)
                    st.caption(f"Session ID: {session['session_id']}")

                with col2:
                    if st.button("상세", key=f"detail_{session['session_id']}"):
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
            if st.button("⏹️ 모든 세션 중지", type="secondary", use_container_width=True):
                stop_all_active_sessions()
                st.rerun()
        else:
            st.info("현재 활성화된 세션이 없습니다.")

    st.markdown("---")

    # Control Section
    st.subheader("모의투자 제어")

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
            "▶️ 모의투자 시작",
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
            st.success(f"모의투자 실행 중 — {selected_strategy}")
        else:
            st.info("모의투자 대기 중")

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
            st.success(f"모의투자가 시작되었습니다! (Session ID: {session_id})")
            st.rerun()
        else:
            st.error("모의투자 시작에 실패했습니다.")

    if stop_button:
        stop_paper_trading()
        st.rerun()

    # Check for errors in background thread
    if hasattr(st.session_state, 'paper_trading_error'):
        st.error(f"모의투자 실행 중 오류 발생: {st.session_state.paper_trading_error}")
        del st.session_state.paper_trading_error

    # Display current session info
    if st.session_state.paper_trading_active and st.session_state.paper_trader:
        st.markdown("---")
        st.subheader("현재 세션 정보")

        trader = st.session_state.paper_trader

        # Display session ID if available
        if trader.session_id:
            if trader.display_name:
                st.caption(f"{trader.display_name}")
            st.caption(f"Session ID: {trader.session_id}")

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
        st.caption(f"종목: {', '.join(trader.symbols)}")

        # Real-time Portfolio Status
        st.markdown("---")
        st.subheader("실시간 포트폴리오 현황")

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
            if st.button("수동 새로고침", key="manual_refresh_portfolio"):
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
                st.subheader("보유 포지션")

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
                    st.caption("자동 새로고침 활성화: 10초마다 업데이트")
                    time.sleep(10)
                    st.rerun()

            else:
                st.warning("브로커 연결 실패. 포트폴리오 정보를 가져올 수 없습니다.")

        except Exception as e:
            st.error(f"포트폴리오 데이터 로딩 실패: {e}")

    elif not st.session_state.paper_trading_active:
        # No active session message
        st.info("활성화된 모의투자 세션이 없습니다. '모의투자 시작' 버튼을 눌러 시작하세요.")
