"""
Parallel Prompt Builder for Market Analysis

시장 분석 Notion 페이지를 병렬로 생성하기 위한 워커별 프롬프트 빌더입니다.
3개 워커(A, B, C)가 각각 독립적인 섹션을 생성하고,
Notion Writer가 최종 페이지를 조립하여 생성합니다.

Worker A: 섹션 1 (시장 요약), 2 (종목별 분석) - WebSearch 필요
Worker B: 섹션 3 (Top 3), 4 (공포/탐욕), 5 (뉴스) - WebSearch + Read 필요
Worker C: 섹션 6-10 (전략/성과/세션/전망/리스크) - 도구 불필요
Notion Writer: 조립된 콘텐츠로 Notion 페이지 생성

Usage:
    from trading_bot.parallel_prompt_builder import (
        build_worker_a_prompt,
        build_worker_b_prompt,
        build_worker_c_prompt,
        build_notion_writer_prompt,
        precompute_session_metrics,
        assemble_sections,
    )
"""

import logging
from typing import Dict, List, Optional, Tuple

from trading_bot.prompts.prompt_engine import PromptEngine
from trading_bot.prompts.prompt_data import (
    PromptDataBuilder,
    # 하위 호환성을 위한 re-export
    precompute_session_metrics,
    assemble_sections,
    validate_assembly,
    _load_previous_top3,
    _save_top3_marker,
    _build_intelligence_block,
    _build_intelligence_summary,
    _build_daily_changes_block,
    _compute_top3_candidates,
    _build_historical_performance_block,
    _calculate_var_95,
    _calculate_strategy_pnl_breakdown,
    _format_trade_log,
    _extract_forward_look_data,
    _build_events_data_block,
    _build_fundamentals_data_block,
    _load_session_reports,
    get_notion_page_id,
)

logger = logging.getLogger(__name__)

# 워커별 모델 ID 매핑
WORKER_MODELS = {
    'Worker-A': 'claude-sonnet-4-6',        # WebSearch required
    'Worker-B': 'claude-sonnet-4-6',        # WebSearch + Read required
    'Worker-C': 'claude-haiku-4-5-20251001',  # No tools, data analysis only
    'Notion-Writer': 'claude-haiku-4-5-20251001',  # Simple page creation
}

# 페이지 하단 푸터 템플릿 (.format() 사용 — {{ → { 로 이스케이프)
FOOTER_TEMPLATE = """::: callout {{icon="📝" color="gray_bg"}}
\t**분석 생성**: {date}  \\|  **데이터 수집**: {date} KST  \\|  **병렬 생성**: Worker A + B + C
\t**주의사항**: 본 분석은 자동 수집된 데이터와 기술적 지표를 기반으로 생성된 참고 자료입니다. 실제 투자 결정은 개인의 판단과 책임 하에 이루어져야 합니다.
:::"""

# Notion Enhanced Markdown 포맷 규칙 (각 워커에 포함) — 하위 호환
_FORMAT_RULES = r"""--- FORMAT RULES (MANDATORY) ---
1. ALL section headers (# 1., # 2., ...) MUST have {color="blue"}
2. ALL tables MUST have fit-page-width="true" header-row="true"
3. Header rows in tables MUST have color="blue_bg"
4. Notable/warning rows MUST have color="orange_bg"
5. Risk table headers MUST have color="red_bg"
6. Price changes: <span color="green"> for positive, <span color="red"> for negative
7. MACD: <span color="green">Bullish</span> or <span color="red">Bearish</span>
8. Use --- between ALL major sections
9. Use ::: callout blocks with appropriate icons and colors
10. Escape pipe characters as \| inside callouts
11. Use <details><summary> for expandable sections
12. Fear & Greed history rows: green_bg for greed periods, red_bg for fear periods, yellow_bg for neutral
13. Tables with stock symbols should have header-column="true"
--- END FORMAT RULES ---"""

# 모듈-레벨 싱글턴
_engine = PromptEngine()
_builder = PromptDataBuilder()


def build_worker_a_prompt(
    market_data: Dict,
    today: str,
    macro_data: Optional[Dict] = None,
    intelligence_data: Optional[Dict] = None,
    events_data: Optional[Dict] = None,
    fundamentals_data: Optional[Dict] = None,
    fear_greed_data: Optional[Dict] = None,
    daily_changes: Optional[Dict] = None,
) -> str:
    """
    Worker A 프롬프트를 생성합니다.
    담당 섹션: 0 (매크로 시장 환경, macro_data 있을 때), 1 (시장 전체 요약), 2 (종목별 분석)

    Args:
        market_data: 시장 분석 JSON 데이터 (market_summary, stocks 포함)
        today: 분석 날짜 (YYYY-MM-DD)
        macro_data: 매크로 시장 환경 데이터 (Optional)
        intelligence_data: 5-Layer Intelligence 분석 결과 (Optional)
        events_data: 이벤트 캘린더 데이터 (Optional)
        fundamentals_data: 펀더멘탈 데이터 (Optional)
        fear_greed_data: Fear & Greed 지수 데이터 (Optional)
        daily_changes: 전일 대비 변화 데이터 (Optional)

    Returns:
        Worker A용 프롬프트 문자열
    """
    ctx = _builder.build_worker_a_context(
        market_data, today,
        macro_data=macro_data,
        intelligence_data=intelligence_data,
        events_data=events_data,
        fundamentals_data=fundamentals_data,
        fear_greed_data=fear_greed_data,
        daily_changes=daily_changes,
    )

    prompt = _engine.render("worker_a.md.j2", ctx)

    symbols = ctx["symbols"]
    logger.info(f"Worker A 프롬프트 생성 완료 (길이: {len(prompt)}자, 종목: {len(symbols)}개)")
    return prompt


def build_worker_b_prompt(
    market_data: Dict,
    news_data: Dict,
    fear_greed_data: Dict,
    today: str,
    intelligence_data: Optional[Dict] = None,
    worker_a_context: Optional[str] = None,
    daily_changes: Optional[Dict] = None,
    previous_top3: Optional[list] = None,
) -> Tuple[str, List[str]]:
    """
    Worker B 프롬프트를 생성합니다.
    담당 섹션: 3 (주목할 종목 Top 3), 4 (공포/탐욕 지수), 5 (뉴스 분석)

    Args:
        market_data: 시장 분석 JSON 데이터 (stocks 포함)
        news_data: 뉴스 데이터 딕셔너리
        fear_greed_data: Fear & Greed 지수 데이터 딕셔너리
        today: 분석 날짜 (YYYY-MM-DD)
        intelligence_data: 5-Layer Intelligence 분석 결과 (Optional)
        worker_a_context: Worker A의 출력 (Reflection 교차 검증용, Optional)
        daily_changes: 전일 대비 변화 데이터 (Optional)
        previous_top3: 이전 TOP 3 종목 리스트 (Optional)

    Returns:
        (Worker B용 프롬프트 문자열, TOP 3 심볼 리스트) 튜플
    """
    ctx, top3_symbols = _builder.build_worker_b_context(
        market_data, news_data, fear_greed_data, today,
        intelligence_data=intelligence_data,
        worker_a_context=worker_a_context,
        daily_changes=daily_changes,
        previous_top3=previous_top3,
    )

    prompt = _engine.render("worker_b.md.j2", ctx)

    logger.info(f"Worker B 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt, top3_symbols


def build_worker_c_prompt(
    market_data: Dict,
    session_metrics: Dict,
    today: str,
    has_sessions: bool,
    intelligence_data: Optional[Dict] = None,
    daily_changes: Optional[Dict] = None,
) -> str:
    """
    Worker C 프롬프트를 생성합니다.
    담당 섹션: 6 (전략 파라미터), 7 (성과 대시보드), 8 (세션 분석),
               9 (전방 전망), 10 (리스크)
    세션 없으면: 6, 7 (전방 전망), 8 (리스크) - 7, 8번 섹션 스킵

    Args:
        market_data: 시장 분석 JSON 데이터 (stocks 포함)
        session_metrics: precompute_session_metrics()가 반환한 메트릭
        today: 분석 날짜 (YYYY-MM-DD)
        has_sessions: 세션 데이터 존재 여부
        intelligence_data: 5-Layer Intelligence 분석 결과 (Optional)
        daily_changes: 전일 대비 변화 데이터 (Optional)

    Returns:
        Worker C용 프롬프트 문자열
    """
    ctx = _builder.build_worker_c_context(
        market_data, session_metrics, today, has_sessions,
        intelligence_data=intelligence_data,
        daily_changes=daily_changes,
    )

    prompt = _engine.render("worker_c.md.j2", ctx)

    logger.info(f"Worker C 프롬프트 생성 완료 (길이: {len(prompt)}자, 세션: {has_sessions})")
    return prompt


def build_notion_writer_prompt(
    assembled_content: str,
    today: str,
    parent_page_id: str,
) -> str:
    """
    Notion Writer 프롬프트를 생성합니다.
    조립된 콘텐츠를 Notion 페이지로 생성하는 지시를 포함합니다.

    Args:
        assembled_content: assemble_sections()가 반환한 조립된 콘텐츠
        today: 분석 날짜 (YYYY-MM-DD)
        parent_page_id: Notion 상위 페이지 ID

    Returns:
        Notion Writer용 프롬프트 문자열
    """
    ctx = _builder.build_notion_writer_context(
        assembled_content, today, parent_page_id,
    )

    prompt = _engine.render("notion_writer.md.j2", ctx)

    logger.info(f"Notion Writer 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


# 하위 호환을 위한 함수 별칭
_validate_format_rules = PromptEngine.validate_format_rules
_auto_correct_format = PromptEngine.auto_correct_format


# _build_worker_c_sections_with_sessions / _build_worker_c_sections_without_sessions
# 은 이제 Jinja2 템플릿으로 대체되었으므로 제거하되,
# 혹시 직접 참조하는 코드가 있을 경우를 위해 스텁을 유지합니다.
def _build_worker_c_sections_with_sessions() -> str:
    """Deprecated: worker_c_sessions.md.j2 템플릿으로 대체됨."""
    return _engine.render("worker_c_sessions.md.j2", {})


def _build_worker_c_sections_without_sessions() -> str:
    """Deprecated: worker_c_no_sessions.md.j2 템플릿으로 대체됨."""
    return _engine.render("worker_c_no_sessions.md.j2", {})
