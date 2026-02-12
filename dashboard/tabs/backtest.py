"""
백테스팅 탭 - 시뮬레이션/실제 데이터로 전략을 테스트하고 성능을 분석
"""
import streamlit as st
import pandas as pd
from typing import Dict, Any

from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategy_presets import StrategyPresetManager
from dashboard.charts import ChartGenerator
from dashboard.translations import get_text, get_strategy_name
from dashboard.components.strategy_selector import STRATEGY_CONFIGS, create_strategy, render_strategy_params


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
