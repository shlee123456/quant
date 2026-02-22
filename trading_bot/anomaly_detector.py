"""
Anomaly Detector for Trading Bot Operations

운영 이상 상태를 감지하여 알림 메시지를 생성합니다.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any


logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    운영 이상 감지기

    검사 항목:
    - equity_history 크기 과다 (메모리 누수 징후)
    - DB 파일 크기 과다 (500MB 초과)
    - 오래된 마지막 거래 시간 (4시간 이상 거래 없음)
    """

    def __init__(
        self,
        equity_history_warn_size: int = 4000,
        db_size_warn_bytes: int = 500 * 1024 * 1024,  # 500MB
        stale_trade_hours: float = 4.0,
    ):
        self.equity_history_warn_size = equity_history_warn_size
        self.db_size_warn_bytes = db_size_warn_bytes
        self.stale_trade_hours = stale_trade_hours

    def check_equity_history_size(self, traders: Dict[str, Any]) -> List[str]:
        """equity_history 크기 검사"""
        alerts: List[str] = []
        for label, trader in traders.items():
            size = len(getattr(trader, 'equity_history', []))
            if size > self.equity_history_warn_size:
                alerts.append(
                    f"[{label}] equity_history 크기 과다: {size}개 "
                    f"(기준: {self.equity_history_warn_size})"
                )
        return alerts

    def check_db_file_size(self, db_path: str) -> List[str]:
        """DB 파일 크기 검사"""
        alerts: List[str] = []
        try:
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                if size > self.db_size_warn_bytes:
                    size_mb = size / (1024 * 1024)
                    alerts.append(
                        f"DB 파일 크기 과다: {size_mb:.1f}MB "
                        f"(기준: {self.db_size_warn_bytes // (1024 * 1024)}MB)"
                    )
        except OSError as e:
            logger.warning(f"DB 파일 크기 확인 실패: {e}")
        return alerts

    def check_stale_trades(self, traders: Dict[str, Any]) -> List[str]:
        """오래된 마지막 거래 시간 검사"""
        alerts: List[str] = []
        threshold = timedelta(hours=self.stale_trade_hours)
        now = datetime.now()

        for label, trader in traders.items():
            trades = getattr(trader, 'trades', [])
            if not trades:
                continue
            last_trade = trades[-1]
            last_time = last_trade.get('timestamp')
            if last_time and isinstance(last_time, datetime):
                elapsed = now - last_time
                if elapsed > threshold:
                    hours = elapsed.total_seconds() / 3600
                    alerts.append(
                        f"[{label}] 마지막 거래 후 {hours:.1f}시간 경과 "
                        f"(기준: {self.stale_trade_hours}시간)"
                    )
        return alerts

    def check_all(
        self, traders: Dict[str, Any], db_path: str = "data/paper_trading.db"
    ) -> List[str]:
        """모든 이상 검사 실행"""
        alerts: List[str] = []
        alerts.extend(self.check_equity_history_size(traders))
        alerts.extend(self.check_db_file_size(db_path))
        alerts.extend(self.check_stale_trades(traders))
        return alerts
