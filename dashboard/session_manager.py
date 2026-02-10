"""
Session Manager Widget
Manages paper trading sessions - view history, recover zombie sessions, inspect logs
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, List, Optional, Any
from trading_bot.database import TradingDatabase


def render_session_manager(lang: str = 'ko') -> None:
    """
    Render session manager section inside scheduler tab

    Args:
        lang: Language code ('ko' or 'en')
    """
    st.subheader("📂 세션 관리" if lang == 'ko' else "📂 Session Manager")
    st.caption(
        "모든 Paper Trading 세션을 관리하고, 로그를 조회할 수 있습니다."
        if lang == 'ko'
        else "Manage all paper trading sessions and inspect logs."
    )

    db = TradingDatabase()

    # Session status overview
    _render_status_overview(db, lang)

    st.markdown("---")

    # Session list with filter
    _render_session_list(db, lang)


def _render_status_overview(db: TradingDatabase, lang: str) -> None:
    """Render session status counts as metrics"""
    status_counts = db.get_session_status_counts()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        active = status_counts.get('active', 0)
        st.metric("🟢 활성" if lang == 'ko' else "🟢 Active", active)
    with col2:
        completed = status_counts.get('completed', 0)
        st.metric("✅ 완료" if lang == 'ko' else "✅ Completed", completed)
    with col3:
        interrupted = status_counts.get('interrupted', 0)
        st.metric("⚠️ 중단됨" if lang == 'ko' else "⚠️ Interrupted", interrupted)
    with col4:
        terminated = status_counts.get('terminated', 0)
        st.metric("🛑 종료됨" if lang == 'ko' else "🛑 Terminated", terminated)


def _render_session_list(db: TradingDatabase, lang: str) -> None:
    """Render session list with filtering and detail view"""

    # Filter options
    col1, col2 = st.columns([1, 3])

    with col1:
        status_options = {
            '전체': None,
            '🟢 활성': 'active',
            '✅ 완료': 'completed',
            '⚠️ 중단됨': 'interrupted',
            '🛑 종료됨': 'terminated',
        }
        if lang != 'ko':
            status_options = {
                'All': None,
                '🟢 Active': 'active',
                '✅ Completed': 'completed',
                '⚠️ Interrupted': 'interrupted',
                '🛑 Terminated': 'terminated',
            }

        selected_status_label = st.selectbox(
            "상태 필터" if lang == 'ko' else "Status Filter",
            list(status_options.keys()),
            key="session_status_filter"
        )
        status_filter = status_options[selected_status_label]

    # Fetch sessions
    sessions = db.get_all_sessions(status_filter=status_filter)

    if not sessions:
        st.info(
            "세션이 없습니다." if lang == 'ko'
            else "No sessions found."
        )
        return

    # Build session list for selectbox
    session_options = []
    for s in sessions:
        status_emoji = _status_emoji(s['status'])
        start_str = s['start_time'][:16] if s['start_time'] else '?'
        ret = f"{s.get('total_return', 0) or 0:+.2f}%" if s.get('total_return') else ''
        label = f"{status_emoji} {s['strategy_name']} | {start_str} | {ret}"
        session_options.append(label)

    selected_idx = st.selectbox(
        "세션 선택" if lang == 'ko' else "Select Session",
        range(len(session_options)),
        format_func=lambda i: session_options[i],
        key="session_select"
    )

    selected_session = sessions[selected_idx]

    # Action buttons for non-completed sessions
    if selected_session['status'] in ('active', 'interrupted'):
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button(
                "🛑 세션 종료 처리" if lang == 'ko' else "🛑 Terminate",
                key="terminate_session_btn"
            ):
                db.terminate_session(selected_session['session_id'])
                st.success(
                    f"세션 `{selected_session['session_id'][:12]}...` 종료 처리 완료"
                    if lang == 'ko'
                    else f"Session `{selected_session['session_id'][:12]}...` terminated"
                )
                st.rerun()

    # Session detail view
    _render_session_detail(db, selected_session, lang)


def _render_session_detail(db: TradingDatabase, session: Dict[str, Any], lang: str) -> None:
    """Render detailed view of a specific session"""

    session_id = session['session_id']

    # Session overview card
    with st.expander(
        f"📋 세션 정보: {session_id[:12]}..." if lang == 'ko'
        else f"📋 Session Info: {session_id[:12]}...",
        expanded=True
    ):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(f"**전략**: {session['strategy_name']}" if lang == 'ko' else f"**Strategy**: {session['strategy_name']}")
            st.markdown(f"**상태**: {_status_emoji(session['status'])} {session['status']}")
            st.markdown(f"**시작**: {session['start_time'][:19] if session['start_time'] else 'N/A'}")
            st.markdown(f"**종료**: {session['end_time'][:19] if session['end_time'] else '실행 중' if lang == 'ko' else 'Running'}")

        with col2:
            initial_cap = session.get('initial_capital', 0) or 0
            final_cap = session.get('final_capital', 0) or 0
            st.metric(
                "초기 자본" if lang == 'ko' else "Initial Capital",
                f"${initial_cap:,.0f}"
            )
            st.metric(
                "최종 자본" if lang == 'ko' else "Final Capital",
                f"${final_cap:,.0f}",
                delta=f"{session.get('total_return', 0) or 0:+.2f}%"
            )

        with col3:
            st.metric("Sharpe Ratio", f"{session.get('sharpe_ratio', 0) or 0:.2f}")
            st.metric("Max Drawdown", f"{session.get('max_drawdown', 0) or 0:.2f}%")
            st.metric(
                "승률" if lang == 'ko' else "Win Rate",
                f"{session.get('win_rate', 0) or 0:.1f}%"
            )

    # Tabs for different log views
    log_tab1, log_tab2, log_tab3 = st.tabs([
        "📝 거래 내역" if lang == 'ko' else "📝 Trades",
        "📈 포트폴리오 추이" if lang == 'ko' else "📈 Portfolio",
        "🔔 전략 시그널" if lang == 'ko' else "🔔 Signals",
    ])

    with log_tab1:
        _render_trades_log(db, session_id, lang)

    with log_tab2:
        _render_portfolio_snapshots(db, session_id, lang)

    with log_tab3:
        _render_signals_log(db, session_id, lang)


def _render_trades_log(db: TradingDatabase, session_id: str, lang: str) -> None:
    """Render trade history for a session"""
    trades = db.get_session_trades(session_id)

    if not trades:
        st.info("거래 내역이 없습니다." if lang == 'ko' else "No trades found.")
        return

    df = pd.DataFrame(trades)

    # Format columns
    display_cols = ['timestamp', 'symbol', 'type', 'price', 'size', 'commission', 'pnl', 'pnl_pct']
    available_cols = [c for c in display_cols if c in df.columns]
    df_display = df[available_cols].copy()

    # Rename for display
    rename_map_ko = {
        'timestamp': '시간', 'symbol': '종목', 'type': '유형',
        'price': '가격', 'size': '수량', 'commission': '수수료',
        'pnl': '손익($)', 'pnl_pct': '손익(%)'
    }
    rename_map_en = {
        'timestamp': 'Time', 'symbol': 'Symbol', 'type': 'Type',
        'price': 'Price', 'size': 'Size', 'commission': 'Commission',
        'pnl': 'P&L ($)', 'pnl_pct': 'P&L (%)'
    }

    df_display = df_display.rename(columns=rename_map_ko if lang == 'ko' else rename_map_en)

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 거래 수" if lang == 'ko' else "Total Trades", len(trades))
    with col2:
        buys = len([t for t in trades if t.get('type') == 'BUY'])
        st.metric("매수" if lang == 'ko' else "Buys", buys)
    with col3:
        sells = len([t for t in trades if t.get('type') == 'SELL'])
        st.metric("매도" if lang == 'ko' else "Sells", sells)

    st.dataframe(df_display, use_container_width=True, hide_index=True)


def _render_portfolio_snapshots(db: TradingDatabase, session_id: str, lang: str) -> None:
    """Render portfolio snapshots chart for a session"""
    snapshots = db.get_session_snapshots(session_id)

    if not snapshots:
        st.info("포트폴리오 스냅샷이 없습니다." if lang == 'ko' else "No portfolio snapshots found.")
        return

    df = pd.DataFrame(snapshots)

    # Portfolio value chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['total_value'],
        mode='lines',
        name='총 자산' if lang == 'ko' else 'Total Value',
        line=dict(color='#1f77b4', width=2)
    ))

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['cash'],
        mode='lines',
        name='현금' if lang == 'ko' else 'Cash',
        line=dict(color='#ff7f0e', width=1, dash='dot')
    ))

    fig.update_layout(
        title='포트폴리오 추이' if lang == 'ko' else 'Portfolio Timeline',
        xaxis_title='시간' if lang == 'ko' else 'Time',
        yaxis_title='가치 ($)' if lang == 'ko' else 'Value ($)',
        template='plotly_white',
        hovermode='x unified',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary
    if len(df) >= 2:
        first_val = df['total_value'].iloc[0]
        last_val = df['total_value'].iloc[-1]
        peak_val = df['total_value'].max()
        low_val = df['total_value'].min()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "시작" if lang == 'ko' else "Start",
                f"${first_val:,.0f}"
            )
        with col2:
            st.metric(
                "현재/종료" if lang == 'ko' else "Current/End",
                f"${last_val:,.0f}",
                delta=f"{((last_val - first_val) / first_val) * 100:+.2f}%"
            )
        with col3:
            st.metric("최고" if lang == 'ko' else "Peak", f"${peak_val:,.0f}")
        with col4:
            st.metric("최저" if lang == 'ko' else "Low", f"${low_val:,.0f}")


def _render_signals_log(db: TradingDatabase, session_id: str, lang: str) -> None:
    """Render strategy signals for a session"""
    try:
        signals = db.get_session_signals(session_id)
    except Exception:
        signals = []

    if not signals:
        st.info("전략 시그널이 없습니다." if lang == 'ko' else "No strategy signals found.")
        return

    df = pd.DataFrame(signals)

    # Signal type mapping
    signal_map = {1: '🟢 BUY', -1: '🔴 SELL', 0: '⚪ HOLD'}

    display_cols = ['timestamp', 'symbol', 'signal', 'executed']
    available_cols = [c for c in display_cols if c in df.columns]
    df_display = df[available_cols].copy()

    if 'signal' in df_display.columns:
        df_display['signal'] = df_display['signal'].map(signal_map).fillna('⚪ HOLD')

    if 'executed' in df_display.columns:
        df_display['executed'] = df_display['executed'].map({1: '✅', 0: '❌'}).fillna('❌')

    rename_ko = {
        'timestamp': '시간', 'symbol': '종목',
        'signal': '시그널', 'executed': '실행 여부'
    }
    rename_en = {
        'timestamp': 'Time', 'symbol': 'Symbol',
        'signal': 'Signal', 'executed': 'Executed'
    }
    df_display = df_display.rename(columns=rename_ko if lang == 'ko' else rename_en)

    # Summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 시그널" if lang == 'ko' else "Total Signals", len(signals))
    with col2:
        buy_signals = len([s for s in signals if s.get('signal') == 1])
        st.metric("BUY 시그널", buy_signals)
    with col3:
        sell_signals = len([s for s in signals if s.get('signal') == -1])
        st.metric("SELL 시그널", sell_signals)

    st.dataframe(df_display, use_container_width=True, hide_index=True)


def _status_emoji(status: str) -> str:
    """Get emoji for session status"""
    return {
        'active': '🟢',
        'completed': '✅',
        'interrupted': '⚠️',
        'terminated': '🛑'
    }.get(status, '❓')
