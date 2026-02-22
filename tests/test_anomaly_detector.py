"""
AnomalyDetector 단위 테스트
"""

import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from trading_bot.anomaly_detector import AnomalyDetector


@pytest.fixture
def detector() -> AnomalyDetector:
    """기본 설정의 AnomalyDetector fixture"""
    return AnomalyDetector(
        equity_history_warn_size=4000,
        db_size_warn_bytes=500 * 1024 * 1024,
        stale_trade_hours=4.0,
    )


def _make_trader(equity_history_size: int = 0, trades: list = None) -> MagicMock:
    """테스트용 Mock trader 생성"""
    trader = MagicMock()
    trader.equity_history = [0.0] * equity_history_size
    trader.trades = trades if trades is not None else []
    return trader


# ---------- check_equity_history_size ----------


class TestCheckEquityHistorySize:
    """equity_history 크기 검사 테스트"""

    def test_normal_size_no_alert(self, detector: AnomalyDetector) -> None:
        """정상 크기일 때 알림 없음"""
        traders = {"session_1": _make_trader(equity_history_size=100)}
        alerts = detector.check_equity_history_size(traders)
        assert alerts == []

    def test_exact_threshold_no_alert(self, detector: AnomalyDetector) -> None:
        """기준값과 동일하면 알림 없음"""
        traders = {"session_1": _make_trader(equity_history_size=4000)}
        alerts = detector.check_equity_history_size(traders)
        assert alerts == []

    def test_oversized_triggers_alert(self, detector: AnomalyDetector) -> None:
        """기준 초과 시 알림 발생"""
        traders = {"session_1": _make_trader(equity_history_size=5000)}
        alerts = detector.check_equity_history_size(traders)
        assert len(alerts) == 1
        assert "session_1" in alerts[0]
        assert "5000" in alerts[0]

    def test_multiple_traders_mixed(self, detector: AnomalyDetector) -> None:
        """여러 트레이더 중 일부만 초과"""
        traders = {
            "ok_session": _make_trader(equity_history_size=100),
            "big_session": _make_trader(equity_history_size=8000),
        }
        alerts = detector.check_equity_history_size(traders)
        assert len(alerts) == 1
        assert "big_session" in alerts[0]

    def test_trader_without_equity_history(self, detector: AnomalyDetector) -> None:
        """equity_history 속성이 없는 트레이더"""
        trader = MagicMock(spec=[])  # equity_history 속성 없음
        traders = {"no_attr": trader}
        alerts = detector.check_equity_history_size(traders)
        assert alerts == []

    def test_empty_traders_dict(self, detector: AnomalyDetector) -> None:
        """빈 트레이더 딕셔너리"""
        alerts = detector.check_equity_history_size({})
        assert alerts == []


# ---------- check_db_file_size ----------


class TestCheckDbFileSize:
    """DB 파일 크기 검사 테스트"""

    def test_small_file_no_alert(self, detector: AnomalyDetector, tmp_path) -> None:
        """작은 파일은 알림 없음"""
        db_file = tmp_path / "small.db"
        db_file.write_bytes(b"x" * 1024)  # 1KB
        alerts = detector.check_db_file_size(str(db_file))
        assert alerts == []

    def test_large_file_triggers_alert(self, detector: AnomalyDetector, tmp_path) -> None:
        """500MB 초과 파일은 알림 발생"""
        db_file = tmp_path / "large.db"
        # 실제로 500MB 파일을 만들 수 없으므로 임계값을 낮춰서 테스트
        small_detector = AnomalyDetector(db_size_warn_bytes=100)
        db_file.write_bytes(b"x" * 200)  # 200 bytes > 100 threshold
        alerts = small_detector.check_db_file_size(str(db_file))
        assert len(alerts) == 1
        assert "DB 파일 크기 과다" in alerts[0]

    def test_nonexistent_file_no_alert(self, detector: AnomalyDetector) -> None:
        """존재하지 않는 파일은 알림 없음"""
        alerts = detector.check_db_file_size("/nonexistent/path/db.sqlite")
        assert alerts == []

    def test_exact_threshold_no_alert(self, tmp_path) -> None:
        """정확히 기준값이면 알림 없음"""
        detector = AnomalyDetector(db_size_warn_bytes=100)
        db_file = tmp_path / "exact.db"
        db_file.write_bytes(b"x" * 100)
        alerts = detector.check_db_file_size(str(db_file))
        assert alerts == []


# ---------- check_stale_trades ----------


class TestCheckStaleTrades:
    """오래된 마지막 거래 시간 검사 테스트"""

    def test_recent_trade_no_alert(self, detector: AnomalyDetector) -> None:
        """최근 거래는 알림 없음"""
        recent_time = datetime.now() - timedelta(hours=1)
        trades = [{"timestamp": recent_time, "type": "BUY"}]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []

    def test_stale_trade_triggers_alert(self, detector: AnomalyDetector) -> None:
        """4시간 이상 경과 시 알림 발생"""
        old_time = datetime.now() - timedelta(hours=5)
        trades = [{"timestamp": old_time, "type": "BUY"}]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert len(alerts) == 1
        assert "session_1" in alerts[0]
        assert "5.0시간" in alerts[0]

    def test_no_trades_no_alert(self, detector: AnomalyDetector) -> None:
        """거래 없는 트레이더는 알림 없음"""
        traders = {"session_1": _make_trader(trades=[])}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []

    def test_trade_without_timestamp_no_alert(self, detector: AnomalyDetector) -> None:
        """timestamp가 없는 거래는 무시"""
        trades = [{"type": "BUY"}]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []

    def test_trade_with_non_datetime_timestamp(self, detector: AnomalyDetector) -> None:
        """timestamp가 datetime이 아닌 경우 무시"""
        trades = [{"timestamp": "2026-01-01 10:00:00", "type": "BUY"}]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []

    def test_multiple_trades_checks_last(self, detector: AnomalyDetector) -> None:
        """여러 거래 중 마지막 거래만 검사"""
        old_time = datetime.now() - timedelta(hours=10)
        recent_time = datetime.now() - timedelta(hours=1)
        trades = [
            {"timestamp": old_time, "type": "BUY"},
            {"timestamp": recent_time, "type": "SELL"},
        ]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []

    def test_just_under_threshold_no_alert(self, detector: AnomalyDetector) -> None:
        """4시간 미만이면 알림 없음"""
        under_time = datetime.now() - timedelta(hours=3, minutes=59)
        trades = [{"timestamp": under_time, "type": "BUY"}]
        traders = {"session_1": _make_trader(trades=trades)}
        alerts = detector.check_stale_trades(traders)
        assert alerts == []


# ---------- check_all ----------


class TestCheckAll:
    """check_all 통합 검사 테스트"""

    def test_all_clean_no_alerts(self, detector: AnomalyDetector, tmp_path) -> None:
        """모든 검사 통과 시 빈 리스트"""
        db_file = tmp_path / "clean.db"
        db_file.write_bytes(b"x" * 100)
        recent_time = datetime.now() - timedelta(hours=1)
        traders = {
            "session_1": _make_trader(
                equity_history_size=100,
                trades=[{"timestamp": recent_time, "type": "BUY"}],
            )
        }
        alerts = detector.check_all(traders, db_path=str(db_file))
        assert alerts == []

    def test_aggregates_all_alerts(self, tmp_path) -> None:
        """여러 검사에서 발생한 알림을 모두 합침"""
        # 작은 임계값으로 설정하여 모든 알림 트리거
        detector = AnomalyDetector(
            equity_history_warn_size=10,
            db_size_warn_bytes=50,
            stale_trade_hours=1.0,
        )

        # DB 파일 생성 (임계값 초과)
        db_file = tmp_path / "big.db"
        db_file.write_bytes(b"x" * 100)

        # 트레이더 (equity_history 과다 + 오래된 거래)
        old_time = datetime.now() - timedelta(hours=2)
        traders = {
            "session_1": _make_trader(
                equity_history_size=50,
                trades=[{"timestamp": old_time, "type": "BUY"}],
            )
        }

        alerts = detector.check_all(traders, db_path=str(db_file))
        # equity_history 알림 + DB 크기 알림 + 오래된 거래 알림 = 3개
        assert len(alerts) == 3

    def test_default_db_path(self, detector: AnomalyDetector) -> None:
        """기본 DB 경로 사용"""
        traders = {"session_1": _make_trader(equity_history_size=100)}
        # 기본 경로 파일이 없으면 알림 없음
        alerts = detector.check_all(traders)
        assert isinstance(alerts, list)


# ---------- Custom thresholds ----------


class TestCustomThresholds:
    """커스텀 임계값 설정 테스트"""

    def test_custom_equity_threshold(self) -> None:
        """커스텀 equity_history 임계값"""
        detector = AnomalyDetector(equity_history_warn_size=100)
        traders = {"s1": _make_trader(equity_history_size=150)}
        alerts = detector.check_equity_history_size(traders)
        assert len(alerts) == 1
        assert "100" in alerts[0]

    def test_custom_stale_hours(self) -> None:
        """커스텀 stale_trade_hours 임계값"""
        detector = AnomalyDetector(stale_trade_hours=1.0)
        old_time = datetime.now() - timedelta(hours=2)
        traders = {"s1": _make_trader(trades=[{"timestamp": old_time, "type": "BUY"}])}
        alerts = detector.check_stale_trades(traders)
        assert len(alerts) == 1
        assert "1.0시간" in alerts[0]
