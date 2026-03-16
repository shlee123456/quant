"""
PromptEngine / PromptDataBuilder 유닛 테스트.

Jinja2 기반 프롬프트 렌더링 엔진, 데이터 빌더, 포맷 필터,
하위 호환성(backward compatibility)을 검증합니다.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import pytest

from trading_bot.prompts.prompt_engine import PromptEngine
from trading_bot.prompts.prompt_data import (
    PromptDataBuilder,
    _build_intelligence_block,
    _build_intelligence_summary,
    _build_daily_changes_block,
    _calculate_var_95,
    _calculate_strategy_pnl_breakdown,
    _format_trade_log,
    _extract_forward_look_data,
    _load_previous_top3,
    _save_top3_marker,
    assemble_sections,
    validate_assembly,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def engine():
    return PromptEngine()


@pytest.fixture
def builder():
    return PromptDataBuilder()


@pytest.fixture
def sample_market_data() -> Dict:
    """최소한의 시장 데이터 픽스처."""
    return {
        "market_summary": {"average_rsi": 55.0},
        "stocks": {
            "AAPL": {
                "price": {"last": 195.0, "change_1d": 0.5, "change_5d": 2.1, "change_20d": -1.3},
                "indicators": {
                    "rsi": {"value": 52.0},
                    "macd": {"signal": "Bullish"},
                    "bollinger": {"signal": "Neutral"},
                    "adx": {"value": 28.5},
                },
                "regime": {"state": "BULLISH", "confidence": 0.78},
                "patterns": {"support_levels": [190.0, 185.0, 180.0]},
                "signal_diagnosis": {"optimal_rsi_range": {"oversold": 30, "overbought": 70}},
            },
            "MSFT": {
                "price": {"last": 420.0, "change_1d": -0.3, "change_5d": 1.5, "change_20d": 3.2},
                "indicators": {
                    "rsi": {"value": 68.0},
                    "macd": {"signal": "Bearish"},
                    "bollinger": {"signal": "Upper"},
                    "adx": {"value": 32.0},
                },
                "regime": {"state": "BULLISH", "confidence": 0.85},
                "patterns": {"support_levels": [410.0, 400.0]},
                "signal_diagnosis": {"optimal_rsi_range": {"oversold": 30, "overbought": 70}},
            },
        },
    }


@pytest.fixture
def sample_news_data() -> Dict:
    return {
        "market_news": [
            {"title": "Fed holds rates steady", "source": "Reuters"},
        ],
        "stock_news": {
            "AAPL": [
                {"title": "Apple announces new product", "source": "Bloomberg"},
            ],
        },
    }


@pytest.fixture
def sample_fear_greed_data() -> Dict:
    return {
        "current": {"value": 45, "classification": "Fear", "timestamp": "2026-03-16T10:00:00"},
        "history": [
            {"date": "2026-03-15", "value": 42, "classification": "Fear"},
            {"date": "2026-03-14", "value": 48, "classification": "Neutral"},
        ],
    }


@pytest.fixture
def sample_intelligence_data() -> Dict:
    return {
        "overall": {"score": 2.5, "signal": "Mildly Bullish", "interpretation": "약한 상승 시그널"},
        "layers": {
            "macro_regime": {"score": 1.0, "signal": "Neutral", "confidence": 0.6, "interpretation": "중립", "metrics": {}},
            "sentiment": {"score": 3.0, "signal": "Bullish", "confidence": 0.8, "interpretation": "긍정적", "metrics": {}},
        },
    }


# =========================================================================
# PromptEngine 기본 렌더링 테스트
# =========================================================================


class TestPromptEngineRendersTemplate:
    """test_prompt_engine_renders_template"""

    def test_render_footer_template(self, engine):
        result = engine.render("footer.md.j2", {"today": "2026-03-16"})
        assert "2026-03-16" in result
        assert "분석 생성" in result
        assert "::: callout" in result

    def test_render_format_rules(self, engine):
        result = engine.render("format_rules.md.j2", {})
        assert "FORMAT RULES" in result
        assert 'color="blue"' in result

    def test_render_notion_writer(self, engine):
        result = engine.render("notion_writer.md.j2", {
            "assembled_content": "test content",
            "today": "2026-03-16",
            "parent_page_id": "abc-123",
        })
        assert "abc-123" in result
        assert "test content" in result
        assert "2026-03-16" in result

    def test_render_worker_a(self, engine):
        ctx = {
            "today": "2026-03-16",
            "symbols": ["AAPL", "MSFT"],
            "symbols_str": "AAPL, MSFT",
            "symbols_count": 2,
            "json_str": '{"stocks": {}}',
            "intel_block": "",
            "rag_block": "",
            "macro_block": "",
            "events_block": "",
            "fundamentals_block": "",
            "fg_block": "",
            "daily_changes_block": "",
            "macro_section_template": "",
            "section_spec": "**섹션 1과 섹션 2만**",
            "section_note": "섹션 1과 2만 출력합니다",
        }
        result = engine.render("worker_a.md.j2", ctx)
        assert "워커 A" in result
        assert "AAPL, MSFT" in result
        assert "FORMAT RULES" in result  # format_rules included

    def test_render_worker_c_with_sessions(self, engine):
        ctx = {
            "today": "2026-03-16",
            "has_sessions": True,
            "intel_summary": "",
            "daily_changes_block": "",
            "metrics_json": "{}",
            "forward_json": "{}",
            "stocks_json": "{}",
            "fact_sheet_block": "",
        }
        result = engine.render("worker_c.md.j2", ctx)
        assert "# 7. 성과 대시보드" in result
        assert "# 10. 리스크 요인" in result

    def test_render_worker_c_without_sessions(self, engine):
        ctx = {
            "today": "2026-03-16",
            "has_sessions": False,
            "intel_summary": "",
            "daily_changes_block": "",
            "metrics_json": "",
            "forward_json": "{}",
            "stocks_json": "{}",
            "fact_sheet_block": "",
        }
        result = engine.render("worker_c.md.j2", ctx)
        assert "# 7. 전방 전망" in result
        assert "# 8. 리스크 요인" in result
        assert "# 10." not in result


# =========================================================================
# PromptDataBuilder 컨텍스트 생성 테스트
# =========================================================================


class TestPromptDataBuilderWorkerAContext:
    """test_prompt_data_builder_worker_a_context"""

    def test_basic_context(self, builder, sample_market_data):
        ctx = builder.build_worker_a_context(sample_market_data, "2026-03-16")
        assert ctx["today"] == "2026-03-16"
        assert "AAPL" in ctx["symbols"]
        assert "MSFT" in ctx["symbols"]
        assert ctx["symbols_count"] == 2
        assert "AAPL" in ctx["symbols_str"]
        assert "json_str" in ctx
        # 매크로 없으면 섹션 1, 2만
        assert "섹션 1" in ctx["section_note"]

    def test_with_macro_data(self, builder, sample_market_data):
        macro = {
            "indices": {"SPY": {"last": 500, "chg_1d": 0.5, "chg_5d": 1.2, "chg_20d": 3.0, "rsi": 55}},
            "sectors": {},
        }
        ctx = builder.build_worker_a_context(
            sample_market_data, "2026-03-16", macro_data=macro,
        )
        assert "매크로" in ctx["section_note"]
        assert ctx["macro_block"] != ""
        assert ctx["macro_section_template"] != ""


class TestPromptDataBuilderWorkerBContext:
    """test_prompt_data_builder_worker_b_context — top3_symbols 반환 검증."""

    @patch("trading_bot.prompts.prompt_data._compute_top3_candidates")
    def test_returns_top3_symbols(self, mock_top3, builder, sample_market_data, sample_news_data, sample_fear_greed_data):
        mock_top3.return_value = ("ranking text", ["AAPL", "MSFT", "GOOGL"])
        ctx, top3 = builder.build_worker_b_context(
            sample_market_data, sample_news_data, sample_fear_greed_data, "2026-03-16",
        )
        assert top3 == ["AAPL", "MSFT", "GOOGL"]
        assert "stocks_json" in ctx
        assert "news_block" in ctx

    @patch("trading_bot.prompts.prompt_data._compute_top3_candidates")
    def test_worker_a_reflection(self, mock_top3, builder, sample_market_data, sample_news_data, sample_fear_greed_data):
        mock_top3.return_value = ("", [])
        ctx, _ = builder.build_worker_b_context(
            sample_market_data, sample_news_data, sample_fear_greed_data, "2026-03-16",
            worker_a_context="Worker A wrote this",
        )
        assert "Worker-A 분석 결과" in ctx["reflection_block"]


class TestPromptDataBuilderWorkerCContext:
    """test_prompt_data_builder_worker_c_context"""

    def test_with_sessions(self, builder, sample_market_data):
        metrics = {
            "session_details": [{"session_id": "s1", "total_return": 2.5}],
            "var_95": -1.5,
            "strategy_pnl_breakdown": [],
            "trade_log": [],
        }
        ctx = builder.build_worker_c_context(
            sample_market_data, metrics, "2026-03-16", True,
        )
        assert ctx["has_sessions"] is True
        assert ctx["metrics_json"] != ""
        assert "forward_json" in ctx

    def test_without_sessions(self, builder, sample_market_data):
        ctx = builder.build_worker_c_context(
            sample_market_data, {}, "2026-03-16", False,
        )
        assert ctx["has_sessions"] is False
        assert ctx["metrics_json"] == ""


# =========================================================================
# 필터 테스트
# =========================================================================


class TestFormatFilters:
    """test_format_filters"""

    def test_format_price(self):
        assert PromptEngine._filter_format_price(1234.5) == "$1,234.50"
        assert PromptEngine._filter_format_price(None) == "N/A"
        assert PromptEngine._filter_format_price("abc") == "abc"

    def test_format_pct(self):
        assert PromptEngine._filter_format_pct(1.234) == "+1.23%"
        assert PromptEngine._filter_format_pct(-0.5) == "-0.50%"
        assert PromptEngine._filter_format_pct(None) == "N/A"

    def test_color_pct(self):
        result = PromptEngine._filter_color_pct(2.5)
        assert 'color="green"' in result
        assert "+2.50%" in result

        result = PromptEngine._filter_color_pct(-1.3)
        assert 'color="red"' in result
        assert "-1.30%" in result

        assert PromptEngine._filter_color_pct(None) == "N/A"


# =========================================================================
# 하위 호환성 테스트
# =========================================================================


class TestBackwardCompatibility:
    """test_backward_compatibility — build_worker_b_prompt returns Tuple[str, List[str]]."""

    @patch("trading_bot.prompts.prompt_data._compute_top3_candidates")
    @patch("trading_bot.prompts.prompt_data._build_historical_performance_block", return_value="")
    def test_build_worker_b_returns_tuple(self, mock_rag, mock_top3, sample_market_data, sample_news_data, sample_fear_greed_data):
        mock_top3.return_value = ("ranking", ["AAPL", "MSFT", "TSLA"])
        from trading_bot.parallel_prompt_builder import build_worker_b_prompt

        result = build_worker_b_prompt(
            sample_market_data, sample_news_data, sample_fear_greed_data, "2026-03-16",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        prompt, top3 = result
        assert isinstance(prompt, str)
        assert isinstance(top3, list)
        assert len(prompt) > 0

    def test_imports_from_parallel_prompt_builder(self):
        """notion_writer.py 가 사용하는 모든 이름이 import 가능한지 확인."""
        from trading_bot.parallel_prompt_builder import (
            WORKER_MODELS,
            precompute_session_metrics,
            build_worker_a_prompt,
            build_worker_b_prompt,
            build_worker_c_prompt,
            build_notion_writer_prompt,
            assemble_sections,
            validate_assembly,
            _load_previous_top3,
            _save_top3_marker,
        )
        assert callable(precompute_session_metrics)
        assert callable(build_worker_a_prompt)
        assert callable(build_worker_b_prompt)
        assert callable(build_worker_c_prompt)
        assert callable(build_notion_writer_prompt)
        assert callable(assemble_sections)
        assert callable(validate_assembly)
        assert callable(_load_previous_top3)
        assert callable(_save_top3_marker)
        assert isinstance(WORKER_MODELS, dict)


# =========================================================================
# 템플릿 include 테스트
# =========================================================================


class TestTemplateIncludes:
    """test_template_includes — format_rules 가 include 되는지 검증."""

    def test_worker_a_includes_format_rules(self, engine):
        ctx = {
            "today": "2026-03-16",
            "symbols": ["AAPL"],
            "symbols_str": "AAPL",
            "symbols_count": 1,
            "json_str": "{}",
            "intel_block": "",
            "rag_block": "",
            "macro_block": "",
            "events_block": "",
            "fundamentals_block": "",
            "fg_block": "",
            "daily_changes_block": "",
            "macro_section_template": "",
            "section_spec": "**섹션 1과 섹션 2만**",
            "section_note": "섹션 1과 2만 출력합니다",
        }
        result = engine.render("worker_a.md.j2", ctx)
        assert "FORMAT RULES (MANDATORY)" in result
        assert "END FORMAT RULES" in result

    def test_worker_b_includes_format_rules(self, engine):
        ctx = {
            "today": "2026-03-16",
            "intel_summary": "",
            "top3_ranking": "",
            "prev_top3_block": "",
            "rag_block": "",
            "reflection_block": "",
            "stocks_json": "{}",
            "news_block": "",
            "fg_block": "",
        }
        result = engine.render("worker_b.md.j2", ctx)
        assert "FORMAT RULES (MANDATORY)" in result

    def test_worker_c_includes_format_rules(self, engine):
        ctx = {
            "today": "2026-03-16",
            "has_sessions": False,
            "intel_summary": "",
            "daily_changes_block": "",
            "metrics_json": "",
            "forward_json": "{}",
            "stocks_json": "{}",
            "fact_sheet_block": "",
        }
        result = engine.render("worker_c.md.j2", ctx)
        assert "FORMAT RULES (MANDATORY)" in result


# =========================================================================
# 데이터 헬퍼 함수 테스트
# =========================================================================


class TestDataHelpers:
    """데이터 가공 헬퍼 함수들의 기본 동작 검증."""

    def test_build_intelligence_block_empty(self):
        assert _build_intelligence_block(None) == ""
        assert _build_intelligence_block({}) == ""

    def test_build_intelligence_block_with_data(self, sample_intelligence_data):
        result = _build_intelligence_block(sample_intelligence_data)
        assert "5-Layer" in result
        assert "+2.5" in result

    def test_build_intelligence_summary_empty(self):
        assert _build_intelligence_summary(None) == ""

    def test_build_intelligence_summary_with_data(self, sample_intelligence_data):
        result = _build_intelligence_summary(sample_intelligence_data)
        assert "Intelligence 요약" in result
        assert "Mildly Bullish" in result

    def test_build_daily_changes_block_empty(self):
        assert _build_daily_changes_block(None) == ""
        assert _build_daily_changes_block({}) == ""
        assert _build_daily_changes_block({"has_previous": False}) == ""

    def test_calculate_var_95_insufficient_data(self):
        assert _calculate_var_95([]) is None
        assert _calculate_var_95([{"total_value": 100}]) is None

    def test_calculate_var_95_with_data(self):
        snapshots = [{"total_value": 100 + i * 0.5} for i in range(50)]
        result = _calculate_var_95(snapshots)
        assert result is not None
        assert isinstance(result, float)

    def test_calculate_strategy_pnl_breakdown_empty(self):
        assert _calculate_strategy_pnl_breakdown([]) == []

    def test_calculate_strategy_pnl_breakdown_with_trades(self):
        trades = [
            {"symbol": "AAPL", "type": "SELL", "pnl": 100},
            {"symbol": "AAPL", "type": "SELL", "pnl": -50},
            {"symbol": "MSFT", "type": "SELL", "pnl": 200},
            {"symbol": "MSFT", "type": "BUY", "pnl": 0},  # BUY 는 무시
        ]
        result = _calculate_strategy_pnl_breakdown(trades)
        assert len(result) == 2
        aapl = next(r for r in result if r["symbol"] == "AAPL")
        assert aapl["total_pnl"] == 50.0
        assert aapl["win_count"] == 1
        assert aapl["loss_count"] == 1

    def test_format_trade_log_empty(self):
        assert _format_trade_log([]) == []

    def test_format_trade_log_limit(self):
        trades = [{"timestamp": f"2026-03-{i:02d}", "symbol": "AAPL", "type": "BUY"} for i in range(1, 11)]
        result = _format_trade_log(trades, limit=5)
        assert len(result) == 5

    def test_extract_forward_look_data(self, sample_market_data):
        result = _extract_forward_look_data(sample_market_data)
        assert "support_resistance" in result
        assert "rsi_pending_signals" in result
        assert "AAPL" in result["support_resistance"]

    def test_load_save_top3_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "2026-03-16.json")
            Path(json_path).write_text("{}")
            _save_top3_marker(json_path, ["AAPL", "MSFT", "GOOGL"])

            # 마커 파일이 생성되었는지 확인
            marker = Path(json_path + ".top3")
            assert marker.exists()
            assert json.loads(marker.read_text()) == ["AAPL", "MSFT", "GOOGL"]

            # _load_previous_top3는 이전 날짜 마커를 찾으므로
            # 오늘 기준 내일을 today로 지정
            result = _load_previous_top3(tmpdir, "2026-03-17")
            assert result == ["AAPL", "MSFT", "GOOGL"]


# =========================================================================
# assemble / validate 테스트
# =========================================================================


class TestAssemblyAndValidation:
    """assemble_sections / validate_assembly 통합 테스트."""

    def test_assemble_sections(self):
        a = "# 1. 시장 요약\ncontent a\n---"
        b = "# 3. Top 3\ncontent b\n---"
        c = "# 6. 전략\ncontent c\n---"
        result = assemble_sections(a, b, c, "2026-03-16")
        assert "<table_of_contents/>" in result
        assert "# 1." in result
        assert "# 3." in result
        assert "# 6." in result
        assert "2026-03-16" in result

    def test_validate_assembly_pass(self):
        content = "# 1. a\n# 2. b\n# 3. c"
        assert validate_assembly(content, ["# 1.", "# 2.", "# 3."]) is True

    def test_validate_assembly_missing_section(self):
        content = "# 1. a\n# 3. c"
        assert validate_assembly(content, ["# 1.", "# 2.", "# 3."]) is False


# =========================================================================
# PromptEngine 포맷 검증 테스트
# =========================================================================


class TestFormatValidation:

    def test_validate_format_rules_clean(self):
        # callout close는 \n:::\n 또는 줄 끝 ::: 로 카운트됨
        # 중복 카운트를 피하기 위해 뒤에 텍스트를 넣음
        clean = '::: callout {icon="x" color="blue_bg"}\ntext\n:::\nmore text'
        warnings = PromptEngine.validate_format_rules(clean)
        assert len(warnings) == 0

    def test_validate_format_rules_mismatched_callout(self):
        bad = '::: callout {icon="x"}\ntext\n'  # missing close
        warnings = PromptEngine.validate_format_rules(bad)
        assert any("callout" in w for w in warnings)

    def test_auto_correct_single_quotes(self):
        content = "<span color='red'>text</span>"
        result, corrections = PromptEngine.auto_correct_format(content)
        assert 'color="red"' in result
        assert len(corrections) > 0


# =========================================================================
# Worker C 숏 트레이드 메트릭 테스트
# =========================================================================


class TestWorkerCShortTradeMetrics:
    """Worker C 세션 메트릭에 숏 데이터 포함 테스트"""

    def test_pnl_breakdown_includes_cover_trades(self):
        """COVER 트레이드가 PnL breakdown에 포함되는지 확인"""
        trades = [
            {"type": "SELL", "symbol": "AAPL", "pnl": 50.0},
            {"type": "COVER", "symbol": "AAPL", "pnl": 30.0},
            {"type": "SELL", "symbol": "MSFT", "pnl": -20.0},
        ]
        result = _calculate_strategy_pnl_breakdown(trades)
        # AAPL should have both SELL and COVER pnl summed
        aapl = [r for r in result if r["symbol"] == "AAPL"][0]
        assert aapl["total_pnl"] == 80.0
        assert aapl["trade_count"] == 2
        assert aapl["long_count"] == 1  # SELL
        assert aapl["short_count"] == 1  # COVER

    def test_pnl_breakdown_sell_close_counted_as_long(self):
        """SELL (CLOSE) 트레이드가 롱으로 카운트되는지 확인"""
        trades = [
            {"type": "SELL (CLOSE)", "symbol": "NVDA", "pnl": 100.0},
        ]
        result = _calculate_strategy_pnl_breakdown(trades)
        assert result[0]["long_count"] == 1
        assert result[0]["short_count"] == 0

    def test_pnl_breakdown_no_cover_trades(self):
        """COVER 트레이드 없을 때 short_count=0"""
        trades = [
            {"type": "SELL", "symbol": "AAPL", "pnl": 50.0},
        ]
        result = _calculate_strategy_pnl_breakdown(trades)
        assert result[0]["short_count"] == 0
