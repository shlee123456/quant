"""Tests for FactSheetBuilder and OutputValidator."""

import json
import pytest

from trading_bot.fact_sheet import (
    FactSheetBuilder,
    MarketFact,
    RankingFact,
    StockFact,
)
from trading_bot.output_validator import OutputValidator, ValidationResult


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────


def _make_market_data(symbols=None):
    """테스트용 시장 데이터를 생성합니다."""
    symbols = symbols or ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    stocks = {}
    rsi_values = [25.0, 55.0, 72.0, 40.0, 80.0]
    prices = [150.0, 300.0, 140.0, 180.0, 250.0]
    changes_1d = [-2.5, 1.2, -0.3, 3.1, -4.0]
    regimes = ["BEARISH", "SIDEWAYS", "BULLISH", "BULLISH", "VOLATILE"]
    for i, sym in enumerate(symbols):
        stocks[sym] = {
            "price": {
                "last": prices[i],
                "change_1d": changes_1d[i],
                "change_5d": changes_1d[i] * 2,
                "change_20d": changes_1d[i] * 3,
            },
            "indicators": {
                "rsi": {"value": rsi_values[i]},
                "macd": {
                    "signal": "Bullish" if i % 2 == 0 else "Bearish",
                    "histogram": 1.5 if i % 2 == 0 else -0.8,
                    "cross_recent": False,
                },
                "bollinger": {"pct_b": 0.5, "signal": "neutral"},
                "stochastic": {"k": 50.0},
                "adx": {"value": 30.0},
            },
            "regime": {
                "state": regimes[i],
                "confidence": 0.75,
            },
        }
    return {"stocks": stocks}


def _make_intelligence_data():
    """테스트용 intelligence 데이터를 생성합니다."""
    return {
        "overall": {
            "score": 15.3,
            "signal": "bullish",
            "interpretation": "종합 긍정적",
        },
        "layers": {
            "macro_regime": {"score": 10.0, "signal": "neutral", "confidence": 0.6},
            "market_structure": {"score": 20.0, "signal": "bullish", "confidence": 0.7},
            "sector_rotation": {"score": 5.0, "signal": "neutral", "confidence": 0.5},
            "enhanced_technicals": {
                "score": 25.0,
                "signal": "bullish",
                "confidence": 0.8,
                "details": {
                    "per_stock": {
                        "AAPL": {"composite_score": 72.5},
                        "MSFT": {"composite_score": 45.0},
                        "GOOGL": {"composite_score": 60.0},
                    }
                },
            },
            "sentiment": {"score": -5.0, "signal": "neutral", "confidence": 0.4},
        },
    }


def _make_fear_greed_data():
    """테스트용 Fear & Greed 데이터를 생성합니다."""
    return {
        "current": {
            "value": 35,
            "classification": "Fear",
            "timestamp": "2026-03-16T10:00:00",
        },
    }


def _make_ranked():
    """테스트용 ranked 리스트를 생성합니다."""
    return [
        {
            "symbol": "AAPL",
            "total_score": 85.0,
            "reasons": ["RSI 25.0 과매도", "1일 -2.5% 변동"],
            "direction": "long",
            "short_eligible": False,
            "short_signal_count": 0,
            "rank": 1,
        },
        {
            "symbol": "TSLA",
            "total_score": 78.0,
            "reasons": ["RSI 80.0 과매수", "1일 -4.0% 급변"],
            "direction": "short",
            "short_eligible": True,
            "short_signal_count": 3,
            "rank": 2,
        },
        {
            "symbol": "AMZN",
            "total_score": 70.0,
            "reasons": ["1일 +3.1% 급변", "레짐 BULLISH"],
            "direction": "long",
            "short_eligible": False,
            "short_signal_count": 0,
            "rank": 3,
        },
        {
            "symbol": "GOOGL",
            "total_score": 55.0,
            "reasons": ["RSI 72.0 과매수"],
            "direction": "long",
            "short_eligible": False,
            "short_signal_count": 1,
            "rank": 4,
        },
        {
            "symbol": "MSFT",
            "total_score": 40.0,
            "reasons": ["변동 작음"],
            "direction": "long",
            "short_eligible": False,
            "short_signal_count": 0,
            "rank": 5,
        },
    ]


# ──────────────────────────────────────────────────────────────
# FactSheetBuilder tests
# ──────────────────────────────────────────────────────────────


class TestFactSheetBuilder:
    def test_fact_sheet_builder_basic(self):
        """기본 팩트시트 빌드 및 구조 검증."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        intelligence_data = _make_intelligence_data()
        fear_greed_data = _make_fear_greed_data()
        ranked = _make_ranked()

        result = builder.build(
            market_data=market_data,
            intelligence_data=intelligence_data,
            fear_greed_data=fear_greed_data,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        assert "market" in result
        assert "stocks" in result
        assert "ranking" in result

        # Market fact
        market = result["market"]
        assert isinstance(market, MarketFact)
        assert market.analysis_date == "2026-03-16"
        assert market.total_symbols == 5
        assert market.intelligence_score == 15.3
        assert market.intelligence_signal == "bullish"
        assert market.fear_greed_value == 35
        assert market.fear_greed_classification == "Fear"
        assert len(market.layer_scores) == 5

        # Stock facts
        stocks = result["stocks"]
        assert len(stocks) == 5
        assert all(isinstance(sf, StockFact) for sf in stocks)

        # Ranking fact
        ranking = result["ranking"]
        assert isinstance(ranking, RankingFact)
        assert ranking.ranked_symbols[:3] == ["AAPL", "TSLA", "AMZN"]

    def test_fact_sheet_builder_missing_intelligence(self):
        """intelligence_data=None일 때 정상 동작."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        result = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        market = result["market"]
        assert market.intelligence_score == 0.0
        assert market.intelligence_signal == "neutral"
        assert market.layer_scores == {}

    def test_fact_sheet_builder_missing_fear_greed(self):
        """fear_greed_data=None일 때 정상 동작."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        result = builder.build(
            market_data=market_data,
            intelligence_data=_make_intelligence_data(),
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        market = result["market"]
        assert market.fear_greed_value is None
        assert market.fear_greed_classification is None

    def test_stock_fact_rsi_zones(self):
        """RSI 구간 분류: <30=oversold, 30-70=neutral, >70=overbought."""
        builder = FactSheetBuilder()

        assert builder._classify_rsi_zone(25.0) == "oversold"
        assert builder._classify_rsi_zone(29.9) == "oversold"
        assert builder._classify_rsi_zone(30.0) == "neutral"
        assert builder._classify_rsi_zone(50.0) == "neutral"
        assert builder._classify_rsi_zone(70.0) == "neutral"
        assert builder._classify_rsi_zone(70.1) == "overbought"
        assert builder._classify_rsi_zone(85.0) == "overbought"

    def test_stock_fact_rsi_zones_in_build(self):
        """빌드 결과에서 RSI 구간이 올바르게 분류되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        result = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        stock_map = {sf.symbol: sf for sf in result["stocks"]}
        assert stock_map["AAPL"].rsi_zone == "oversold"  # RSI 25
        assert stock_map["MSFT"].rsi_zone == "neutral"  # RSI 55
        assert stock_map["GOOGL"].rsi_zone == "overbought"  # RSI 72
        assert stock_map["AMZN"].rsi_zone == "neutral"  # RSI 40
        assert stock_map["TSLA"].rsi_zone == "overbought"  # RSI 80

    def test_to_prompt_block_contains_facts(self):
        """프롬프트 블록에 모든 종목 심볼과 점수가 포함되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=_make_intelligence_data(),
            fear_greed_data=_make_fear_greed_data(),
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        block = builder.to_prompt_block(fact_sheet)

        # All symbols should appear
        for sym in ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]:
            assert sym in block, f"{sym} not found in prompt block"

        # Intelligence score
        assert "+15.3" in block

        # Fear & Greed
        assert "35" in block
        assert "Fear" in block

        # TOP 3
        assert "AAPL" in block
        assert "TSLA" in block
        assert "AMZN" in block

    def test_to_prompt_block_has_immutable_header(self):
        """프롬프트 블록에 '확정 사실' 헤더가 포함되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        block = builder.to_prompt_block(fact_sheet)
        assert "확정 사실" in block
        assert "IMMUTABLE FACTS" in block
        assert "변경 금지" in block

    def test_to_json_roundtrip(self):
        """JSON 직렬화/역직렬화 라운드트립."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=_make_intelligence_data(),
            fear_greed_data=_make_fear_greed_data(),
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        json_str = builder.to_json(fact_sheet)
        parsed = json.loads(json_str)

        assert "market" in parsed
        assert "stocks" in parsed
        assert "ranking" in parsed
        assert parsed["market"]["analysis_date"] == "2026-03-16"
        assert len(parsed["stocks"]) == 5
        assert parsed["ranking"]["ranked_symbols"][:3] == ["AAPL", "TSLA", "AMZN"]

    def test_composite_score_from_intelligence(self):
        """Layer 4 per_stock composite_score가 올바르게 추출되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        intelligence_data = _make_intelligence_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=intelligence_data,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        stock_map = {sf.symbol: sf for sf in fact_sheet["stocks"]}
        assert stock_map["AAPL"].composite_score == 72.5
        assert stock_map["MSFT"].composite_score == 45.0
        assert stock_map["GOOGL"].composite_score == 60.0
        # AMZN, TSLA not in per_stock
        assert stock_map["AMZN"].composite_score is None
        assert stock_map["TSLA"].composite_score is None

    def test_direction_and_short_from_ranked(self):
        """ranked 데이터에서 direction/short_eligible이 올바르게 매핑되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        stock_map = {sf.symbol: sf for sf in fact_sheet["stocks"]}
        assert stock_map["TSLA"].direction == "short"
        assert stock_map["TSLA"].short_eligible is True
        assert stock_map["TSLA"].short_signal_count == 3
        assert stock_map["AAPL"].direction == "long"
        assert stock_map["AAPL"].short_eligible is False

    def test_regime_counts(self):
        """레짐 분포가 올바르게 계산되는지 확인."""
        builder = FactSheetBuilder()
        market_data = _make_market_data()
        ranked = _make_ranked()

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data=None,
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        counts = fact_sheet["market"].regime_counts
        assert counts.get("BULLISH", 0) == 2  # GOOGL, AMZN
        assert counts.get("BEARISH", 0) == 1  # AAPL
        assert counts.get("SIDEWAYS", 0) == 1  # MSFT
        assert counts.get("VOLATILE", 0) == 1  # TSLA

    def test_macd_signal_classification(self):
        """MACD 시그널 분류 테스트."""
        builder = FactSheetBuilder()

        assert builder._classify_macd_signal({"signal": "Bullish"}) == "bullish"
        assert builder._classify_macd_signal({"signal": "Bearish"}) == "bearish"
        assert builder._classify_macd_signal({"signal": "buy"}) == "bullish"
        assert builder._classify_macd_signal({"signal": "sell"}) == "bearish"
        assert builder._classify_macd_signal({"histogram": 1.5}) == "bullish"
        assert builder._classify_macd_signal({"histogram": -0.5}) == "bearish"
        assert builder._classify_macd_signal({"histogram": 0}) == "neutral"
        assert builder._classify_macd_signal({}) == "neutral"

    def test_empty_stocks(self):
        """종목이 없는 경우 빈 리스트 반환."""
        builder = FactSheetBuilder()

        fact_sheet = builder.build(
            market_data={"stocks": {}},
            intelligence_data=None,
            fear_greed_data=None,
            ranked=[],
            daily_changes=None,
            today="2026-03-16",
        )

        assert fact_sheet["stocks"] == []
        assert fact_sheet["ranking"].ranked_symbols == []
        assert fact_sheet["market"].total_symbols == 0

    def test_fear_greed_direct_value_format(self):
        """fear_greed_data에 직접 value 키가 있는 형식도 지원."""
        builder = FactSheetBuilder()
        market_data = _make_market_data(["AAPL"])
        ranked = [
            {
                "symbol": "AAPL",
                "total_score": 50.0,
                "reasons": [],
                "direction": "long",
                "short_eligible": False,
                "short_signal_count": 0,
            }
        ]

        fact_sheet = builder.build(
            market_data=market_data,
            intelligence_data=None,
            fear_greed_data={"value": 42, "value_classification": "Fear"},
            ranked=ranked,
            daily_changes=None,
            today="2026-03-16",
        )

        assert fact_sheet["market"].fear_greed_value == 42
        assert fact_sheet["market"].fear_greed_classification == "Fear"


# ──────────────────────────────────────────────────────────────
# OutputValidator tests
# ──────────────────────────────────────────────────────────────


class TestOutputValidator:
    def _make_fact_sheet(self):
        """검증용 팩트시트를 생성합니다."""
        builder = FactSheetBuilder()
        return builder.build(
            market_data=_make_market_data(),
            intelligence_data=_make_intelligence_data(),
            fear_greed_data=_make_fear_greed_data(),
            ranked=_make_ranked(),
            daily_changes=None,
            today="2026-03-16",
        )

    def test_output_validator_top3_correct(self):
        """올바른 TOP 3 순서는 통과."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        output = """
## 주목할 종목 Top 3
## 🥇 1위: **AAPL** (Apple) — 매수 추천
분석 내용...
## 🥈 2위: **TSLA** (Tesla) — 관망
분석 내용...
## 🥉 3위: **AMZN** (Amazon) — 매수 추천
분석 내용...
"""
        result = validator.validate_worker_b(output, fact_sheet)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_output_validator_top3_wrong_order(self):
        """잘못된 TOP 3 순서는 에러 발생."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        output = """
## 주목할 종목 Top 3
## 🥇 1위: **TSLA** (Tesla) — 매수 추천
## 🥈 2위: **AAPL** (Apple) — 관망
## 🥉 3위: **AMZN** (Amazon) — 매수 추천
"""
        result = validator.validate_worker_b(output, fact_sheet)
        assert result.is_valid is False
        assert any("TOP 3 순위 불일치" in e for e in result.errors)

    def test_output_validator_short_eligibility(self):
        """숏 적격이 아닌 종목을 숏 추천하면 에러."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        # AAPL is NOT short_eligible but we recommend short
        output = """
## 주목할 종목 Top 3
## 🥇 1위: **AAPL** (Apple) — 숏 포지션 추천
AAPL은 공매도가 적절합니다.
## 🥈 2위: **TSLA** (Tesla) — 숏 추천
## 🥉 3위: **AMZN** (Amazon) — 매수 추천
"""
        result = validator.validate_worker_b(output, fact_sheet)
        assert any("숏 적격=False" in e for e in result.errors)

    def test_output_validator_short_eligible_stock_ok(self):
        """숏 적격인 종목(TSLA)의 숏 추천은 에러가 아님."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        output = """
## 주목할 종목 Top 3
## 🥇 1위: **AAPL** (Apple) — 매수 추천
## 🥈 2위: **TSLA** (Tesla) — 숏 추천
TSLA short 포지션이 적합합니다.
## 🥉 3위: **AMZN** (Amazon) — 매수 추천
"""
        result = validator.validate_worker_b(output, fact_sheet)
        # TSLA is short_eligible, so no error for TSLA short
        tsla_errors = [e for e in result.errors if "TSLA" in e and "숏 적격" in e]
        assert len(tsla_errors) == 0

    def test_output_validator_empty_output(self):
        """빈 출력은 유효하지 않음."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        result = validator.validate_worker_b("", fact_sheet)
        assert result.is_valid is False
        assert any("비어있습니다" in e for e in result.errors)

        result2 = validator.validate_worker_b("   ", fact_sheet)
        assert result2.is_valid is False

    def test_output_validator_worker_a_basic(self):
        """Worker A 기본 검증."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        output = "AAPL MSFT GOOGL AMZN TSLA 시장 분석 결과"
        result = validator.validate_worker_a(output, fact_sheet)
        assert result.is_valid is True

    def test_output_validator_worker_a_empty(self):
        """Worker A 빈 출력은 에러."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        result = validator.validate_worker_a("", fact_sheet)
        assert result.is_valid is False

    def test_output_validator_worker_a_missing_symbols(self):
        """Worker A에서 종목 누락 시 경고."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        output = "AAPL MSFT 시장 분석 결과"
        result = validator.validate_worker_a(output, fact_sheet)
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("누락" in w for w in result.warnings)

    def test_extract_top3_symbols_various_formats(self):
        """다양한 마크다운 포맷에서 심볼 추출 테스트."""
        validator = OutputValidator()

        # Format 1: 위 + 콜론
        output1 = """
## 🥇 1위: **AAPL** (Apple)
## 🥈 2위: **MSFT** (Microsoft)
## 🥉 3위: **GOOGL** (Alphabet)
"""
        assert validator._extract_top3_symbols(output1) == ["AAPL", "MSFT", "GOOGL"]

        # Format 2: ### numbered
        output2 = """
### 1. AAPL
### 2. MSFT
### 3. GOOGL
"""
        assert validator._extract_top3_symbols(output2) == ["AAPL", "MSFT", "GOOGL"]

        # Format 3: ### numbered bold
        output3 = """
### 1. **AAPL**
### 2. **MSFT**
### 3. **GOOGL**
"""
        assert validator._extract_top3_symbols(output3) == ["AAPL", "MSFT", "GOOGL"]

        # Format 4: medal emoji
        output4 = """
🥇 AAPL 분석 ...
🥈 MSFT 분석 ...
🥉 GOOGL 분석 ...
"""
        assert validator._extract_top3_symbols(output4) == ["AAPL", "MSFT", "GOOGL"]

    def test_extract_top3_no_match(self):
        """심볼을 찾지 못하면 빈 리스트 반환."""
        validator = OutputValidator()
        result = validator._extract_top3_symbols("일반 텍스트만 있는 문서")
        assert result == []

    def test_direction_consistency_warning(self):
        """Intelligence 방향과 출력 톤 불일치 시 경고 발생."""
        validator = OutputValidator()
        fact_sheet = self._make_fact_sheet()

        # Intelligence is bullish but output is very bearish
        output = """
## 🥇 1위: **AAPL**
## 🥈 2위: **TSLA**
## 🥉 3위: **AMZN**
약세 약세 약세 하락 하락 하락 하락 bearish bearish bearish
부정적 전망 부정적 전망 부정적 전망
"""
        result = validator.validate_worker_b(output, fact_sheet)
        assert any("방향 불일치" in w for w in result.warnings)

    def test_validation_result_defaults(self):
        """ValidationResult 기본값 테스트."""
        result = ValidationResult(is_valid=True)
        assert result.errors == []
        assert result.warnings == []

    def test_no_ranking_in_fact_sheet(self):
        """fact_sheet에 ranking이 없을 때 경고로 처리."""
        validator = OutputValidator()
        fact_sheet = {"market": MarketFact(
            analysis_date="2026-03-16",
            total_symbols=0,
            symbols_list=[],
            intelligence_score=0,
            intelligence_signal="neutral",
            layer_scores={},
        )}

        output = "some output text"
        result = validator.validate_worker_b(output, fact_sheet)
        assert any("ranking 데이터가 없어" in w for w in result.warnings)


# ──────────────────────────────────────────────────────────────
# Bidirectional scenario analysis tests
# ──────────────────────────────────────────────────────────────


class TestBidirectionalScenario:
    """양방향 시나리오 분석 관련 테스트"""

    def test_ranking_fact_has_short_signal_counts(self):
        """RankingFact에 short_signal_counts 필드 존재"""
        rf = RankingFact(
            ranked_symbols=["AAPL"],
            scores={"AAPL": 80},
            reasons={"AAPL": ["test"]},
            directions={"AAPL": "long"},
            short_signal_counts={"AAPL": 2},
        )
        assert rf.short_signal_counts["AAPL"] == 2

    def test_signal_tag_bearish(self):
        """약세시그널 3/5 이상이면 ⚠️ 태그"""
        builder = FactSheetBuilder()
        fact_sheet = {
            "market": MarketFact(
                analysis_date="2026-03-16",
                total_symbols=1,
                symbols_list=["TEST"],
                intelligence_score=0,
                intelligence_signal="neutral",
                layer_scores={},
                regime_counts={"BEARISH": 1},
            ),
            "stocks": [
                StockFact(
                    symbol="TEST",
                    current_price=100,
                    change_1d=-2,
                    change_5d=-5,
                    change_20d=-10,
                    rsi_value=78,
                    rsi_zone="overbought",
                    macd_signal="bearish",
                    regime="BEARISH",
                    regime_confidence=0.7,
                    short_signal_count=4,
                    short_eligible=True,
                    direction="short",
                )
            ],
            "ranking": RankingFact(
                ranked_symbols=["TEST"],
                scores={"TEST": 80},
                reasons={"TEST": ["RSI 78 과매수"]},
                directions={"TEST": "short"},
                short_signal_counts={"TEST": 4},
            ),
        }
        block = builder.to_prompt_block(fact_sheet)
        assert "⚠️ 약세시그널 4/5" in block

    def test_signal_tag_bullish(self):
        """약세시그널 2/5 이하이면 📈 태그"""
        builder = FactSheetBuilder()
        fact_sheet = {
            "market": MarketFact(
                analysis_date="2026-03-16",
                total_symbols=1,
                symbols_list=["AAPL"],
                intelligence_score=10,
                intelligence_signal="bullish",
                layer_scores={},
                regime_counts={"BULLISH": 1},
            ),
            "stocks": [
                StockFact(
                    symbol="AAPL",
                    current_price=250,
                    change_1d=1,
                    change_5d=2,
                    change_20d=5,
                    rsi_value=55,
                    rsi_zone="neutral",
                    macd_signal="bullish",
                    regime="BULLISH",
                    regime_confidence=0.8,
                    short_signal_count=0,
                )
            ],
            "ranking": RankingFact(
                ranked_symbols=["AAPL"],
                scores={"AAPL": 75},
                reasons={"AAPL": ["RSI 55 neutral"]},
                directions={"AAPL": "long"},
                short_signal_counts={"AAPL": 0},
            ),
        }
        block = builder.to_prompt_block(fact_sheet)
        assert "\U0001f4c8" in block
        assert "⚠️ 약세시그널" not in block

    def test_bidirectional_section_appears(self):
        """약세 시그널 집중 종목이 있으면 양방향 분석 섹션 존재"""
        builder = FactSheetBuilder()
        fact_sheet = {
            "market": MarketFact(
                analysis_date="2026-03-16",
                total_symbols=1,
                symbols_list=["GOOGL"],
                intelligence_score=-5,
                intelligence_signal="neutral",
                layer_scores={},
                regime_counts={"BEARISH": 1},
            ),
            "stocks": [
                StockFact(
                    symbol="GOOGL",
                    current_price=300,
                    change_1d=-3,
                    change_5d=-5,
                    change_20d=-8,
                    rsi_value=76,
                    rsi_zone="overbought",
                    macd_signal="bearish",
                    regime="BEARISH",
                    regime_confidence=0.6,
                    short_signal_count=3,
                    short_eligible=True,
                    direction="short",
                )
            ],
            "ranking": RankingFact(
                ranked_symbols=["GOOGL"],
                scores={"GOOGL": 70},
                reasons={"GOOGL": ["BEARISH"]},
                directions={"GOOGL": "short"},
                short_signal_counts={"GOOGL": 3},
            ),
        }
        block = builder.to_prompt_block(fact_sheet)
        assert "양방향 시나리오 분석 필요" in block
        assert "하락 시나리오" in block
        assert "반등 시나리오" in block

    def test_no_bidirectional_section_when_no_concentrated(self):
        """약세 시그널 집중 종목 없으면 양방향 섹션 없음"""
        builder = FactSheetBuilder()
        fact_sheet = {
            "market": MarketFact(
                analysis_date="2026-03-16",
                total_symbols=1,
                symbols_list=["AAPL"],
                intelligence_score=10,
                intelligence_signal="bullish",
                layer_scores={},
                regime_counts={"BULLISH": 1},
            ),
            "stocks": [
                StockFact(
                    symbol="AAPL",
                    current_price=250,
                    change_1d=1,
                    change_5d=2,
                    change_20d=5,
                    rsi_value=55,
                    rsi_zone="neutral",
                    macd_signal="bullish",
                    regime="BULLISH",
                    regime_confidence=0.8,
                    short_signal_count=1,
                )
            ],
            "ranking": RankingFact(
                ranked_symbols=["AAPL"],
                scores={"AAPL": 75},
                reasons={"AAPL": ["neutral"]},
                short_signal_counts={"AAPL": 1},
            ),
        }
        block = builder.to_prompt_block(fact_sheet)
        assert "양방향 시나리오 분석 필요" not in block
