"""
실시간 모니터링 탭 - 시뮬레이션 데이터로 전략 신호를 실시간 모니터링
"""
import streamlit as st
import pandas as pd
from typing import Dict

from trading_bot.simulation_data import SimulationDataGenerator
from dashboard.charts import ChartGenerator
from dashboard.translations import get_text
from dashboard.components.strategy_selector import STRATEGY_CONFIGS, create_strategy, render_strategy_params


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
