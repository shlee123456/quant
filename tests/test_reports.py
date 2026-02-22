"""
Tests for ReportGenerator

Covers CSV/JSON report generation, daily summary, edge cases.
All database interactions use a temporary in-memory or temp-file TradingDatabase.
"""

import csv
import json
import os
import tempfile
import pytest
from datetime import datetime

from trading_bot.reports import ReportGenerator
from trading_bot.database import TradingDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    """Temporary TradingDatabase backed by a file in tmp_path."""
    db_path = str(tmp_path / "test_reports.db")
    db = TradingDatabase(db_path=db_path)
    yield db


@pytest.fixture
def populated_db(temp_db):
    """TradingDatabase with one session, trades, and snapshots."""
    session_id = temp_db.create_session(
        strategy_name="RSI_14_30_70",
        initial_capital=10000.0,
    )
    now = datetime.now().isoformat()
    # Log some trades
    temp_db.log_trade(session_id, {
        "symbol": "AAPL",
        "timestamp": now,
        "type": "BUY",
        "price": 150.0,
        "size": 10.0,
        "commission": 1.5,
        "pnl": 0.0,
    })
    temp_db.log_trade(session_id, {
        "symbol": "AAPL",
        "timestamp": now,
        "type": "SELL",
        "price": 155.0,
        "size": 10.0,
        "commission": 1.5,
        "pnl": 47.0,
    })
    # Log a portfolio snapshot
    temp_db.log_portfolio_snapshot(session_id, {
        "timestamp": now,
        "total_value": 10047.0,
        "cash": 10047.0,
        "positions": {},
    })
    # Update session summary
    temp_db.update_session(session_id, {
        "final_capital": 10047.0,
        "total_return": 0.47,
        "sharpe_ratio": 1.2,
        "max_drawdown": -1.0,
        "win_rate": 100.0,
        "status": "completed",
    })
    return temp_db, session_id


@pytest.fixture
def report_gen(populated_db):
    """ReportGenerator using populated_db."""
    db, _ = populated_db
    return ReportGenerator(db)


@pytest.fixture
def session_id(populated_db):
    _, sid = populated_db
    return sid


# ---------------------------------------------------------------------------
# _sanitize_session_id
# ---------------------------------------------------------------------------

class TestSanitizeSessionId:

    def test_replaces_colons_and_spaces(self, report_gen):
        assert report_gen._sanitize_session_id("RSI:2026-02-22 10:30") == "RSI_2026-02-22_10_30"

    def test_no_change_for_safe_id(self, report_gen):
        assert report_gen._sanitize_session_id("session_123") == "session_123"


# ---------------------------------------------------------------------------
# generate_session_report - CSV
# ---------------------------------------------------------------------------

class TestGenerateCSVReport:

    def test_csv_report_created(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["csv"]
        )
        assert "csv" in output
        assert os.path.exists(output["csv"])

    def test_csv_summary_content(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["csv"]
        )
        summary_path = output["csv"]
        with open(summary_path, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Header row + data rows
        metrics = {row[0]: row[1] for row in rows}
        assert "Session ID" in metrics
        assert "Strategy" in metrics
        assert "Total Trades" in metrics

    def test_trades_csv_created(self, report_gen, session_id, tmp_path):
        report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["csv"]
        )
        # Find the trades CSV
        safe_id = report_gen._sanitize_session_id(session_id)
        # Date-based subdir
        summary = report_gen.db.get_session_summary(session_id)
        start_time = summary.get("start_time", "")
        if start_time:
            date_str = start_time.split("T")[0] if "T" in start_time else start_time.split()[0]
        else:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
        trades_path = os.path.join(str(tmp_path), date_str, f"{safe_id}_trades.csv")
        assert os.path.exists(trades_path)

        with open(trades_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["type"] == "BUY"
        assert rows[1]["type"] == "SELL"


# ---------------------------------------------------------------------------
# generate_session_report - JSON
# ---------------------------------------------------------------------------

class TestGenerateJSONReport:

    def test_json_report_created(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["json"]
        )
        assert "json" in output
        assert os.path.exists(output["json"])

    def test_json_report_content(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["json"]
        )
        with open(output["json"], "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["session_id"] == session_id
        assert "summary" in data
        assert "trades" in data
        assert len(data["trades"]) == 2
        assert "snapshots" in data
        assert "generated_at" in data


# ---------------------------------------------------------------------------
# generate_session_report - both formats
# ---------------------------------------------------------------------------

class TestGenerateBothFormats:

    def test_default_generates_both(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path)
        )
        assert "csv" in output
        assert "json" in output

    def test_date_based_directory(self, report_gen, session_id, tmp_path):
        output = report_gen.generate_session_report(
            session_id, output_dir=str(tmp_path)
        )
        # Files should be in a date-based subdir
        for path in output.values():
            # Parent dir should be a date string like 2026-02-22
            parent = os.path.basename(os.path.dirname(path))
            assert len(parent) == 10  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# generate_session_report - error / edge cases
# ---------------------------------------------------------------------------

class TestGenerateReportEdgeCases:

    def test_nonexistent_session_returns_empty(self, report_gen, tmp_path):
        output = report_gen.generate_session_report(
            "nonexistent_session", output_dir=str(tmp_path)
        )
        assert output == {}

    def test_session_with_no_trades(self, temp_db, tmp_path):
        session_id = temp_db.create_session("NoTrade", 5000.0)
        temp_db.update_session(session_id, {
            "final_capital": 5000.0,
            "total_return": 0.0,
            "status": "completed",
        })
        gen = ReportGenerator(temp_db)
        output = gen.generate_session_report(session_id, output_dir=str(tmp_path))
        assert "json" in output
        with open(output["json"], "r") as f:
            data = json.load(f)
        assert data["trades"] == []

    def test_none_metric_values(self, temp_db, tmp_path):
        """None metric values should be handled gracefully in CSV."""
        session_id = temp_db.create_session("NullMetrics", 10000.0)
        # Set final_capital to avoid format error, but leave other metrics as None
        temp_db.update_session(session_id, {
            "final_capital": 10000.0,
            "status": "completed",
        })
        gen = ReportGenerator(temp_db)
        output = gen.generate_session_report(
            session_id, output_dir=str(tmp_path), formats=["csv"]
        )
        assert "csv" in output
        # Should not raise


# ---------------------------------------------------------------------------
# generate_daily_summary
# ---------------------------------------------------------------------------

class TestGenerateDailySummary:

    def test_daily_summary_created(self, report_gen, session_id, tmp_path):
        # Get the date from the session
        summary = report_gen.db.get_session_summary(session_id)
        start_time = summary.get("start_time", "")
        if start_time:
            date_str = start_time.split("T")[0] if "T" in start_time else start_time.split()[0]
        else:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")

        result = report_gen.generate_daily_summary(
            output_dir=str(tmp_path), date=date_str
        )
        assert result != ""
        assert os.path.exists(result)

    def test_daily_summary_no_sessions(self, report_gen, tmp_path):
        result = report_gen.generate_daily_summary(
            output_dir=str(tmp_path), date="1999-01-01"
        )
        assert result == ""

    def test_daily_summary_csv_content(self, report_gen, session_id, tmp_path):
        summary = report_gen.db.get_session_summary(session_id)
        start_time = summary.get("start_time", "")
        if start_time:
            date_str = start_time.split("T")[0] if "T" in start_time else start_time.split()[0]
        else:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")

        result = report_gen.generate_daily_summary(
            output_dir=str(tmp_path), date=date_str
        )
        with open(result, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 1
        assert "session_id" in rows[0]
        assert "strategy_name" in rows[0]
