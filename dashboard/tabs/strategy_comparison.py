"""
전략 비교 탭 - Paper Trading 세션 비교 및 백테스팅 전략 비교
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Optional, List

from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.database import TradingDatabase
from dashboard.components.strategy_selector import STRATEGY_CONFIGS, create_strategy


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

    # 세션 관리 (삭제)
    st.markdown("---")
    with st.expander("🗑️ 세션 관리"):
        deletable_sessions = []
        for session in all_sessions:
            is_active = session['status'] == 'active'
            session_id = session['session_id']
            strategy = session['strategy_name']
            start_time = session['start_time'][:16] if session['start_time'] else 'N/A'
            status = session['status']
            label = f"{session_id} | {strategy} | {start_time} | {status}"

            checked = st.checkbox(
                label,
                key=f"delete_{session_id}",
                disabled=is_active,
                help="active 상태 세션은 삭제할 수 없습니다" if is_active else None
            )
            if checked:
                deletable_sessions.append(session_id)

        if deletable_sessions:
            confirm = st.checkbox(
                "정말 삭제하시겠습니까? (복구 불가)",
                key="confirm_delete_sessions"
            )

            if st.button("선택한 세션 삭제", type="primary", disabled=not confirm):
                deleted = []
                failed = []
                for sid in deletable_sessions:
                    if db.delete_session(sid):
                        deleted.append(sid)
                    else:
                        failed.append(sid)

                if deleted:
                    st.success(f"✅ {len(deleted)}개 세션 삭제 완료")
                if failed:
                    st.error(f"❌ {len(failed)}개 세션 삭제 실패: {', '.join(failed)}")

                st.rerun()
        else:
            st.info("삭제할 세션을 선택하세요. (active 상태 세션은 삭제 불가)")


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
