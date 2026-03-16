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

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from trading_bot.market_analysis_prompt import (
    MACRO_SECTION_TEMPLATE_PARALLEL,
    _build_events_data_block,
    _build_fundamentals_data_block,
    _load_session_reports,
    get_notion_page_id,
)
from trading_bot.performance_calculator import PerformanceCalculator

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

# Notion Enhanced Markdown 포맷 규칙 (각 워커에 포함)
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


def _build_intelligence_block(intelligence_data: Optional[Dict]) -> str:
    """5-Layer 인텔리전스 분석 결과를 프롬프트 블록으로 구성합니다.

    Args:
        intelligence_data: MarketIntelligence.analyze() 반환값

    Returns:
        프롬프트에 삽입할 인텔리전스 블록 문자열 (데이터 없으면 빈 문자열)
    """
    if not intelligence_data:
        return ""

    lines = ["\n## 5-Layer Market Intelligence 분석 결과"]
    overall = intelligence_data.get('overall', {})
    score = overall.get('score', 0)
    signal = overall.get('signal', 'N/A')
    interpretation = overall.get('interpretation', 'N/A')

    lines.append(f"**종합 점수**: {score:+.1f} ({signal})")
    lines.append(f"**종합 판단**: {interpretation}")
    lines.append("")
    lines.append("### Layer별 상세 분석")

    layer_names_kr = {
        'macro_regime': 'Layer 1: 매크로 레짐',
        'market_structure': 'Layer 2: 시장 구조',
        'sector_rotation': 'Layer 3: 섹터/팩터 로테이션',
        'enhanced_technicals': 'Layer 4: 기술적 분석',
        'sentiment': 'Layer 5: 센티먼트',
    }

    for layer_key, layer_data in intelligence_data.get('layers', {}).items():
        kr_name = layer_names_kr.get(layer_key, layer_key)
        layer_score = layer_data.get('score', 0)
        layer_signal = layer_data.get('signal', 'N/A')
        interp = layer_data.get('interpretation', '')
        confidence = layer_data.get('confidence', 0)

        lines.append(f"#### {kr_name}")
        lines.append(
            f"- **점수**: {layer_score:+.1f} ({layer_signal}), "
            f"신뢰도: {confidence:.0%}"
        )
        lines.append(f"- **판단**: {interp}")

        # 핵심 메트릭 표시
        metrics = layer_data.get('metrics', {})
        if isinstance(metrics, dict):
            for mk, mv in metrics.items():
                if isinstance(mv, dict):
                    # 서브 메트릭을 컴팩트하게 포맷
                    parts = [
                        f"{k}={v}" for k, v in mv.items()
                        if not isinstance(v, (dict, list))
                    ]
                    if parts:
                        lines.append(f"  - {mk}: {', '.join(parts[:5])}")
                elif not isinstance(mv, (list, dict)):
                    lines.append(f"  - {mk}: {mv}")
        lines.append("")

    return "\n".join(lines)


def _build_intelligence_summary(intelligence_data: Optional[Dict]) -> str:
    """인텔리전스 데이터의 간략 요약 (Worker B/C용).

    Args:
        intelligence_data: MarketIntelligence.analyze() 반환값

    Returns:
        간략 요약 문자열 (데이터 없으면 빈 문자열)
    """
    if not intelligence_data:
        return ""

    overall = intelligence_data.get('overall', {})
    score = overall.get('score', 0)
    signal = overall.get('signal', 'N/A')

    lines = [
        "\n## 5-Layer Intelligence 요약",
        f"**종합**: {score:+.1f} ({signal}) — {overall.get('interpretation', '')}",
    ]

    layer_names_kr = {
        'macro_regime': '매크로',
        'market_structure': '시장 구조',
        'sector_rotation': '섹터 로테이션',
        'enhanced_technicals': '기술적',
        'sentiment': '센티먼트',
    }

    for layer_key, layer_data in intelligence_data.get('layers', {}).items():
        kr = layer_names_kr.get(layer_key, layer_key)
        ls = layer_data.get('score', 0)
        lsig = layer_data.get('signal', 'N/A')
        lines.append(f"- {kr}: {ls:+.1f} ({lsig})")

    return "\n".join(lines)


def _build_daily_changes_block(daily_changes: Optional[Dict]) -> str:
    """전일 대비 변화 정보를 프롬프트 블록으로 구성.

    Args:
        daily_changes: MarketAnalyzer._calculate_daily_changes() 반환값

    Returns:
        프롬프트에 삽입할 전일 변화 블록 문자열 (데이터 없으면 빈 문자열)
    """
    if not daily_changes or not daily_changes.get('has_previous'):
        return ""

    lines = [f"\n## 전일 대비 변화 (vs {daily_changes.get('previous_date', 'N/A')})"]

    # 인텔리전스 점수 변화
    intel = daily_changes.get('intelligence', {})
    if intel.get('overall_score_change') is not None:
        score_chg = intel['overall_score_change']
        direction = "▲" if score_chg > 0 else "▼" if score_chg < 0 else "━"
        lines.append(f"- 종합 점수 변화: {direction} {score_chg:+.1f}점 (전일 시그널: {intel.get('prev_signal', 'N/A')})")

    layer_changes = intel.get('layer_changes', {})
    if layer_changes:
        layer_parts = [f"{name}: {chg:+.1f}" for name, chg in layer_changes.items()]
        lines.append(f"- 레이어별 변화: {', '.join(layer_parts)}")

    # 종목별 가격 변화 요약
    stock_changes = daily_changes.get('stocks', {})
    if stock_changes:
        lines.append("- 종목별 전일비:")
        for sym, chg in stock_changes.items():
            parts = []
            if 'price_change_pct' in chg:
                parts.append(f"가격 {chg['price_change_pct']:+.2f}%")
            if 'rsi_change' in chg:
                parts.append(f"RSI {chg['rsi_change']:+.1f}")
            lines.append(f"  - {sym}: {', '.join(parts)}")

    lines.append("")
    return "\n".join(lines)


def _compute_top3_candidates(
    market_data: Dict,
    daily_changes: Optional[Dict] = None,
    intelligence_data: Optional[Dict] = None,
    previous_top3: Optional[list] = None,
) -> Tuple[str, List[str]]:
    """결정론적 TOP 3 종목 선정.

    StockRanker를 사용하여 종목을 점수화하고 순위를 결정합니다.

    Returns:
        (랭킹 텍스트 블록, TOP 3 심볼 리스트)
    """
    from trading_bot.stock_ranker import StockRanker

    stocks = market_data.get('stocks', {})
    if not stocks:
        return "", []

    ranker = StockRanker()
    ranked = ranker.rank(
        stocks_data=stocks,
        intelligence_data=intelligence_data,
        daily_changes=daily_changes,
        previous_top3=previous_top3,
    )

    if not ranked:
        return "", []

    top3_symbols = [r['symbol'] for r in ranked[:3]]

    lines = ["\n## 코드 기반 종목 랭킹 (확정 — 이 순위대로 분석을 작성하세요)"]
    lines.append("아래 TOP 3는 10개 기술 지표, 모멘텀, 레짐, 변화율을 종합하여 **코드로 결정**된 순위입니다.")
    lines.append("각 종목에 대해 기술적 근거, 뉴스, 전망을 분석하세요. **순위는 변경하지 마세요.**\n")

    for i, item in enumerate(ranked[:8], 1):
        reasons_str = ", ".join(item['reasons'][:3]) if item['reasons'] else "변동 작음"
        if i <= 3:
            prefix = f"**[TOP {i}]**"
        else:
            prefix = f"{i}."
        lines.append(f"{prefix} **{item['symbol']}** (점수: {item['total_score']:.0f}) — {reasons_str}")

    return "\n".join(lines), top3_symbols


def _load_previous_top3(analysis_dir: str, today: str) -> Optional[list]:
    """이전 Notion 리포트의 TOP 3 종목을 로드합니다.

    .top3 마커 파일에서 읽거나, 없으면 None을 반환합니다.
    """
    from pathlib import Path
    from datetime import datetime, timedelta

    try:
        today_date = datetime.strptime(today, "%Y-%m-%d")
        for days_back in range(1, 4):  # 최대 3일 전까지 탐색
            prev_date = (today_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
            marker = Path(analysis_dir) / f"{prev_date}.json.top3"
            if marker.exists():
                return json.loads(marker.read_text())
    except Exception:
        pass
    return None


def _save_top3_marker(json_path: str, top3_symbols: list) -> None:
    """TOP 3 종목을 마커 파일로 저장합니다."""
    from pathlib import Path
    marker = Path(json_path).with_suffix(Path(json_path).suffix + ".top3")
    marker.write_text(json.dumps(top3_symbols))


def _build_historical_performance_block() -> str:
    """SignalTracker에서 최근 30일 시그널 정확도 → 프롬프트 텍스트.

    RAG 컨텍스트로 과거 시그널 성과를 주입하여 LLM이 참고하도록 합니다.
    SIGNAL_TRACKING_ENABLED=false이거나 데이터 없으면 빈 문자열 반환.
    """
    if os.getenv('SIGNAL_TRACKING_ENABLED', 'true').lower() != 'true':
        return ''

    try:
        from trading_bot.signal_tracker import SignalTracker
        tracker = SignalTracker()
        summary = tracker.get_recent_accuracy_summary(lookback_days=30)
        if not summary:
            return ''

        overall = summary.get('overall', {})
        total = overall.get('total_signals', 0)
        if total == 0:
            return ''

        correct = overall.get('correct_count', 0)
        accuracy = overall.get('accuracy_pct')
        avg_bullish = overall.get('avg_return_when_bullish')
        avg_bearish = overall.get('avg_return_when_bearish')

        lines = [
            "\n## 과거 시그널 성과 (최근 30일)",
            f"- 전체 정확도: {accuracy:.1f}% ({correct}/{total}건)" if accuracy is not None else f"- 전체: {total}건 (정확도 미측정)",
        ]

        if avg_bullish is not None:
            lines.append(f"- Bullish 시그널 평균 5일 수익: {avg_bullish:+.1f}%")
        if avg_bearish is not None:
            lines.append(f"- Bearish 시그널 평균 5일 수익: {avg_bearish:+.1f}%")

        # 레이어별 정확도
        layers = summary.get('layers', {})
        if layers:
            best_layer = max(layers.items(), key=lambda x: x[1].get('accuracy_pct') or 0)
            worst_layer = min(layers.items(), key=lambda x: x[1].get('accuracy_pct') or 100)
            if best_layer[1].get('accuracy_pct') is not None:
                lines.append(f"- 가장 정확한 레이어: {best_layer[0]} ({best_layer[1]['accuracy_pct']:.0f}%)")
            if worst_layer[1].get('accuracy_pct') is not None:
                lines.append(f"- 가장 부정확한 레이어: {worst_layer[0]} ({worst_layer[1]['accuracy_pct']:.0f}%)")

        lines.append("**이 과거 데이터를 참고하여 오늘의 분석 신뢰도를 판단하세요.**")
        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"RAG 컨텍스트 빌드 실패: {e}")
        return ''


def _calculate_var_95(snapshots: List[Dict]) -> Optional[float]:
    """
    95% VaR를 히스토리컬 시뮬레이션으로 계산합니다.

    Args:
        snapshots: 포트폴리오 스냅샷 리스트 (total_value 키 포함)

    Returns:
        95% VaR 값 (퍼센트), 데이터 부족 시 None
    """
    if len(snapshots) < 3:
        return None

    values = [s.get('total_value', s.get('equity', 0)) for s in snapshots]
    returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            returns.append((values[i] - values[i - 1]) / values[i - 1])

    if len(returns) < 2:
        return None

    sorted_returns = sorted(returns)
    index = int(len(sorted_returns) * 0.05)
    var_95 = sorted_returns[index] * 100
    return round(var_95, 4)


def _calculate_strategy_pnl_breakdown(trades: List[Dict]) -> List[Dict]:
    """
    전략별 PnL 분석을 계산합니다.

    Args:
        trades: 거래 리스트 (symbol, type, pnl 키 포함)

    Returns:
        전략(심볼)별 PnL 분석 딕셔너리 리스트
    """
    if not trades:
        return []

    sell_trades = [t for t in trades if t.get('type') == 'SELL']
    if not sell_trades:
        return []

    # 심볼별 그룹핑
    symbol_pnl: Dict[str, List[float]] = {}
    for t in sell_trades:
        symbol = t.get('symbol', 'N/A')
        pnl = t.get('pnl', 0)
        if symbol not in symbol_pnl:
            symbol_pnl[symbol] = []
        symbol_pnl[symbol].append(pnl)

    breakdown = []
    for symbol, pnls in sorted(symbol_pnl.items()):
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        breakdown.append({
            'symbol': symbol,
            'total_pnl': round(total_pnl, 2),
            'trade_count': len(pnls),
            'win_count': len(wins),
            'loss_count': len(losses),
            'avg_pnl': round(total_pnl / len(pnls), 2) if pnls else 0,
            'max_win': round(max(wins), 2) if wins else 0,
            'max_loss': round(min(losses), 2) if losses else 0,
        })

    return breakdown


def _format_trade_log(trades: List[Dict], limit: int = 50) -> List[Dict]:
    """
    거래 로그를 통합하여 최근 N건을 반환합니다.

    Args:
        trades: 전체 거래 리스트
        limit: 반환할 최대 건수

    Returns:
        최근 거래 딕셔너리 리스트
    """
    if not trades:
        return []

    formatted = []
    for t in trades:
        formatted.append({
            'timestamp': t.get('timestamp', 'N/A'),
            'symbol': t.get('symbol', 'N/A'),
            'type': t.get('type', 'N/A'),
            'price': t.get('price', 0),
            'size': t.get('size', 0),
            'pnl': t.get('pnl'),
            'commission': t.get('commission', 0),
        })

    # 타임스탬프 기준 정렬 (최신순)
    formatted.sort(key=lambda x: x['timestamp'], reverse=True)
    return formatted[:limit]


def precompute_session_metrics(session_reports_dir: str) -> Dict[str, Any]:
    """
    세션 리포트 디렉토리에서 고급 메트릭을 사전 계산합니다.

    _load_session_reports()로 세션 데이터를 로드하고,
    VaR(95%), 전략별 PnL, 통합 거래 로그 등을 계산합니다.

    Args:
        session_reports_dir: 세션 리포트 JSON 파일들이 있는 디렉토리 경로

    Returns:
        사전 계산된 메트릭 딕셔너리:
        - sessions: 세션 요약 리스트
        - has_sessions: 세션 데이터 존재 여부
        - var_95: 전체 VaR(95%) 값
        - strategy_pnl_breakdown: 전략별 PnL 분석
        - trade_log: 통합 거래 로그 (최근 50건)
        - session_details: 세션별 상세 메트릭
    """
    sessions = _load_session_reports(session_reports_dir)

    if not sessions:
        return {
            'sessions': [],
            'has_sessions': False,
            'var_95': None,
            'strategy_pnl_breakdown': [],
            'trade_log': [],
            'session_details': [],
        }

    # 리포트 파일 직접 읽기 (스냅샷, 거래 데이터)
    import glob as glob_module
    pattern = os.path.join(session_reports_dir, "*_report.json")
    report_files = sorted(glob_module.glob(pattern))

    all_trades: List[Dict] = []
    all_snapshots: List[Dict] = []
    session_details: List[Dict] = []
    calc = PerformanceCalculator()

    for fpath in report_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                report = json.load(f)

            summary = report.get("summary", {})
            trades = report.get("trades", [])
            snapshots = report.get("snapshots", [])

            all_trades.extend(trades)
            all_snapshots.extend(snapshots)

            # 세션별 상세 메트릭
            profit_factor = calc.calculate_profit_factor(trades)
            var_95 = _calculate_var_95(snapshots)

            session_details.append({
                'session_id': report.get('session_id', 'N/A'),
                'display_name': summary.get('display_name', summary.get('strategy_name', 'N/A')),
                'strategy_name': summary.get('strategy_name', 'N/A'),
                'total_return': summary.get('total_return', 0),
                'sharpe_ratio': summary.get('sharpe_ratio'),
                'max_drawdown': summary.get('max_drawdown', 0),
                'win_rate': summary.get('win_rate'),
                'profit_factor': profit_factor,
                'var_95': var_95,
                'total_trades': len(trades),
                'initial_capital': summary.get('initial_capital', 0),
                'final_capital': summary.get('final_capital', 0),
            })
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"세션 리포트 상세 로드 실패: {fpath} - {e}")

    # 전체 메트릭 계산
    overall_var_95 = _calculate_var_95(all_snapshots)
    strategy_pnl = _calculate_strategy_pnl_breakdown(all_trades)
    trade_log = _format_trade_log(all_trades)

    return {
        'sessions': sessions,
        'has_sessions': True,
        'var_95': overall_var_95,
        'strategy_pnl_breakdown': strategy_pnl,
        'trade_log': trade_log,
        'session_details': session_details,
    }


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
    # 5-Layer Intelligence 블록 (있을 때만)
    intel_block = _build_intelligence_block(intelligence_data)

    # RAG 컨텍스트 (과거 시그널 성과)
    rag_block = _build_historical_performance_block()

    # stocks 데이터만 추출 (뉴스, fear_greed 제외)
    data_for_worker = {
        'market_summary': market_data.get('market_summary', {}),
        'stocks': market_data.get('stocks', {}),
    }
    json_str = json.dumps(data_for_worker, ensure_ascii=False, indent=2)

    symbols = list(market_data.get('stocks', {}).keys())
    symbols_str = ", ".join(symbols)

    # 매크로 시장 환경 데이터 블록
    macro_block = ""
    if macro_data:
        ml = []

        # 지수
        ml.append("### 주요 지수 현황")
        for sym, info in macro_data.get('indices', {}).items():
            chg_1d = info.get('chg_1d', 0)
            chg_5d = info.get('chg_5d', 0)
            chg_20d = info.get('chg_20d', 0)
            s1 = '+' if chg_1d and chg_1d > 0 else ''
            s5 = '+' if chg_5d > 0 else ''
            s20 = '+' if chg_20d and chg_20d > 0 else ''
            ml.append(f"- **{sym}**: ${info.get('last', 'N/A')} (1일 {s1}{chg_1d}%, 5일 {s5}{chg_5d}%, 20일 {s20}{chg_20d}%, RSI {info.get('rsi', 'N/A')})")

        # 섹터 (rank 순)
        ml.append("\n### 섹터 상대강도 (5일/20일 수익률)")
        sectors = sorted(macro_data.get('sectors', {}).items(), key=lambda x: x[1].get('rank_5d', 99))
        for sym, info in sectors:
            chg_5d = info.get('chg_5d', 0)
            chg_20d = info.get('chg_20d', 0)
            s5 = '+' if chg_5d > 0 else ''
            s20 = '+' if chg_20d and chg_20d > 0 else ''
            r20 = info.get('rank_20d', '?')
            ml.append(f"- #{info.get('rank_5d', '?')} **{info.get('name', sym)}**({sym}): 5일 {s5}{chg_5d}%, 20일 {s20}{chg_20d}% (20일순위 #{r20}, RSI {info.get('rsi', 'N/A')})")

        # 로테이션
        rot = macro_data.get('rotation', {})
        if rot:
            ml.append(f"\n### 섹터 로테이션: {rot.get('signal', 'N/A')}")
            ml.append(f"- 공격적 섹터 평균: {rot.get('offensive_avg_5d', 'N/A')}%")
            ml.append(f"- 방어적 섹터 평균: {rot.get('defensive_avg_5d', 'N/A')}%")

        # 시장 폭
        breadth = macro_data.get('breadth', {})
        if breadth:
            ml.append(f"\n### 시장 폭: {breadth.get('interpretation', 'N/A')}")
            ml.append(f"- SPY vs IWM 5일 괴리: {breadth.get('spy_vs_iwm_5d', 'N/A')}%p")
            ml.append(f"- 상승 섹터: {breadth.get('sectors_positive_5d', 0)}개 / 하락: {breadth.get('sectors_negative_5d', 0)}개")

        # 리스크 환경
        risk = macro_data.get('risk_environment', {})
        if risk:
            ml.append(f"\n### 리스크 환경: {risk.get('assessment', 'N/A')}")
            ml.append(f"- TLT(국채): {risk.get('tlt_chg_5d', 'N/A')}%")
            ml.append(f"- GLD(금): {risk.get('gld_chg_5d', 'N/A')}%")
            ml.append(f"- HYG(하이일드): {risk.get('hyg_chg_5d', 'N/A')}%")

        # 종합
        overall = macro_data.get('overall', '')
        if overall:
            ml.append(f"\n### 종합: {overall}")

        macro_block = "\n## 매크로 시장 환경 데이터\n" + "\n".join(ml)

    # 이벤트 캘린더 블록 (있을 때만)
    events_block = _build_events_data_block(events_data) if events_data else ""

    # 펀더멘탈 데이터 블록 (있을 때만)
    fundamentals_block = _build_fundamentals_data_block(fundamentals_data) if fundamentals_data else ""

    # Fear & Greed 데이터 블록 (있을 때만)
    fg_block = ""
    if fear_greed_data:
        current = fear_greed_data.get('current', {})
        if isinstance(current, dict) and current.get('value') is not None:
            fg_block = f"""
## Fear & Greed Index (CNN)
- 현재 값: {current.get('value')} ({current.get('classification', 'N/A')})
- 이전 종가: {fear_greed_data.get('previous_close', {}).get('value', 'N/A')} ({fear_greed_data.get('previous_close', {}).get('classification', 'N/A')})
- 1주 전: {fear_greed_data.get('one_week_ago', {}).get('value', 'N/A')} ({fear_greed_data.get('one_week_ago', {}).get('classification', 'N/A')})
- 1개월 전: {fear_greed_data.get('one_month_ago', {}).get('value', 'N/A')} ({fear_greed_data.get('one_month_ago', {}).get('classification', 'N/A')})

위 Fear & Greed 데이터를 공포탐욕 지수 행에 정확히 반영하세요.
"""

    # 전일 대비 변화 블록
    daily_changes_block = _build_daily_changes_block(daily_changes)

    # 매크로 섹션 템플릿 (있을 때만)
    macro_section_template = ""
    if macro_data:
        macro_section_template = MACRO_SECTION_TEMPLATE_PARALLEL

    if macro_data:
        section_spec = "**섹션 0, 섹션 1, 섹션 2를**"
        section_note = "섹션 0(매크로 시장 환경), 1, 2만 출력합니다"
    else:
        section_spec = "**섹션 1과 섹션 2만**"
        section_note = "섹션 1과 2만 출력합니다"

    prompt = f"""당신은 시장 분석 워커 A입니다.
아래 JSON 데이터를 분석하여 {section_spec} Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. {section_note}.

## WebSearch 활용 지시
- WebSearch 도구를 사용하여 각 종목의 최신 뉴스와 시장 동향을 검색하세요.
{intel_block}
{rag_block}
- 특히 극단적 과매도/과매수, 급등/급락 종목의 뉴스를 심층 검색하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.
{macro_block}
{events_block}
{fundamentals_block}
{fg_block}
{daily_changes_block}
## 대상 종목
{symbols_str} ({len(symbols)}개)

{_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---
""" + macro_section_template + r"""
# 1. 시장 전체 요약 {color="blue"}
::: callout {icon="📅" color="gray_bg"}
""" + f"""\t**분석 일자**: {today}  \\|  **대상 종목**: {len(symbols)}개 ({symbols_str})
:::""" + r"""
## 오늘의 시장 상황
[2-3 paragraphs analyzing today's market based on the provided data + WebSearch news]

## 주요 지표 요약
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**지표**</td>
<td>**값**</td>
<td>**해석**</td>
</tr>
<tr>
<td>평균 RSI</td>
<td>**{value}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>강세 종목 수</td>
<td>**{value}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>약세 종목 수</td>
<td>**{value}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>횡보 종목 수</td>
<td>**{value}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>공포탐욕 지수</td>
<td>**{value}**</td>
<td>[interpretation]</td>
</tr>
</table>

## 전반적인 시장 분위기
::: callout {icon="⚠️" color="red_bg"}
(Use red_bg for bearish, green_bg for bullish, yellow_bg for neutral. Choose appropriate emoji.)
	**[강세/약세/중립] ([Bullish/Bearish/Neutral])** — [explanation with data]
:::
---
# 2. 종목별 분석 {color="blue"}
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가 (\$)**</td>
<td>**5일 변화**</td>
<td>**20일 변화**</td>
<td>**RSI**</td>
<td>**MACD**</td>
<td>**레짐**</td>
<td>**주요 시그널**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable stocks (oversold/overbought/extreme moves)
<td>**{SYMBOL}**</td>
<td>{price}</td>
<td><span color="red">{negative%}</span> or <span color="green">{positive%}</span></td>
<td><span color="red">{negative%}</span> or <span color="green">{positive%}</span></td>
<td>{rsi} ({label})</td>
<td><span color="red">Bearish</span> or <span color="green">Bullish</span></td>
<td>{REGIME} ({confidence}%)</td>
<td>{signal_notes}</td>
</tr>
[... repeat for all stocks]
</table>
---

--- END EXACT OUTPUT STRUCTURE ---
""" + f"""
JSON 데이터:
```json
{json_str}
```"""

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
    # 5-Layer Intelligence 요약 (Top 3 선정 참고용)
    intel_summary = _build_intelligence_summary(intelligence_data)

    # 코드 기반 종목 랭킹 (확정 TOP 3)
    top3_ranking, top3_symbols = _compute_top3_candidates(
        market_data, daily_changes, intelligence_data, previous_top3
    )

    # 이전 TOP 3 중복 방지
    prev_top3_block = ""
    if previous_top3:
        prev_top3_block = f"""
## 이전 리포트 TOP 3
어제 TOP 3: {', '.join(previous_top3)}
위 랭킹에는 이미 중복 감점이 적용되었습니다. 재선정된 종목이 있다면 새로운 촉매를 반드시 명시하세요.
"""

    # RAG 컨텍스트 (과거 시그널 성과)
    rag_block = _build_historical_performance_block()

    # Reflection 컨텍스트 (Worker A 출력 교차 검증)
    reflection_block = ""
    if worker_a_context:
        reflection_block = f"""
## Worker-A 분석 결과 (교차 검증용)
아래 분석과 일치하는지 확인하고, 불일치 시 이유를 명시하세요.
{worker_a_context}
"""

    # 종목 데이터 경량화 (Worker B는 Top 3 선정과 뉴스 분석이 목적이므로 핵심 지표만 추출)
    stocks_compact = {}
    for sym, sdata in market_data.get('stocks', {}).items():
        price_info = sdata.get('price', {})
        indicators = sdata.get('indicators', {})
        regime = sdata.get('regime', {})
        patterns = sdata.get('patterns', {})
        stocks_compact[sym] = {
            'price': {
                'last': price_info.get('last'),
                'change_1d': price_info.get('change_1d'),
                'change_5d': price_info.get('change_5d'),
                'change_20d': price_info.get('change_20d'),
            },
            'indicators': {
                'rsi': indicators.get('rsi', {}),
                'macd': {'signal': indicators.get('macd', {}).get('signal')},
                'bollinger': {'signal': indicators.get('bollinger', {}).get('signal')},
                'adx': indicators.get('adx', {}).get('value'),
            },
            'regime': {'state': regime.get('state'), 'confidence': regime.get('confidence')},
            'support_levels': patterns.get('support_levels', [])[:3],
        }
    stocks_json = json.dumps(stocks_compact, ensure_ascii=False, indent=2)

    # 뉴스 블록 구성
    news_block = ""
    if news_data:
        news_lines = []
        market_news = news_data.get('market_news', [])
        if market_news:
            news_lines.append("### 시장 전체 뉴스")
            for item in market_news:
                news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        stock_news = news_data.get('stock_news', {})
        if stock_news:
            news_lines.append("\n### 종목별 뉴스")
            for symbol, items in stock_news.items():
                news_lines.append(f"\n**{symbol}**:")
                for item in items[:3]:
                    news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        news_block = "\n## 수집된 뉴스 데이터\n" + "\n".join(news_lines)

    # Fear & Greed 블록 구성
    fg_block = ""
    if fear_greed_data:
        current = fear_greed_data.get('current', {})
        fg_lines = []
        fg_lines.append("### 현재 Fear & Greed Index")
        fg_lines.append(f"- **값**: {current.get('value', 'N/A')}")
        fg_lines.append(f"- **분류**: {current.get('classification', 'N/A')}")
        fg_lines.append(f"- **시각**: {current.get('timestamp', 'N/A')}")

        history = fear_greed_data.get('history', [])
        if history:
            fg_lines.append(f"\n### 최근 {len(history)}일 히스토리")
            for item in history[:7]:
                fg_lines.append(f"- {item['date']}: {item['value']} ({item['classification']})")
            if len(history) > 7:
                fg_lines.append(f"- ... 외 {len(history) - 7}일")

        chart_path = fear_greed_data.get('chart_path')
        if chart_path:
            fg_lines.append(f"\n### 차트")
            fg_lines.append(f"- 차트 파일 경로: `{chart_path}`")
            fg_lines.append(f"- Read 도구로 이 차트 이미지를 읽어서 시각적 분석에 반영하세요.")

        fg_block = "\n## 공포/탐욕 지수 (Fear & Greed Index)\n" + "\n".join(fg_lines)

    prompt = f"""당신은 시장 분석 워커 B입니다.
아래 데이터를 분석하여 **섹션 3, 4, 5만** Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 섹션 3, 4, 5만 출력합니다.

## WebSearch + Read 도구 활용 지시 (예산 절약 중요!)
- WebSearch는 **최대 3회**만 사용하세요 (예: Top 3 종목 각각 1회씩, 또는 시장 전체 1회 + 주요 종목 2회).
- Read: Fear & Greed 차트 이미지 파일이 있으면 **1회**만 읽으세요.
- 이미 수집된 뉴스 데이터가 아래에 있으므로, WebSearch는 추가 확인이 필요한 경우에만 사용하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.
- **중요**: 도구 호출보다 최종 마크다운 출력 생성을 우선하세요. 예산이 부족하면 도구 호출을 줄이세요.
{intel_summary}
{top3_ranking}
{prev_top3_block}
{rag_block}
{reflection_block}
{news_block}
{fg_block}

{_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---
""" + r"""
# 3. 주목할 종목 Top 3 {color="blue"}
## 🥇 1위: {SYMBOL} ({Company}) — {action recommendation}
::: callout {icon="📌" color="yellow_bg"}
	**현재가**: \${price}  \|  **20일 변화**: {change}  \|  **RSI**: {rsi}  \|  **레짐**: {regime}
:::
**선정 이유 및 기술적 근거**:
- [bullet points with technical analysis]
- **지지선**: \${support1} / \${support2}

**뉴스 근거**: [news-based analysis with sources]

> **의견**: [emoji] **[recommendation]** — [detailed reasoning with price targets]
---
(Repeat same structure for 🥈 2위 and 🥉 3위)
---
# 4. 공포/탐욕 지수 분석 {color="blue"}
## 현재 Fear & Greed Index
::: callout {icon="😰" color="red_bg"}
(Choose emoji and color based on value: 😰/red_bg for fear, 😊/green_bg for greed, 😐/yellow_bg for neutral)
	**현재값: {value} ({classification})** — [interpretation]
	측정 시각: {timestamp}
:::
## 차트 시각적 분석 (30일 히스토리)
[analysis of the Fear & Greed chart if chart image was provided]
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**기간**</td>
<td>**지수 범위**</td>
<td>**분류**</td>
<td>**특이사항**</td>
</tr>
<tr color="green_bg"> or <tr color="red_bg"> or <tr color="yellow_bg"> based on sentiment period
<td>{period}</td>
<td>{range}</td>
<td>{classification}</td>
<td>{notes}</td>
</tr>
[... periods]
</table>
## 최근 추세 변화 해석
[numbered analysis points]
## 기술적 지표와의 상관관계
[bullet points correlating F&G with RSI and other indicators]
::: callout {icon="💡" color="blue_bg"}
	**역발상 투자 관점**: [contrarian analysis]
:::
---
# 5. 뉴스 & 이벤트 분석 {color="blue"}
## 시장 전체 주요 뉴스
<details>
<summary>📰 거시경제 & 시장 이벤트</summary>
	[numbered news items with sources]
</details>
## 종목별 핵심 뉴스 분석
### [Theme/Category] ([affected symbols])
::: callout {icon="🤖" color="orange_bg"}
	**핵심 이슈**: [key issue description with source links]
:::
[bullet points per symbol]
[... more themes as needed]
## 기술적 지표 vs 뉴스 일치성 분석
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**기술적 시그널**</td>
<td>**뉴스 방향**</td>
<td>**일치 여부**</td>
</tr>
<tr>
<td>{symbol}</td>
<td>{technical}</td>
<td>{news}</td>
<td>✅ 일치 or ⚠️ 혼재 or ❌ 불일치</td>
</tr>
[... all symbols]
</table>
---

--- END EXACT OUTPUT STRUCTURE ---
""" + f"""
종목 데이터:
```json
{stocks_json}
```"""

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
    # 5-Layer Intelligence 요약 (전략 파라미터 제안 참고용)
    intel_summary = _build_intelligence_summary(intelligence_data)

    # 종목 데이터 (전략 파라미터/전망용)
    stocks_json = json.dumps(market_data.get('stocks', {}), ensure_ascii=False, indent=2)

    # 세션 메트릭 JSON
    metrics_json = ""
    if has_sessions:
        metrics_for_prompt = {
            'session_details': session_metrics.get('session_details', []),
            'var_95': session_metrics.get('var_95'),
            'strategy_pnl_breakdown': session_metrics.get('strategy_pnl_breakdown', []),
            'trade_log': session_metrics.get('trade_log', [])[:20],  # 프롬프트 경량화
        }
        metrics_json = json.dumps(metrics_for_prompt, ensure_ascii=False, indent=2)

    # 전일 대비 변화 블록
    daily_changes_block = _build_daily_changes_block(daily_changes)

    # 전방 전망용 데이터 (지지선, RSI 임계치 근접 종목)
    forward_data = _extract_forward_look_data(market_data)
    forward_json = json.dumps(forward_data, ensure_ascii=False, indent=2)

    if has_sessions:
        # 세션 있을 때: 섹션 6, 7, 8, 9, 10
        section_structure = _build_worker_c_sections_with_sessions()
        session_data_block = f"""
## 세션 메트릭 데이터
```json
{metrics_json}
```"""
    else:
        # 세션 없을 때: 섹션 6, 7(전방전망), 8(리스크)
        section_structure = _build_worker_c_sections_without_sessions()
        session_data_block = ""

    prompt = f"""당신은 시장 분석 워커 C입니다.
아래 데이터를 분석하여 아래 지정된 섹션만 Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 지정된 섹션만 출력합니다.
**중요**: 도구(WebSearch, Read 등)는 사용하지 마세요. 주어진 데이터만으로 분석하세요.
{intel_summary}
{daily_changes_block}

{_FORMAT_RULES}

{section_structure}
{session_data_block}

## 전방 전망 데이터 (지지선/RSI 임계치 근접)
```json
{forward_json}
```

종목 데이터:
```json
{stocks_json}
```"""

    logger.info(f"Worker C 프롬프트 생성 완료 (길이: {len(prompt)}자, 세션: {has_sessions})")
    return prompt


def _extract_forward_look_data(market_data: Dict) -> Dict[str, Any]:
    """
    전방 전망 섹션에 필요한 데이터를 추출합니다.

    지지선/저항선, RSI 임계치 근접 종목(±3 이내) 등을 추출합니다.

    Args:
        market_data: 시장 분석 JSON 데이터

    Returns:
        전방 전망용 데이터 딕셔너리
    """
    stocks = market_data.get('stocks', {})
    support_resistance = {}
    rsi_pending_signals = []

    for symbol, data in stocks.items():
        # 지지선 추출
        patterns = data.get('patterns', {})
        support_levels = patterns.get('support_levels', [])
        if support_levels:
            support_resistance[symbol] = {
                'support_levels': support_levels,
                'current_price': data.get('price', {}).get('last', 0),
            }

        # RSI 임계치 근접 종목 (±3 이내)
        indicators = data.get('indicators', {})
        rsi_val = indicators.get('rsi', {}).get('value')
        if rsi_val is not None:
            # signal_diagnosis에서 최적 범위 추출
            diagnosis = data.get('signal_diagnosis', {})
            optimal = diagnosis.get('optimal_rsi_range', {})
            oversold = optimal.get('oversold', 30)
            overbought = optimal.get('overbought', 70)

            if abs(rsi_val - oversold) <= 3:
                rsi_pending_signals.append({
                    'symbol': symbol,
                    'rsi': rsi_val,
                    'threshold': oversold,
                    'type': 'near_oversold',
                    'distance': round(rsi_val - oversold, 1),
                })
            elif abs(rsi_val - overbought) <= 3:
                rsi_pending_signals.append({
                    'symbol': symbol,
                    'rsi': rsi_val,
                    'threshold': overbought,
                    'type': 'near_overbought',
                    'distance': round(rsi_val - overbought, 1),
                })

    return {
        'support_resistance': support_resistance,
        'rsi_pending_signals': rsi_pending_signals,
    }


def _build_worker_c_sections_with_sessions() -> str:
    """세션이 있을 때의 Worker C 출력 구조를 반환합니다 (섹션 6-10)."""
    return r"""--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 6. 전략 파라미터 제안 {color="blue"}
## 현재 시장 환경 평가
[bullet points]
## RSI 파라미터 제안
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**최적 Oversold**</td>
<td>**최적 Overbought**</td>
<td>**근거**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable entries
<td>{symbol}</td>
<td>**{oversold}**</td>
<td>{overbought}</td>
<td>{reason}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {icon="📊" color="yellow_bg"}
	**[MACD recommendation]**
	[details]
:::
## 추천 전략
[numbered strategy recommendations]
---
# 7. 성과 대시보드 {color="blue"}
## 전략별 성과 테이블
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**세션**</td>
<td>**수익률**</td>
<td>**Sharpe**</td>
<td>**Profit Factor**</td>
<td>**Max DD**</td>
<td>**VaR(95%)**</td>
<td>**Win Rate**</td>
</tr>
[... rows from session_details data, use color="orange_bg" for negative returns]
</table>
## PnL 기여도 분석
[analysis based on strategy_pnl_breakdown data - which symbols contributed most/least]
## 거래 로그
<details>
<summary>📋 최근 거래 내역 (최대 20건)</summary>
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**시간**</td>
<td>**종목**</td>
<td>**유형**</td>
<td>**가격**</td>
<td>**수량**</td>
<td>**PnL**</td>
</tr>
[... rows from trade_log data]
</table>
</details>
---
# 8. 트레이딩 세션 분석 {color="blue"}
## 세션 실행 결과
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**세션**</td>
<td>**전략**</td>
<td>**초기 자본**</td>
<td>**최종 자본**</td>
<td>**수익률**</td>
<td>**거래 횟수**</td>
</tr>
[... rows from session_details data]
</table>
## 세션별 분석
[per-session analysis: strategy effectiveness, trades detail if any, comparison between sessions]
## 전략 효과 평가
::: callout {icon="📈" color="blue_bg"}
	[evaluation of strategy effectiveness based on session results and market conditions]
:::
---
# 9. 전방 전망 {color="blue"}
## 주요 지지선/저항선
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가**</td>
<td>**지지선 1**</td>
<td>**지지선 2**</td>
<td>**지지선 3**</td>
<td>**현재가 대비 거리**</td>
</tr>
[... rows from support_resistance data]
</table>
## RSI 시그널 대기 종목
::: callout {icon="🔔" color="yellow_bg"}
[list stocks where RSI is within ±3 of their oversold/overbought thresholds from rsi_pending_signals]
:::
## 향후 주시 사항
[numbered points about what to watch for tomorrow/this week based on data]
---
# 10. 리스크 요인 {color="blue"}
## 시장 주요 리스크
[numbered risk items based on market data analysis]
## 변동성 이상 종목
<table fit-page-width="true" header-row="true">
<tr color="red_bg">
<td>**종목**</td>
<td>**리스크 유형**</td>
<td>**주의 사항**</td>
</tr>
[... rows for high-volatility or extreme-move stocks]
</table>
## 뉴스 기반 잠재 리스크
[bullet points - infer from data patterns, regime states, extreme indicators]
---

--- END EXACT OUTPUT STRUCTURE ---"""


def _build_worker_c_sections_without_sessions() -> str:
    """세션이 없을 때의 Worker C 출력 구조를 반환합니다 (섹션 6, 7, 8)."""
    return r"""--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 6. 전략 파라미터 제안 {color="blue"}
## 현재 시장 환경 평가
[bullet points]
## RSI 파라미터 제안
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**최적 Oversold**</td>
<td>**최적 Overbought**</td>
<td>**근거**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable entries
<td>{symbol}</td>
<td>**{oversold}**</td>
<td>{overbought}</td>
<td>{reason}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {icon="📊" color="yellow_bg"}
	**[MACD recommendation]**
	[details]
:::
## 추천 전략
[numbered strategy recommendations]
---
# 7. 전방 전망 {color="blue"}
## 주요 지지선/저항선
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가**</td>
<td>**지지선 1**</td>
<td>**지지선 2**</td>
<td>**지지선 3**</td>
<td>**현재가 대비 거리**</td>
</tr>
[... rows from support_resistance data]
</table>
## RSI 시그널 대기 종목
::: callout {icon="🔔" color="yellow_bg"}
[list stocks where RSI is within ±3 of their oversold/overbought thresholds from rsi_pending_signals]
:::
## 향후 주시 사항
[numbered points about what to watch for tomorrow/this week based on data]
---
# 8. 리스크 요인 {color="blue"}
## 시장 주요 리스크
[numbered risk items based on market data analysis]
## 변동성 이상 종목
<table fit-page-width="true" header-row="true">
<tr color="red_bg">
<td>**종목**</td>
<td>**리스크 유형**</td>
<td>**주의 사항**</td>
</tr>
[... rows for high-volatility or extreme-move stocks]
</table>
## 뉴스 기반 잠재 리스크
[bullet points - infer from data patterns, regime states, extreme indicators]
---

--- END EXACT OUTPUT STRUCTURE ---"""


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
    prompt = f"""아래 콘텐츠를 Notion 페이지로 생성하세요.

Notion MCP 도구(notion-create-pages)를 사용하여 다음 설정으로 페이지를 생성하세요:
- 상위 페이지 ID: {parent_page_id}
- 페이지 제목: "📊 시장 분석 | {today}"

**중요**:
- 아래 콘텐츠를 그대로 페이지 content로 사용하세요.
- 콘텐츠를 수정하거나 재작성하지 마세요.
- notion-create-pages 도구만 호출하면 됩니다.
- 페이지 생성 후, 반드시 마지막에 생성된 페이지의 URL을 "NOTION_PAGE_URL: https://..." 형식으로 출력하세요.

--- 페이지 콘텐츠 시작 ---
{assembled_content}
--- 페이지 콘텐츠 끝 ---"""

    logger.info(f"Notion Writer 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


def _validate_format_rules(content: str) -> List[str]:
    """
    Notion Enhanced Markdown 포맷 규칙 위반을 감지합니다.

    Returns:
        발견된 위반 사항 리스트 (빈 리스트면 문제 없음)
    """
    import re
    warnings = []

    # 1. callout 블록 쌍 매칭 검사 (::: 열기/닫기)
    callout_opens = len(re.findall(r'^::: callout', content, re.MULTILINE))
    callout_closes = content.count('\n:::\n') + (1 if content.rstrip().endswith(':::') else 0)
    if callout_opens != callout_closes:
        warnings.append(f"callout 블록 불일치: 열기 {callout_opens}개, 닫기 {callout_closes}개")

    # 2. 테이블 태그 쌍 매칭
    table_opens = len(re.findall(r'<table\b', content))
    table_closes = content.count('</table>')
    if table_opens != table_closes:
        warnings.append(f"table 태그 불일치: <table> {table_opens}개, </table> {table_closes}개")

    # 3. 잘못된 color 속성 감지 (따옴표 누락)
    bad_colors = re.findall(r'\{color=([^"}\s][^}]*)\}', content)
    if bad_colors:
        warnings.append(f"color 속성 따옴표 누락: {bad_colors[:3]}")

    # 4. 빈 테이블 행 감지 (<tr> 다음에 바로 </tr>)
    empty_rows = len(re.findall(r'<tr[^>]*>\s*</tr>', content))
    if empty_rows:
        warnings.append(f"빈 테이블 행 {empty_rows}개 감지")

    # 5. 일반 마크다운 코드블록 사용 감지 (Notion에서 미지원)
    code_blocks = len(re.findall(r'```\w+', content))
    if code_blocks:
        warnings.append(f"코드블록 {code_blocks}개 감지 (Notion Enhanced MD에서 비권장)")

    return warnings


def _auto_correct_format(content: str) -> Tuple[str, List[str]]:
    """
    LLM이 자주 범하는 포맷 실수를 자동 교정합니다.

    Returns:
        (교정된 콘텐츠, 교정 내역 리스트)
    """
    import re
    corrections = []
    result = content

    # 1. span color에 잘못된 따옴표 사용 교정
    # <span color='red'> → <span color="red">
    pattern = r"<span color='([^']+)'>"
    if re.search(pattern, result):
        result = re.sub(pattern, r'<span color="\1">', result)
        corrections.append("span color 속성의 작은따옴표를 큰따옴표로 교정")

    # 2. callout 닫기 태그 누락 보완 (열기보다 닫기가 적을 때)
    callout_opens = len(re.findall(r'^::: callout', result, re.MULTILINE))
    callout_closes = result.count('\n:::\n') + (1 if result.rstrip().endswith(':::') else 0)
    if callout_opens > callout_closes:
        missing = callout_opens - callout_closes
        # 파일 끝에 누락된 닫기 태그 추가
        result = result.rstrip() + '\n' + ':::\n' * missing
        corrections.append(f"callout 닫기 태그 {missing}개 보완")

    # 3. 이중 구분선 정리 (---\n---  →  ---)
    while '\n---\n---' in result:
        result = result.replace('\n---\n---', '\n---')
        if "이중 구분선 정리" not in corrections:
            corrections.append("이중 구분선 정리")

    return result, corrections


def assemble_sections(
    worker_a_output: str,
    worker_b_output: str,
    worker_c_output: str,
    today: str,
) -> str:
    """
    워커 출력들을 최종 페이지 콘텐츠로 조립합니다.

    TOC + Worker A + Worker B + Worker C + Footer 순서로 결합합니다.

    Args:
        worker_a_output: Worker A의 출력 (섹션 1, 2)
        worker_b_output: Worker B의 출력 (섹션 3, 4, 5)
        worker_c_output: Worker C의 출력 (섹션 6+)
        today: 분석 날짜 (YYYY-MM-DD)

    Returns:
        조립된 최종 페이지 콘텐츠
    """
    footer = FOOTER_TEMPLATE.format(date=today)

    content = f"""<table_of_contents/>
---
{worker_a_output.strip()}
{worker_b_output.strip()}
{worker_c_output.strip()}
{footer}"""

    # 포맷 자동 교정
    content, corrections = _auto_correct_format(content)
    if corrections:
        logger.info(f"포맷 자동 교정 {len(corrections)}건: {corrections}")

    logger.info(f"섹션 조립 완료 (총 길이: {len(content)}자)")
    return content


def validate_assembly(content: str, expected_sections: List[str]) -> bool:
    """
    조립된 콘텐츠에서 예상되는 섹션 헤더가 순서대로 존재하는지 검증합니다.

    Args:
        content: 조립된 페이지 콘텐츠
        expected_sections: 예상되는 섹션 헤더 리스트 (예: ["# 1.", "# 2.", ...])

    Returns:
        모든 섹션이 순서대로 존재하면 True
    """
    last_pos = -1
    for section in expected_sections:
        pos = content.find(section, last_pos + 1)
        if pos == -1:
            logger.warning(f"섹션 누락: '{section}'")
            return False
        if pos <= last_pos:
            logger.warning(f"섹션 순서 오류: '{section}' (pos={pos}, last={last_pos})")
            return False
        last_pos = pos

    # 포맷 규칙 검증
    format_warnings = _validate_format_rules(content)
    if format_warnings:
        for w in format_warnings:
            logger.warning(f"포맷 경고: {w}")

    logger.info(f"섹션 검증 통과: {len(expected_sections)}개 섹션 모두 확인"
                + (f" (포맷 경고 {len(format_warnings)}건)" if format_warnings else ""))
    return True
