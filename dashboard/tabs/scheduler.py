"""
자동 스케줄러 탭 - 미국 시장 시간에 맞춘 자동 트레이딩 관리
"""
import streamlit as st
import time

from trading_bot.strategy_presets import StrategyPresetManager
from dashboard.scheduler_manager import SchedulerManager
from dashboard.session_manager import render_session_manager


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

    st.header("자동 스케줄러")
    st.markdown("""
    미국 시장 시간에 맞춰 자동으로 페이퍼 트레이딩 시작/중지를 실행합니다.
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
        session_count = status.get('active_session_count', 0)
        if session_count > 0:
            st.info(f"활성 세션: {session_count}개")
        else:
            st.info("트레이딩 세션 없음")

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
        if st.button("로그 초기화", use_container_width=True):
            manager.clear_logs()
            st.success("로그가 초기화되었습니다.")
            st.rerun()

    st.markdown("---")

    # 스케줄 설정
    with st.expander("스케줄 시간 설정", expanded=False):
        st.markdown("**스케줄 시간 (Asia/Seoul - KST)**")

        col1, col2 = st.columns(2)

        with col1:
            start_time = st.time_input(
                "트레이딩 시작",
                value=manager.schedule_config['start_time'],
                help="미국 시장 개장 시각 (23:30 KST)"
            )

        with col2:
            stop_time = st.time_input(
                "트레이딩 종료",
                value=manager.schedule_config['stop_time'],
                help="미국 시장 마감 시각 (06:00 KST)"
            )

        if st.button("스케줄 시간 업데이트"):
            result = manager.update_schedule(start_time, stop_time)
            if result['success']:
                st.success(result['message'])
                st.rerun()
            else:
                st.error(f"{result['message']}: {result['error']}")

    # 프리셋 불러오기
    with st.expander("프리셋 불러오기", expanded=True):
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
                    "불러오기",
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
                st.info(f"현재 적용된 프리셋: **{manager.loaded_preset_name}**")

            # 프리셋 상세 정보 표시
            if selected_preset != "(수동 설정)":
                preset_data = next((p for p in all_presets if p['name'] == selected_preset), None)
                if preset_data:
                    with st.expander("프리셋 정보"):
                        st.markdown(f"**전략**: {preset_data['strategy']}")
                        st.markdown(f"**종목**: {', '.join(preset_data['symbols'][:5])}")
                        st.markdown(f"**초기 자본**: ${preset_data['initial_capital']:,.0f}")
                        st.markdown(f"**포지션**: {preset_data['position_size']:.0%}")
                        st.markdown(f"**손절/익절**: {preset_data['stop_loss_pct']:.0%} / {preset_data['take_profit_pct']:.0%}")
                        if preset_data.get('description'):
                            st.caption(preset_data['description'])
                        st.markdown(f"**파라미터**: `{preset_data['strategy_params']}`")
        else:
            st.info("저장된 프리셋이 없습니다. Paper Trading 탭에서 프리셋을 먼저 저장하세요.")

    # 전략 설정
    with st.expander("전략 설정 (수동)", expanded=False):
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
    st.subheader("스케줄 정보")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**현재 스케줄 (KST)**")
        schedule_data = [
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

    # 활성 세션 목록
    st.subheader("활성 세션 목록")

    active_sessions = status.get('active_sessions', [])

    if active_sessions:
        for session_info in active_sessions:
            sid = session_info['session_id']
            s_name = session_info.get('display_name') or session_info.get('strategy_name', 'Unknown')
            s_symbols = session_info.get('symbols', [])
            s_start = session_info.get('start_time', None)
            start_str = s_start.strftime('%H:%M') if hasattr(s_start, 'strftime') else str(s_start)[:16] if s_start else '-'
            source = session_info.get('source', 'dashboard')
            source_label = "🐳" if source == 'external' else ""

            symbols_str = ', '.join(s_symbols[:3]) if s_symbols else ''
            if len(s_symbols) > 3:
                symbols_str += f' 외 {len(s_symbols) - 3}개'

            col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns([2, 2, 2, 1.5, 1])

            with col_s1:
                st.text(f"{source_label} {sid[:12]}...")
            with col_s2:
                st.text(s_name)
            with col_s3:
                st.text(symbols_str)
            with col_s4:
                st.text(start_str)
            with col_s5:
                if source != 'external':
                    if st.button("🛑", key=f"stop_session_{sid}", help=f"세션 {sid[:8]} 중지"):
                        manager.stop_single_session(sid)
                        st.success(f"세션 '{sid[:12]}' 중지 완료")
                        st.rerun()
                else:
                    label = session_info.get('display_name') or sid
                    if st.button("🛑", key=f"stop_ext_{sid}", help=f"외부 세션 {sid[:8]} 중지 명령 전송"):
                        cmd_id = manager.send_stop_command(label)
                        st.success(f"중지 명령 전송 완료 (ID: {cmd_id}, 최대 60초 내 처리)")
                        st.rerun()

        # 전체 중지 / 세션 추가 버튼
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])

        with col_btn1:
            if st.button("▶️ 세션 추가 시작", use_container_width=True, help="현재 설정으로 새 세션을 즉시 시작합니다"):
                new_id = manager.start_manual_session()
                if new_id:
                    st.success(f"새 세션 시작: {new_id[:12]}")
                else:
                    st.error("세션 시작 실패")
                st.rerun()

        with col_btn2:
            if st.button("⏹️ 모두 중지", use_container_width=True, help="모든 활성 세션을 일괄 중지합니다"):
                manager.stop_paper_trading()
                st.success("모든 세션 중지 완료")
                st.rerun()
    else:
        st.info("활성 세션이 없습니다.")

        if st.button("▶️ 세션 추가 시작", help="현재 설정으로 새 세션을 즉시 시작합니다"):
            new_id = manager.start_manual_session()
            if new_id:
                st.success(f"새 세션 시작: {new_id[:12]}")
            else:
                st.error("세션 시작 실패")
            st.rerun()

    st.markdown("---")

    # 실시간 로그 표시
    st.subheader("실시간 로그")

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

    # 외부 스케줄러 제어 (DB 명령 큐)
    _render_external_scheduler_control(manager, lang)

    st.markdown("---")

    # 세션 관리 섹션
    render_session_manager(lang)


def _render_external_scheduler_control(manager, lang: str):
    """Docker 스케줄러 제어 패널 (DB 명령 큐 연동)"""
    st.subheader("외부 스케줄러 제어" if lang == 'ko' else "External Scheduler Control")
    st.caption(
        "Docker 컨테이너에서 실행 중인 스케줄러를 DB 명령 큐를 통해 제어합니다. 명령은 최대 60초 내에 처리됩니다."
        if lang == 'ko' else
        "Control the scheduler running in a Docker container via DB command queue. Commands are processed within 60 seconds."
    )

    # 스케줄러 상태
    health = manager.get_scheduler_health()

    if health:
        state = health.get('state', 'unknown')
        timestamp = health.get('timestamp', '')[:19]
        details = health.get('details', {})
        active_sessions = details.get('active_sessions', [])

        state_emoji = {
            'idle': '💤', 'trading': '📈', 'optimizing': '🔧',
            'starting': '🚀', 'stopping': '🛑', 'error': '❌'
        }.get(state, '❓')

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "스케줄러 상태" if lang == 'ko' else "Scheduler State",
                f"{state_emoji} {state}"
            )
        with col2:
            st.metric(
                "마지막 업데이트" if lang == 'ko' else "Last Update",
                timestamp if timestamp else "N/A"
            )
        with col3:
            session_count = len(active_sessions) if isinstance(active_sessions, list) else 0
            st.metric(
                "외부 활성 세션" if lang == 'ko' else "External Sessions",
                session_count
            )
    else:
        st.warning(
            "외부 스케줄러 상태 파일을 찾을 수 없습니다. 스케줄러가 실행 중인지 확인하세요."
            if lang == 'ko' else
            "Scheduler status file not found. Check if the scheduler is running."
        )

    # 제어 버튼
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(
            "🧹 좀비 세션 정리" if lang == 'ko' else "🧹 Cleanup Zombies",
            use_container_width=True,
            help="외부 스케줄러에 좀비 세션 정리 명령을 전송합니다"
        ):
            cmd_id = manager.send_cleanup_command()
            st.success(
                f"좀비 정리 명령 전송 완료 (ID: {cmd_id})"
                if lang == 'ko' else
                f"Cleanup command sent (ID: {cmd_id})"
            )
            st.rerun()

    with col2:
        if st.button(
            "⏹️ 외부 세션 전체 중지" if lang == 'ko' else "⏹️ Stop All External",
            use_container_width=True,
            help="외부 스케줄러의 모든 활성 세션에 중지 명령을 전송합니다"
        ):
            cmd_ids = manager.send_stop_all_command()
            if cmd_ids:
                st.success(
                    f"전체 중지 명령 전송: {len(cmd_ids)}개 세션"
                    if lang == 'ko' else
                    f"Stop commands sent for {len(cmd_ids)} sessions"
                )
            else:
                st.info(
                    "활성 세션이 없습니다."
                    if lang == 'ko' else
                    "No active sessions found."
                )
            st.rerun()

    with col3:
        if st.button(
            "🔄 새로고침" if lang == 'ko' else "🔄 Refresh",
            use_container_width=True,
        ):
            st.rerun()

    # 대기 중 명령 표시
    pending = manager.get_pending_commands()
    if pending:
        with st.expander(
            f"대기 중 명령 ({len(pending)}개)" if lang == 'ko'
            else f"Pending Commands ({len(pending)})",
            expanded=False
        ):
            cmd_data = []
            for cmd in pending:
                cmd_data.append({
                    'ID': cmd['id'],
                    '명령' if lang == 'ko' else 'Command': cmd['command'],
                    '대상' if lang == 'ko' else 'Target': cmd.get('target_label') or '-',
                    '생성 시간' if lang == 'ko' else 'Created': cmd['created_at'][:19],
                })
            st.dataframe(cmd_data, use_container_width=True, hide_index=True)
