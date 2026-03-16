"""
프롬프트 데이터 준비 모듈.

parallel_prompt_builder.py 와 market_analysis_prompt.py 에서
데이터 준비/가공 로직을 분리한 모듈입니다.
각 워커 프롬프트에 주입할 컨텍스트 딕셔너리를 생성합니다.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =========================================================================
# 순수 헬퍼 함수들 (parallel_prompt_builder.py 에서 이동)
# =========================================================================


def _build_intelligence_block(intelligence_data: Optional[Dict]) -> str:
    """5-Layer 인텔리전스 분석 결과를 프롬프트 블록으로 구성합니다."""
    if not intelligence_data:
        return ""

    lines = ["\n## 5-Layer Market Intelligence 분석 결과"]
    overall = intelligence_data.get("overall", {})
    score = overall.get("score", 0)
    signal = overall.get("signal", "N/A")
    interpretation = overall.get("interpretation", "N/A")

    lines.append(f"**종합 점수**: {score:+.1f} ({signal})")
    lines.append(f"**종합 판단**: {interpretation}")
    lines.append("")
    lines.append("### Layer별 상세 분석")

    layer_names_kr = {
        "macro_regime": "Layer 1: 매크로 레짐",
        "market_structure": "Layer 2: 시장 구조",
        "sector_rotation": "Layer 3: 섹터/팩터 로테이션",
        "enhanced_technicals": "Layer 4: 기술적 분석",
        "sentiment": "Layer 5: 센티먼트",
    }

    for layer_key, layer_data in intelligence_data.get("layers", {}).items():
        kr_name = layer_names_kr.get(layer_key, layer_key)
        layer_score = layer_data.get("score", 0)
        layer_signal = layer_data.get("signal", "N/A")
        interp = layer_data.get("interpretation", "")
        confidence = layer_data.get("confidence", 0)

        lines.append(f"#### {kr_name}")
        lines.append(
            f"- **점수**: {layer_score:+.1f} ({layer_signal}), "
            f"신뢰도: {confidence:.0%}"
        )
        lines.append(f"- **판단**: {interp}")

        metrics = layer_data.get("metrics", {})
        if isinstance(metrics, dict):
            for mk, mv in metrics.items():
                if isinstance(mv, dict):
                    parts = [
                        f"{k}={v}"
                        for k, v in mv.items()
                        if not isinstance(v, (dict, list))
                    ]
                    if parts:
                        lines.append(f"  - {mk}: {', '.join(parts[:5])}")
                elif not isinstance(mv, (list, dict)):
                    lines.append(f"  - {mk}: {mv}")
        lines.append("")

    return "\n".join(lines)


def _build_intelligence_summary(intelligence_data: Optional[Dict]) -> str:
    """인텔리전스 데이터의 간략 요약 (Worker B/C 용)."""
    if not intelligence_data:
        return ""

    overall = intelligence_data.get("overall", {})
    score = overall.get("score", 0)
    signal = overall.get("signal", "N/A")

    lines = [
        "\n## 5-Layer Intelligence 요약",
        f"**종합**: {score:+.1f} ({signal}) — {overall.get('interpretation', '')}",
    ]

    layer_names_kr = {
        "macro_regime": "매크로",
        "market_structure": "시장 구조",
        "sector_rotation": "섹터 로테이션",
        "enhanced_technicals": "기술적",
        "sentiment": "센티먼트",
    }

    for layer_key, layer_data in intelligence_data.get("layers", {}).items():
        kr = layer_names_kr.get(layer_key, layer_key)
        ls = layer_data.get("score", 0)
        lsig = layer_data.get("signal", "N/A")
        lines.append(f"- {kr}: {ls:+.1f} ({lsig})")

    return "\n".join(lines)


def _build_daily_changes_block(daily_changes: Optional[Dict]) -> str:
    """전일 대비 변화 정보를 프롬프트 블록으로 구성."""
    if not daily_changes or not daily_changes.get("has_previous"):
        return ""

    lines = [f"\n## 전일 대비 변화 (vs {daily_changes.get('previous_date', 'N/A')})"]

    intel = daily_changes.get("intelligence", {})
    if intel.get("overall_score_change") is not None:
        score_chg = intel["overall_score_change"]
        direction = "▲" if score_chg > 0 else "▼" if score_chg < 0 else "━"
        lines.append(
            f"- 종합 점수 변화: {direction} {score_chg:+.1f}점 "
            f"(전일 시그널: {intel.get('prev_signal', 'N/A')})"
        )

    layer_changes = intel.get("layer_changes", {})
    if layer_changes:
        layer_parts = [f"{name}: {chg:+.1f}" for name, chg in layer_changes.items()]
        lines.append(f"- 레이어별 변화: {', '.join(layer_parts)}")

    stock_changes = daily_changes.get("stocks", {})
    if stock_changes:
        lines.append("- 종목별 전일비:")
        for sym, chg in stock_changes.items():
            parts = []
            if "price_change_pct" in chg:
                parts.append(f"가격 {chg['price_change_pct']:+.2f}%")
            if "rsi_change" in chg:
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

    Returns:
        (랭킹 텍스트 블록, TOP 3 심볼 리스트)
    """
    from trading_bot.stock_ranker import StockRanker

    stocks = market_data.get("stocks", {})
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

    top3_symbols = [r["symbol"] for r in ranked[:3]]

    lines = ["\n## 코드 기반 종목 랭킹 (확정 — 이 순위대로 분석을 작성하세요)"]
    lines.append(
        "아래 TOP 3는 10개 기술 지표, 모멘텀, 레짐, 변화율을 종합하여 "
        "**코드로 결정**된 순위입니다."
    )
    lines.append(
        "각 종목에 대해 기술적 근거, 뉴스, 전망을 분석하세요. "
        "**순위는 변경하지 마세요.**\n"
    )

    for i, item in enumerate(ranked[:8], 1):
        reasons_str = (
            ", ".join(item["reasons"][:3]) if item["reasons"] else "변동 작음"
        )
        if i <= 3:
            prefix = f"**[TOP {i}]**"
        else:
            prefix = f"{i}."
        lines.append(
            f"{prefix} **{item['symbol']}** (점수: {item['total_score']:.0f}) "
            f"— {reasons_str}"
        )

    return "\n".join(lines), top3_symbols


def _load_previous_top3(analysis_dir: str, today: str) -> Optional[list]:
    """이전 Notion 리포트의 TOP 3 종목을 로드합니다."""
    try:
        today_date = datetime.strptime(today, "%Y-%m-%d")
        for days_back in range(1, 4):
            prev_date = (today_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
            marker = Path(analysis_dir) / f"{prev_date}.json.top3"
            if marker.exists():
                return json.loads(marker.read_text())
    except Exception:
        pass
    return None


def _save_top3_marker(json_path: str, top3_symbols: list) -> None:
    """TOP 3 종목을 마커 파일로 저장합니다."""
    marker = Path(json_path).with_suffix(Path(json_path).suffix + ".top3")
    marker.write_text(json.dumps(top3_symbols))


def _build_historical_performance_block() -> str:
    """SignalTracker 에서 최근 30일 시그널 정확도 → 프롬프트 텍스트."""
    if os.getenv("SIGNAL_TRACKING_ENABLED", "true").lower() != "true":
        return ""

    try:
        from trading_bot.signal_tracker import SignalTracker

        tracker = SignalTracker()
        summary = tracker.get_recent_accuracy_summary(lookback_days=30)
        if not summary:
            return ""

        overall = summary.get("overall", {})
        total = overall.get("total_signals", 0)
        if total == 0:
            return ""

        correct = overall.get("correct_count", 0)
        accuracy = overall.get("accuracy_pct")
        avg_bullish = overall.get("avg_return_when_bullish")
        avg_bearish = overall.get("avg_return_when_bearish")

        lines = [
            "\n## 과거 시그널 성과 (최근 30일)",
            (
                f"- 전체 정확도: {accuracy:.1f}% ({correct}/{total}건)"
                if accuracy is not None
                else f"- 전체: {total}건 (정확도 미측정)"
            ),
        ]

        if avg_bullish is not None:
            lines.append(f"- Bullish 시그널 평균 5일 수익: {avg_bullish:+.1f}%")
        if avg_bearish is not None:
            lines.append(f"- Bearish 시그널 평균 5일 수익: {avg_bearish:+.1f}%")

        layers = summary.get("layers", {})
        if layers:
            best_layer = max(
                layers.items(), key=lambda x: x[1].get("accuracy_pct") or 0
            )
            worst_layer = min(
                layers.items(), key=lambda x: x[1].get("accuracy_pct") or 100
            )
            if best_layer[1].get("accuracy_pct") is not None:
                lines.append(
                    f"- 가장 정확한 레이어: {best_layer[0]} "
                    f"({best_layer[1]['accuracy_pct']:.0f}%)"
                )
            if worst_layer[1].get("accuracy_pct") is not None:
                lines.append(
                    f"- 가장 부정확한 레이어: {worst_layer[0]} "
                    f"({worst_layer[1]['accuracy_pct']:.0f}%)"
                )

        lines.append(
            "**이 과거 데이터를 참고하여 오늘의 분석 신뢰도를 판단하세요.**"
        )
        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"RAG 컨텍스트 빌드 실패: {e}")
        return ""


def _calculate_var_95(snapshots: List[Dict]) -> Optional[float]:
    """95% VaR 를 히스토리컬 시뮬레이션으로 계산합니다."""
    if len(snapshots) < 3:
        return None

    values = [s.get("total_value", s.get("equity", 0)) for s in snapshots]
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
    """전략별 PnL 분석을 계산합니다."""
    if not trades:
        return []

    sell_trades = [t for t in trades if t.get("type") == "SELL"]
    if not sell_trades:
        return []

    symbol_pnl: Dict[str, List[float]] = {}
    for t in sell_trades:
        symbol = t.get("symbol", "N/A")
        pnl = t.get("pnl", 0)
        if symbol not in symbol_pnl:
            symbol_pnl[symbol] = []
        symbol_pnl[symbol].append(pnl)

    breakdown = []
    for symbol, pnls in sorted(symbol_pnl.items()):
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        breakdown.append(
            {
                "symbol": symbol,
                "total_pnl": round(total_pnl, 2),
                "trade_count": len(pnls),
                "win_count": len(wins),
                "loss_count": len(losses),
                "avg_pnl": round(total_pnl / len(pnls), 2) if pnls else 0,
                "max_win": round(max(wins), 2) if wins else 0,
                "max_loss": round(min(losses), 2) if losses else 0,
            }
        )

    return breakdown


def _format_trade_log(trades: List[Dict], limit: int = 50) -> List[Dict]:
    """거래 로그를 통합하여 최근 N건을 반환합니다."""
    if not trades:
        return []

    formatted = []
    for t in trades:
        formatted.append(
            {
                "timestamp": t.get("timestamp", "N/A"),
                "symbol": t.get("symbol", "N/A"),
                "type": t.get("type", "N/A"),
                "price": t.get("price", 0),
                "size": t.get("size", 0),
                "pnl": t.get("pnl"),
                "commission": t.get("commission", 0),
            }
        )

    formatted.sort(key=lambda x: x["timestamp"], reverse=True)
    return formatted[:limit]


def precompute_session_metrics(session_reports_dir: str) -> Dict[str, Any]:
    """세션 리포트 디렉토리에서 고급 메트릭을 사전 계산합니다."""
    from trading_bot.market_analysis_prompt import _load_session_reports
    from trading_bot.performance_calculator import PerformanceCalculator

    sessions = _load_session_reports(session_reports_dir)

    if not sessions:
        return {
            "sessions": [],
            "has_sessions": False,
            "var_95": None,
            "strategy_pnl_breakdown": [],
            "trade_log": [],
            "session_details": [],
        }

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

            profit_factor = calc.calculate_profit_factor(trades)
            var_95 = _calculate_var_95(snapshots)

            session_details.append(
                {
                    "session_id": report.get("session_id", "N/A"),
                    "display_name": summary.get(
                        "display_name", summary.get("strategy_name", "N/A")
                    ),
                    "strategy_name": summary.get("strategy_name", "N/A"),
                    "total_return": summary.get("total_return", 0),
                    "sharpe_ratio": summary.get("sharpe_ratio"),
                    "max_drawdown": summary.get("max_drawdown", 0),
                    "win_rate": summary.get("win_rate"),
                    "profit_factor": profit_factor,
                    "var_95": var_95,
                    "total_trades": len(trades),
                    "initial_capital": summary.get("initial_capital", 0),
                    "final_capital": summary.get("final_capital", 0),
                }
            )
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"세션 리포트 상세 로드 실패: {fpath} - {e}")

    overall_var_95 = _calculate_var_95(all_snapshots)
    strategy_pnl = _calculate_strategy_pnl_breakdown(all_trades)
    trade_log = _format_trade_log(all_trades)

    return {
        "sessions": sessions,
        "has_sessions": True,
        "var_95": overall_var_95,
        "strategy_pnl_breakdown": strategy_pnl,
        "trade_log": trade_log,
        "session_details": session_details,
    }


def _extract_forward_look_data(market_data: Dict) -> Dict[str, Any]:
    """전방 전망 섹션에 필요한 데이터를 추출합니다."""
    stocks = market_data.get("stocks", {})
    support_resistance = {}
    rsi_pending_signals = []

    for symbol, data in stocks.items():
        patterns = data.get("patterns", {})
        support_levels = patterns.get("support_levels", [])
        if support_levels:
            support_resistance[symbol] = {
                "support_levels": support_levels,
                "current_price": data.get("price", {}).get("last", 0),
            }

        indicators = data.get("indicators", {})
        rsi_dict = indicators.get("rsi", {})
        rsi_val = rsi_dict.get("value") if isinstance(rsi_dict, dict) else None
        if rsi_val is not None:
            diagnosis = data.get("signal_diagnosis", {})
            optimal = diagnosis.get("optimal_rsi_range", {})
            oversold = optimal.get("oversold", 30)
            overbought = optimal.get("overbought", 70)

            if abs(rsi_val - oversold) <= 3:
                rsi_pending_signals.append(
                    {
                        "symbol": symbol,
                        "rsi": rsi_val,
                        "threshold": oversold,
                        "type": "near_oversold",
                        "distance": round(rsi_val - oversold, 1),
                    }
                )
            elif abs(rsi_val - overbought) <= 3:
                rsi_pending_signals.append(
                    {
                        "symbol": symbol,
                        "rsi": rsi_val,
                        "threshold": overbought,
                        "type": "near_overbought",
                        "distance": round(rsi_val - overbought, 1),
                    }
                )

    return {
        "support_resistance": support_resistance,
        "rsi_pending_signals": rsi_pending_signals,
    }


def assemble_sections(
    worker_a_output: str,
    worker_b_output: str,
    worker_c_output: str,
    today: str,
) -> str:
    """워커 출력들을 최종 페이지 콘텐츠로 조립합니다."""
    from trading_bot.prompts.prompt_engine import PromptEngine

    footer_template = (
        '::: callout {{icon="\U0001f4dd" color="gray_bg"}}\n'
        "\t**분석 생성**: {date}  \\\\|  **데이터 수집**: {date} KST  "
        "\\\\|  **병렬 생성**: Worker A + B + C\n"
        "\t**주의사항**: 본 분석은 자동 수집된 데이터와 기술적 지표를 기반으로 "
        "생성된 참고 자료입니다. 실제 투자 결정은 개인의 판단과 책임 하에 "
        "이루어져야 합니다.\n"
        ":::"
    )
    footer = footer_template.format(date=today)

    content = (
        f"<table_of_contents/>\n---\n"
        f"{worker_a_output.strip()}\n"
        f"{worker_b_output.strip()}\n"
        f"{worker_c_output.strip()}\n"
        f"{footer}"
    )

    content, corrections = PromptEngine.auto_correct_format(content)
    if corrections:
        logger.info(f"포맷 자동 교정 {len(corrections)}건: {corrections}")

    logger.info(f"섹션 조립 완료 (총 길이: {len(content)}자)")
    return content


def validate_assembly(content: str, expected_sections: List[str]) -> bool:
    """조립된 콘텐츠에서 예상되는 섹션 헤더가 순서대로 존재하는지 검증합니다."""
    from trading_bot.prompts.prompt_engine import PromptEngine

    last_pos = -1
    for section in expected_sections:
        pos = content.find(section, last_pos + 1)
        if pos == -1:
            logger.warning(f"섹션 누락: '{section}'")
            return False
        if pos <= last_pos:
            logger.warning(
                f"섹션 순서 오류: '{section}' (pos={pos}, last={last_pos})"
            )
            return False
        last_pos = pos

    format_warnings = PromptEngine.validate_format_rules(content)
    if format_warnings:
        for w in format_warnings:
            logger.warning(f"포맷 경고: {w}")

    logger.info(
        f"섹션 검증 통과: {len(expected_sections)}개 섹션 모두 확인"
        + (f" (포맷 경고 {len(format_warnings)}건)" if format_warnings else "")
    )
    return True


# =========================================================================
# market_analysis_prompt.py 에서 이동한 함수들 (re-export 용)
# =========================================================================

# 이 함수들은 market_analysis_prompt.py 에 원본이 남아있으므로
# 여기서는 import 를 통해 참조만 제공합니다.
# (순환 참조 방지를 위해 런타임 import 사용)


def _build_events_data_block(events_data: dict) -> str:
    """이벤트 캘린더 데이터를 프롬프트에 포함할 텍스트 블록으로 구성합니다."""
    from trading_bot.market_analysis_prompt import (
        _build_events_data_block as _orig,
    )

    return _orig(events_data)


def _build_fundamentals_data_block(fundamentals_data: dict) -> str:
    """펀더멘탈 데이터를 마크다운 테이블로 변환."""
    from trading_bot.market_analysis_prompt import (
        _build_fundamentals_data_block as _orig,
    )

    return _orig(fundamentals_data)


def _load_session_reports(session_reports_dir: str) -> list:
    """세션 리포트 디렉토리에서 세션 요약 리스트를 반환합니다."""
    from trading_bot.market_analysis_prompt import (
        _load_session_reports as _orig,
    )

    return _orig(session_reports_dir)


def get_notion_page_id() -> str:
    """Notion 시장 분석 상위 페이지 ID 를 반환합니다."""
    from trading_bot.market_analysis_prompt import (
        get_notion_page_id as _orig,
    )

    return _orig()


# =========================================================================
# PromptDataBuilder — 워커별 컨텍스트 딕셔너리 생성
# =========================================================================


class PromptDataBuilder:
    """각 워커 프롬프트에 주입할 Jinja2 컨텍스트를 생성합니다."""

    def build_fact_sheet(
        self,
        market_data: Dict,
        today: str,
        *,
        intelligence_data: Optional[Dict] = None,
        fear_greed_data: Optional[Dict] = None,
        daily_changes: Optional[Dict] = None,
        previous_top3: Optional[list] = None,
    ) -> Dict[str, Any]:
        """FactSheetBuilder를 사용하여 팩트 시트를 생성합니다.

        Returns:
            {'market': MarketFact, 'stocks': [StockFact], 'ranking': RankingFact}
        """
        from trading_bot.fact_sheet import FactSheetBuilder
        from trading_bot.stock_ranker import StockRanker

        stocks = market_data.get("stocks", {})
        ranked: list = []
        if stocks:
            ranker = StockRanker()
            ranked = ranker.rank(
                stocks_data=stocks,
                intelligence_data=intelligence_data,
                daily_changes=daily_changes,
                previous_top3=previous_top3,
            )

        builder = FactSheetBuilder()
        return builder.build(
            market_data=market_data,
            intelligence_data=intelligence_data,
            fear_greed_data=fear_greed_data,
            ranked=ranked,
            daily_changes=daily_changes,
            today=today,
        )

    def build_worker_a_context(
        self,
        market_data: Dict,
        today: str,
        *,
        macro_data: Optional[Dict] = None,
        intelligence_data: Optional[Dict] = None,
        events_data: Optional[Dict] = None,
        fundamentals_data: Optional[Dict] = None,
        fear_greed_data: Optional[Dict] = None,
        daily_changes: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Worker A 프롬프트용 컨텍스트를 생성합니다."""
        from trading_bot.market_analysis_prompt import (
            MACRO_SECTION_TEMPLATE_PARALLEL,
            _build_events_data_block as events_fn,
            _build_fundamentals_data_block as fund_fn,
        )

        intel_block = _build_intelligence_block(intelligence_data)
        rag_block = _build_historical_performance_block()

        data_for_worker = {
            "market_summary": market_data.get("market_summary", {}),
            "stocks": market_data.get("stocks", {}),
        }
        json_str = json.dumps(data_for_worker, ensure_ascii=False, indent=2)

        symbols = list(market_data.get("stocks", {}).keys())
        symbols_str = ", ".join(symbols)

        # 매크로 블록 생성
        macro_block = self._build_macro_block(macro_data) if macro_data else ""

        events_block = events_fn(events_data) if events_data else ""
        fundamentals_block = fund_fn(fundamentals_data) if fundamentals_data else ""

        fg_block = ""
        if fear_greed_data:
            current = fear_greed_data.get("current", {})
            if isinstance(current, dict) and current.get("value") is not None:
                fg_block = (
                    f"\n## Fear & Greed Index (CNN)\n"
                    f"- 현재 값: {current.get('value')} "
                    f"({current.get('classification', 'N/A')})\n"
                    f"- 이전 종가: "
                    f"{fear_greed_data.get('previous_close', {}).get('value', 'N/A')} "
                    f"({fear_greed_data.get('previous_close', {}).get('classification', 'N/A')})\n"
                    f"- 1주 전: "
                    f"{fear_greed_data.get('one_week_ago', {}).get('value', 'N/A')} "
                    f"({fear_greed_data.get('one_week_ago', {}).get('classification', 'N/A')})\n"
                    f"- 1개월 전: "
                    f"{fear_greed_data.get('one_month_ago', {}).get('value', 'N/A')} "
                    f"({fear_greed_data.get('one_month_ago', {}).get('classification', 'N/A')})\n\n"
                    f"위 Fear & Greed 데이터를 공포탐욕 지수 행에 정확히 반영하세요.\n"
                )

        daily_changes_block = _build_daily_changes_block(daily_changes)

        macro_section_template = ""
        if macro_data:
            macro_section_template = MACRO_SECTION_TEMPLATE_PARALLEL

        if macro_data:
            section_spec = "**섹션 0, 섹션 1, 섹션 2를**"
            section_note = "섹션 0(매크로 시장 환경), 1, 2만 출력합니다"
        else:
            section_spec = "**섹션 1과 섹션 2만**"
            section_note = "섹션 1과 2만 출력합니다"

        # Fact sheet block
        fact_sheet_block = ""
        try:
            fact_sheet = self.build_fact_sheet(
                market_data, today,
                intelligence_data=intelligence_data,
                fear_greed_data=fear_greed_data,
                daily_changes=daily_changes,
            )
            from trading_bot.fact_sheet import FactSheetBuilder
            fact_sheet_block = FactSheetBuilder().to_prompt_block(fact_sheet)
        except Exception as e:
            logger.warning(f"Worker A 팩트시트 빌드 실패 (무시): {e}")
            fact_sheet_block = "(⚠️ 팩트시트 생성 실패 — 데이터 기반으로 직접 분석하세요)"

        return {
            "today": today,
            "symbols": symbols,
            "symbols_str": symbols_str,
            "symbols_count": len(symbols),
            "json_str": json_str,
            "intel_block": intel_block,
            "rag_block": rag_block,
            "macro_block": macro_block,
            "events_block": events_block,
            "fundamentals_block": fundamentals_block,
            "fg_block": fg_block,
            "daily_changes_block": daily_changes_block,
            "macro_section_template": macro_section_template,
            "section_spec": section_spec,
            "section_note": section_note,
            "fact_sheet_block": fact_sheet_block,
        }

    def build_worker_b_context(
        self,
        market_data: Dict,
        news_data: Dict,
        fear_greed_data: Dict,
        today: str,
        *,
        intelligence_data: Optional[Dict] = None,
        worker_a_context: Optional[str] = None,
        daily_changes: Optional[Dict] = None,
        previous_top3: Optional[list] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Worker B 프롬프트용 컨텍스트를 생성합니다.

        Returns:
            (context_dict, top3_symbols) 튜플
        """
        intel_summary = _build_intelligence_summary(intelligence_data)

        top3_ranking, top3_symbols = _compute_top3_candidates(
            market_data, daily_changes, intelligence_data, previous_top3
        )

        prev_top3_block = ""
        if previous_top3:
            prev_top3_block = (
                f"\n## 이전 리포트 TOP 3\n"
                f"어제 TOP 3: {', '.join(previous_top3)}\n"
                f"위 랭킹에는 이미 중복 감점이 적용되었습니다. "
                f"재선정된 종목이 있다면 새로운 촉매를 반드시 명시하세요.\n"
            )

        rag_block = _build_historical_performance_block()

        reflection_block = ""
        if worker_a_context:
            reflection_block = (
                f"\n## Worker-A 분석 결과 (교차 검증용)\n"
                f"아래 분석과 일치하는지 확인하고, 불일치 시 이유를 명시하세요.\n"
                f"{worker_a_context}\n"
            )

        # 종목 데이터 경량화
        stocks_compact: Dict[str, Any] = {}
        for sym, sdata in market_data.get("stocks", {}).items():
            price_info = sdata.get("price", {})
            indicators = sdata.get("indicators", {})
            regime = sdata.get("regime", {})
            patterns = sdata.get("patterns", {})
            stocks_compact[sym] = {
                "price": {
                    "last": price_info.get("last"),
                    "change_1d": price_info.get("change_1d"),
                    "change_5d": price_info.get("change_5d"),
                    "change_20d": price_info.get("change_20d"),
                },
                "indicators": {
                    "rsi": indicators.get("rsi", {}),
                    "macd": {"signal": indicators.get("macd", {}).get("signal")},
                    "bollinger": {
                        "signal": indicators.get("bollinger", {}).get("signal")
                    },
                    "adx": indicators.get("adx", {}).get("value"),
                },
                "regime": {
                    "state": regime.get("state"),
                    "confidence": regime.get("confidence"),
                },
                "support_levels": patterns.get("support_levels", [])[:3],
            }
        stocks_json = json.dumps(stocks_compact, ensure_ascii=False, indent=2)

        # 뉴스 블록
        news_block = ""
        if news_data:
            news_lines = []
            market_news = news_data.get("market_news", [])
            if market_news:
                news_lines.append("### 시장 전체 뉴스")
                for item in market_news:
                    news_lines.append(
                        f"- {item['title']} ({item.get('source', 'N/A')})"
                    )

            stock_news = news_data.get("stock_news", {})
            if stock_news:
                news_lines.append("\n### 종목별 뉴스")
                for symbol, items in stock_news.items():
                    news_lines.append(f"\n**{symbol}**:")
                    for item in items[:3]:
                        news_lines.append(
                            f"- {item['title']} ({item.get('source', 'N/A')})"
                        )

            news_block = "\n## 수집된 뉴스 데이터\n" + "\n".join(news_lines)

        # Fear & Greed 블록
        fg_block = ""
        if fear_greed_data:
            current = fear_greed_data.get("current", {})
            fg_lines = []
            fg_lines.append("### 현재 Fear & Greed Index")
            fg_lines.append(f"- **값**: {current.get('value', 'N/A')}")
            fg_lines.append(f"- **분류**: {current.get('classification', 'N/A')}")
            fg_lines.append(f"- **시각**: {current.get('timestamp', 'N/A')}")

            history = fear_greed_data.get("history", [])
            if history:
                fg_lines.append(f"\n### 최근 {len(history)}일 히스토리")
                for item in history[:7]:
                    fg_lines.append(
                        f"- {item['date']}: {item['value']} ({item['classification']})"
                    )
                if len(history) > 7:
                    fg_lines.append(f"- ... 외 {len(history) - 7}일")

            chart_path = fear_greed_data.get("chart_path")
            if chart_path:
                fg_lines.append("\n### 차트")
                fg_lines.append(f"- 차트 파일 경로: `{chart_path}`")
                fg_lines.append(
                    "- Read 도구로 이 차트 이미지를 읽어서 시각적 분석에 반영하세요."
                )

            fg_block = (
                "\n## 공포/탐욕 지수 (Fear & Greed Index)\n" + "\n".join(fg_lines)
            )

        # Fact sheet block
        fact_sheet_block = ""
        try:
            fact_sheet = self.build_fact_sheet(
                market_data, today,
                intelligence_data=intelligence_data,
                fear_greed_data=fear_greed_data,
                daily_changes=daily_changes,
                previous_top3=previous_top3,
            )
            from trading_bot.fact_sheet import FactSheetBuilder
            fact_sheet_block = FactSheetBuilder().to_prompt_block(fact_sheet)
        except Exception as e:
            logger.warning(f"Worker B 팩트시트 빌드 실패 (무시): {e}")
            fact_sheet_block = "(⚠️ 팩트시트 생성 실패 — 데이터 기반으로 직접 분석하세요)"

        ctx = {
            "today": today,
            "intel_summary": intel_summary,
            "top3_ranking": top3_ranking,
            "prev_top3_block": prev_top3_block,
            "rag_block": rag_block,
            "reflection_block": reflection_block,
            "stocks_json": stocks_json,
            "news_block": news_block,
            "fg_block": fg_block,
            "fact_sheet_block": fact_sheet_block,
        }

        return ctx, top3_symbols

    def build_worker_c_context(
        self,
        market_data: Dict,
        session_metrics: Dict,
        today: str,
        has_sessions: bool,
        *,
        intelligence_data: Optional[Dict] = None,
        daily_changes: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Worker C 프롬프트용 컨텍스트를 생성합니다."""
        intel_summary = _build_intelligence_summary(intelligence_data)

        stocks_json = json.dumps(
            market_data.get("stocks", {}), ensure_ascii=False, indent=2
        )

        metrics_json = ""
        if has_sessions:
            metrics_for_prompt = {
                "session_details": session_metrics.get("session_details", []),
                "var_95": session_metrics.get("var_95"),
                "strategy_pnl_breakdown": session_metrics.get(
                    "strategy_pnl_breakdown", []
                ),
                "trade_log": session_metrics.get("trade_log", [])[:20],
            }
            metrics_json = json.dumps(
                metrics_for_prompt, ensure_ascii=False, indent=2
            )

        daily_changes_block = _build_daily_changes_block(daily_changes)

        forward_data = _extract_forward_look_data(market_data)
        forward_json = json.dumps(forward_data, ensure_ascii=False, indent=2)

        # Fact sheet block
        fact_sheet_block = ""
        try:
            fact_sheet = self.build_fact_sheet(
                market_data, today,
                intelligence_data=intelligence_data,
                daily_changes=daily_changes,
            )
            from trading_bot.fact_sheet import FactSheetBuilder
            fact_sheet_block = FactSheetBuilder().to_prompt_block(fact_sheet)
        except Exception as e:
            logger.warning(f"Worker C 팩트시트 빌드 실패 (무시): {e}")
            fact_sheet_block = "(⚠️ 팩트시트 생성 실패 — 데이터 기반으로 직접 분석하세요)"

        return {
            "today": today,
            "has_sessions": has_sessions,
            "intel_summary": intel_summary,
            "daily_changes_block": daily_changes_block,
            "stocks_json": stocks_json,
            "metrics_json": metrics_json,
            "forward_json": forward_json,
            "fact_sheet_block": fact_sheet_block,
        }

    def build_notion_writer_context(
        self,
        assembled_content: str,
        today: str,
        parent_page_id: str,
    ) -> Dict[str, Any]:
        """Notion Writer 프롬프트용 컨텍스트를 생성합니다."""
        return {
            "assembled_content": assembled_content,
            "today": today,
            "parent_page_id": parent_page_id,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_macro_block(macro_data: Optional[Dict]) -> str:
        """매크로 시장 환경 데이터 블록을 생성합니다."""
        if not macro_data:
            return ""

        ml = []

        # 지수
        ml.append("### 주요 지수 현황")
        for sym, info in macro_data.get("indices", {}).items():
            chg_1d = info.get("chg_1d", 0)
            chg_5d = info.get("chg_5d", 0)
            chg_20d = info.get("chg_20d", 0)
            s1 = "+" if chg_1d and chg_1d > 0 else ""
            s5 = "+" if chg_5d > 0 else ""
            s20 = "+" if chg_20d and chg_20d > 0 else ""
            ml.append(
                f"- **{sym}**: ${info.get('last', 'N/A')} "
                f"(1일 {s1}{chg_1d}%, 5일 {s5}{chg_5d}%, "
                f"20일 {s20}{chg_20d}%, RSI {info.get('rsi', 'N/A')})"
            )

        # 섹터
        ml.append("\n### 섹터 상대강도 (5일/20일 수익률)")
        sectors = sorted(
            macro_data.get("sectors", {}).items(),
            key=lambda x: x[1].get("rank_5d", 99),
        )
        for sym, info in sectors:
            chg_5d = info.get("chg_5d", 0)
            chg_20d = info.get("chg_20d", 0)
            s5 = "+" if chg_5d > 0 else ""
            s20 = "+" if chg_20d and chg_20d > 0 else ""
            r20 = info.get("rank_20d", "?")
            ml.append(
                f"- #{info.get('rank_5d', '?')} "
                f"**{info.get('name', sym)}**({sym}): "
                f"5일 {s5}{chg_5d}%, 20일 {s20}{chg_20d}% "
                f"(20일순위 #{r20}, RSI {info.get('rsi', 'N/A')})"
            )

        # 로테이션
        rot = macro_data.get("rotation", {})
        if rot:
            ml.append(f"\n### 섹터 로테이션: {rot.get('signal', 'N/A')}")
            ml.append(f"- 공격적 섹터 평균: {rot.get('offensive_avg_5d', 'N/A')}%")
            ml.append(f"- 방어적 섹터 평균: {rot.get('defensive_avg_5d', 'N/A')}%")

        # 시장 폭
        breadth = macro_data.get("breadth", {})
        if breadth:
            ml.append(
                f"\n### 시장 폭: {breadth.get('interpretation', 'N/A')}"
            )
            ml.append(
                f"- SPY vs IWM 5일 괴리: "
                f"{breadth.get('spy_vs_iwm_5d', 'N/A')}%p"
            )
            ml.append(
                f"- 상승 섹터: {breadth.get('sectors_positive_5d', 0)}개 "
                f"/ 하락: {breadth.get('sectors_negative_5d', 0)}개"
            )

        # 리스크 환경
        risk = macro_data.get("risk_environment", {})
        if risk:
            ml.append(
                f"\n### 리스크 환경: {risk.get('assessment', 'N/A')}"
            )
            ml.append(f"- TLT(국채): {risk.get('tlt_chg_5d', 'N/A')}%")
            ml.append(f"- GLD(금): {risk.get('gld_chg_5d', 'N/A')}%")
            ml.append(f"- HYG(하이일드): {risk.get('hyg_chg_5d', 'N/A')}%")

        # 종합
        overall = macro_data.get("overall", "")
        if overall:
            ml.append(f"\n### 종합: {overall}")

        return "\n## 매크로 시장 환경 데이터\n" + "\n".join(ml)
