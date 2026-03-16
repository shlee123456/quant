"""Fact sheet builder for LLM prompt anchoring.

Computes immutable facts from code-computed data and structures them
for injection into LLM prompts. LLM's role becomes "interpret why",
not "compute what".
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class StockFact:
    """단일 종목의 확정 사실."""

    symbol: str
    current_price: float
    change_1d: float
    change_5d: float
    change_20d: float
    rsi_value: float
    rsi_zone: str  # 'oversold' | 'neutral' | 'overbought'
    macd_signal: str  # 'bullish' | 'bearish' | 'neutral'
    regime: str  # 'BULLISH' | 'BEARISH' | 'SIDEWAYS' | 'VOLATILE'
    regime_confidence: float
    composite_score: Optional[float] = None  # Layer 4 score
    direction: str = "long"  # 'long' | 'short'
    short_eligible: bool = False
    short_signal_count: int = 0


@dataclass
class MarketFact:
    """시장 전체의 확정 사실."""

    analysis_date: str
    total_symbols: int
    symbols_list: List[str]
    intelligence_score: float
    intelligence_signal: str  # 'bullish' | 'bearish' | 'neutral'
    layer_scores: Dict[str, float]
    fear_greed_value: Optional[int] = None
    fear_greed_classification: Optional[str] = None
    regime_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class RankingFact:
    """종목 랭킹 확정 사실."""

    ranked_symbols: List[str]
    scores: Dict[str, float]
    reasons: Dict[str, List[str]]
    directions: Dict[str, str] = field(default_factory=dict)
    short_signal_counts: Dict[str, int] = field(default_factory=dict)


class FactSheetBuilder:
    """Builds structured fact sheets from market data and intelligence results."""

    def build(
        self,
        market_data: Dict[str, Any],
        intelligence_data: Optional[Dict[str, Any]],
        fear_greed_data: Optional[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        daily_changes: Optional[Dict[str, Any]],
        today: str,
    ) -> Dict[str, Any]:
        """Build complete fact sheet.

        Args:
            market_data: 시장 분석 JSON 데이터 (stocks 포함)
            intelligence_data: 5-Layer Intelligence 분석 결과
            fear_greed_data: Fear & Greed 지수 데이터
            ranked: StockRanker.rank() 반환값
            daily_changes: 전일 대비 변화 데이터
            today: 분석 날짜 (YYYY-MM-DD)

        Returns:
            {'market': MarketFact, 'stocks': [StockFact], 'ranking': RankingFact}
        """
        market_fact = self._build_market_fact(
            intelligence_data, fear_greed_data, market_data, today
        )
        stock_facts = self._build_stock_facts(market_data, intelligence_data, ranked)
        ranking_fact = self._build_ranking_fact(ranked)

        return {
            "market": market_fact,
            "stocks": stock_facts,
            "ranking": ranking_fact,
        }

    def _build_market_fact(
        self,
        intelligence_data: Optional[Dict[str, Any]],
        fear_greed_data: Optional[Dict[str, Any]],
        market_data: Dict[str, Any],
        today: str,
    ) -> MarketFact:
        """인텔리전스/FG/시장 데이터에서 MarketFact를 생성합니다."""
        stocks = market_data.get("stocks", {})
        symbols_list = list(stocks.keys())

        # Intelligence overall
        overall = (intelligence_data or {}).get("overall", {})
        intelligence_score = overall.get("score", 0.0)
        intelligence_signal = overall.get("signal", "neutral")

        # Layer scores
        layer_scores: Dict[str, float] = {}
        for layer_key, layer_data in (intelligence_data or {}).get("layers", {}).items():
            layer_scores[layer_key] = layer_data.get("score", 0.0)

        # Fear & Greed
        fg_value: Optional[int] = None
        fg_classification: Optional[str] = None
        if fear_greed_data:
            current = fear_greed_data.get("current", {})
            if isinstance(current, dict) and current.get("value") is not None:
                try:
                    fg_value = int(current["value"])
                except (TypeError, ValueError):
                    pass
                fg_classification = current.get("classification")
            elif "value" in fear_greed_data:
                try:
                    fg_value = int(fear_greed_data["value"])
                except (TypeError, ValueError):
                    pass
                fg_classification = fear_greed_data.get("value_classification")

        # Regime counts
        regime_counts: Dict[str, int] = {}
        for _sym, sdata in stocks.items():
            state = sdata.get("regime", {}).get("state", "SIDEWAYS")
            regime_counts[state] = regime_counts.get(state, 0) + 1

        return MarketFact(
            analysis_date=today,
            total_symbols=len(symbols_list),
            symbols_list=symbols_list,
            intelligence_score=intelligence_score,
            intelligence_signal=intelligence_signal,
            layer_scores=layer_scores,
            fear_greed_value=fg_value,
            fear_greed_classification=fg_classification,
            regime_counts=regime_counts,
        )

    def _build_stock_facts(
        self,
        market_data: Dict[str, Any],
        intelligence_data: Optional[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
    ) -> List[StockFact]:
        """종목별 StockFact 리스트를 생성합니다."""
        stocks = market_data.get("stocks", {})
        per_stock = (
            (intelligence_data or {})
            .get("layers", {})
            .get("enhanced_technicals", {})
            .get("details", {})
            .get("per_stock", {})
        )

        # ranked에서 direction/short 정보를 심볼 키로 매핑
        ranked_map: Dict[str, Dict[str, Any]] = {}
        for item in ranked:
            ranked_map[item["symbol"]] = item

        facts: List[StockFact] = []
        for symbol, sdata in stocks.items():
            price = sdata.get("price", {})
            indicators = sdata.get("indicators", {})
            regime = sdata.get("regime", {})

            current_price = price.get("last", 0.0) or 0.0
            change_1d = price.get("change_1d", 0.0) or 0.0
            change_5d = price.get("change_5d", 0.0) or 0.0
            change_20d = price.get("change_20d", 0.0) or 0.0

            rsi_value = indicators.get("rsi", {}).get("value", 50.0) or 50.0
            rsi_zone = self._classify_rsi_zone(rsi_value)

            macd_data = indicators.get("macd", {})
            macd_signal = self._classify_macd_signal(macd_data)

            regime_state = regime.get("state", "SIDEWAYS")
            regime_confidence = regime.get("confidence", 0.0) or 0.0

            composite_score = per_stock.get(symbol, {}).get("composite_score")

            ranked_info = ranked_map.get(symbol, {})
            direction = ranked_info.get("direction", "long")
            short_eligible = ranked_info.get("short_eligible", False)
            short_signal_count = ranked_info.get("short_signal_count", 0)

            facts.append(
                StockFact(
                    symbol=symbol,
                    current_price=current_price,
                    change_1d=change_1d,
                    change_5d=change_5d,
                    change_20d=change_20d,
                    rsi_value=rsi_value,
                    rsi_zone=rsi_zone,
                    macd_signal=macd_signal,
                    regime=regime_state,
                    regime_confidence=regime_confidence,
                    composite_score=composite_score,
                    direction=direction,
                    short_eligible=short_eligible,
                    short_signal_count=short_signal_count,
                )
            )

        return facts

    def _build_ranking_fact(self, ranked: List[Dict[str, Any]]) -> RankingFact:
        """ranked 리스트에서 RankingFact를 생성합니다."""
        ranked_symbols: List[str] = []
        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}
        directions: Dict[str, str] = {}
        short_signal_counts: Dict[str, int] = {
            r["symbol"]: r.get("short_signal_count", 0) for r in ranked
        }

        for item in ranked:
            sym = item["symbol"]
            ranked_symbols.append(sym)
            scores[sym] = item.get("total_score", 0.0)
            reasons[sym] = item.get("reasons", [])
            directions[sym] = item.get("direction", "long")

        return RankingFact(
            ranked_symbols=ranked_symbols,
            scores=scores,
            reasons=reasons,
            directions=directions,
            short_signal_counts=short_signal_counts,
        )

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------

    def to_prompt_block(self, fact_sheet: Dict[str, Any]) -> str:
        """Render fact sheet as markdown for prompt injection.

        Returns:
            확정 사실 마크다운 블록
        """
        lines: List[str] = []
        lines.append("")
        lines.append("## 확정 사실 (IMMUTABLE FACTS — 변경 금지)")
        lines.append(
            "아래는 코드에서 계산된 사실입니다. 이 수치를 그대로 사용하세요."
        )
        lines.append("")

        # Market section
        market: MarketFact = fact_sheet["market"]
        lines.append("### 종합 점수")
        lines.append(
            f"- Intelligence 점수: {market.intelligence_score:+.1f} "
            f"({market.intelligence_signal})"
        )
        if market.layer_scores:
            layer_parts = [
                f"{k}: {v:+.1f}" for k, v in market.layer_scores.items()
            ]
            lines.append(f"- 레이어별: {', '.join(layer_parts)}")
        if market.fear_greed_value is not None:
            lines.append(
                f"- Fear & Greed: {market.fear_greed_value} "
                f"({market.fear_greed_classification or 'N/A'})"
            )
        else:
            lines.append("- Fear & Greed: 데이터 없음")
        if market.regime_counts:
            regime_parts = [
                f"{k}: {v}" for k, v in market.regime_counts.items()
            ]
            lines.append(f"- 레짐 분포: {', '.join(regime_parts)}")
        lines.append("")

        # Stocks table
        stocks: List[StockFact] = fact_sheet["stocks"]
        if stocks:
            lines.append("### 종목별 핵심 수치")
            lines.append(
                "| 종목 | 가격 | 1D% | RSI | RSI구간 | MACD | 레짐 | 복합점수 | 방향 | 숏적격 |"
            )
            lines.append(
                "|------|------|-----|-----|---------|------|------|----------|------|--------|"
            )
            for sf in stocks:
                composite_str = (
                    f"{sf.composite_score:.1f}" if sf.composite_score is not None else "N/A"
                )
                short_mark = "O" if sf.short_eligible else "X"
                lines.append(
                    f"| {sf.symbol} | ${sf.current_price:,.2f} | "
                    f"{sf.change_1d:+.2f}% | {sf.rsi_value:.1f} | "
                    f"{sf.rsi_zone} | {sf.macd_signal} | "
                    f"{sf.regime} | {composite_str} | "
                    f"{sf.direction} | {short_mark} |"
                )
            lines.append("")

        # Ranking section
        ranking: RankingFact = fact_sheet["ranking"]
        top3 = ranking.ranked_symbols[:3]
        if top3:
            lines.append("### TOP 3 확정 순위 (변경 금지)")
            for i, sym in enumerate(top3, 1):
                score = ranking.scores.get(sym, 0)
                reason_list = ranking.reasons.get(sym, [])
                reasons_str = ", ".join(reason_list[:3]) if reason_list else "변동 작음"
                direction = ranking.directions.get(sym, "long")
                ssc = ranking.short_signal_counts.get(sym, 0)
                tag = f"\u26a0\ufe0f 약세시그널 {ssc}/5" if ssc >= 3 else "\U0001f4c8"
                lines.append(
                    f"{i}. **{sym}** {tag} (점수: {score:.0f}) — {reasons_str}"
                )
            lines.append("")

        # Bidirectional scenario analysis targets
        signal_concentrated = [s for s in stocks if s.short_signal_count >= 3]
        if signal_concentrated:
            lines.append("### \u26a0\ufe0f 약세 시그널 집중 종목 (양방향 시나리오 분석 필요)")
            for s in signal_concentrated:
                lines.append(
                    f"- **{s.symbol}** ({s.short_signal_count}/5 시그널: "
                    f"RSI {s.rsi_value:.1f}, {s.regime})"
                )
            lines.append("")
            lines.append("위 종목은 약세 시그널이 집중되어 있습니다.")
            lines.append("**하락 시나리오**와 **반등 시나리오**를 모두 분석하고,")
            lines.append("각 시나리오의 트리거 조건(가격, 이벤트)을 명시하세요.")
            lines.append("")

        # Footer warnings
        lines.append(
            "숏 적격=X인 종목을 숏 추천하지 마세요."
        )
        lines.append(
            "당신의 역할: 위 사실을 기반으로 **왜 이런 수치가 나왔는지** 해석하고 분석하세요."
        )

        return "\n".join(lines)

    def to_json(self, fact_sheet: Dict[str, Any]) -> str:
        """Serialize fact sheet to JSON for post-validation."""
        serializable: Dict[str, Any] = {
            "market": asdict(fact_sheet["market"]),
            "stocks": [asdict(sf) for sf in fact_sheet["stocks"]],
            "ranking": asdict(fact_sheet["ranking"]),
        }
        return json.dumps(serializable, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_rsi_zone(rsi_value: float) -> str:
        """RSI 값을 구간으로 분류합니다."""
        if rsi_value < 30:
            return "oversold"
        elif rsi_value > 70:
            return "overbought"
        return "neutral"

    @staticmethod
    def _classify_macd_signal(macd_data: Dict[str, Any]) -> str:
        """MACD 데이터에서 시그널 방향을 분류합니다."""
        signal = macd_data.get("signal")
        if isinstance(signal, str):
            sig_lower = signal.lower()
            if "bullish" in sig_lower or "buy" in sig_lower:
                return "bullish"
            if "bearish" in sig_lower or "sell" in sig_lower:
                return "bearish"

        histogram = macd_data.get("histogram", 0) or 0
        if histogram > 0:
            return "bullish"
        elif histogram < 0:
            return "bearish"
        return "neutral"
