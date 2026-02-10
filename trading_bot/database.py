"""
SQLite database for paper trading sessions, trades, signals, and portfolio snapshots
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class TradingDatabase:
    """
    SQLite database manager for paper trading

    Stores:
    - paper_trading_sessions: Session metadata and performance metrics
    - trades: Individual trade records
    - portfolio_snapshots: Time-series portfolio values
    - strategy_signals: Signal generation history
    """

    def __init__(self, db_path: str = "data/paper_trading.db"):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Create data directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Paper trading sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_trading_sessions (
                session_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                initial_capital REAL NOT NULL,
                final_capital REAL,
                total_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                commission REAL NOT NULL,
                pnl REAL,
                pnl_pct REAL,
                FOREIGN KEY (session_id) REFERENCES paper_trading_sessions (session_id)
            )
        """)

        # Portfolio snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                total_value REAL NOT NULL,
                cash REAL NOT NULL,
                positions TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES paper_trading_sessions (session_id)
            )
        """)

        # Strategy signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_signals (
                signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                signal INTEGER NOT NULL,
                indicator_values TEXT NOT NULL,
                market_price REAL NOT NULL,
                executed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES paper_trading_sessions (session_id)
            )
        """)

        conn.commit()
        conn.close()

    def create_session(self, strategy_name: str, initial_capital: float) -> str:
        """
        Create a new paper trading session

        Args:
            strategy_name: Name of the trading strategy
            initial_capital: Starting capital

        Returns:
            session_id: Unique session identifier
        """
        session_id = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO paper_trading_sessions
            (session_id, strategy_name, start_time, initial_capital, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (session_id, strategy_name, start_time, initial_capital))

        conn.commit()
        conn.close()

        return session_id

    def log_trade(self, session_id: str, trade: Dict[str, Any]):
        """
        Log a trade to the database

        Args:
            session_id: Session identifier
            trade: Trade dictionary with keys:
                - symbol: str
                - timestamp: datetime or str
                - type: str (BUY/SELL)
                - price: float
                - size: float
                - commission: float
                - pnl: float (optional)
                - pnl_pct: float (optional)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Convert timestamp to ISO format if datetime
        timestamp = trade['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        cursor.execute("""
            INSERT INTO trades
            (session_id, symbol, timestamp, type, price, size, commission, pnl, pnl_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            trade.get('symbol', 'UNKNOWN'),
            timestamp,
            trade['type'],
            trade['price'],
            trade['size'],
            trade['commission'],
            trade.get('pnl'),
            trade.get('pnl_pct')
        ))

        conn.commit()
        conn.close()

    def log_signal(self, session_id: str, signal: Dict[str, Any]):
        """
        Log a strategy signal to the database

        Args:
            session_id: Session identifier
            signal: Signal dictionary with keys:
                - symbol: str
                - timestamp: datetime or str
                - signal: int (1=BUY, -1=SELL, 0=HOLD)
                - indicator_values: dict
                - market_price: float
                - executed: bool (optional)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Convert timestamp to ISO format if datetime
        timestamp = signal['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Serialize indicator values to JSON
        indicator_values_json = json.dumps(signal['indicator_values'])

        cursor.execute("""
            INSERT INTO strategy_signals
            (session_id, symbol, timestamp, signal, indicator_values, market_price, executed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            signal['symbol'],
            timestamp,
            signal['signal'],
            indicator_values_json,
            signal['market_price'],
            1 if signal.get('executed', False) else 0
        ))

        conn.commit()
        conn.close()

    def log_portfolio_snapshot(self, session_id: str, snapshot: Dict[str, Any]):
        """
        Log a portfolio snapshot to the database

        Args:
            session_id: Session identifier
            snapshot: Snapshot dictionary with keys:
                - timestamp: datetime or str
                - total_value: float
                - cash: float
                - positions: dict {symbol: shares}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Convert timestamp to ISO format if datetime
        timestamp = snapshot['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Serialize positions to JSON
        positions_json = json.dumps(snapshot['positions'])

        cursor.execute("""
            INSERT INTO portfolio_snapshots
            (session_id, timestamp, total_value, cash, positions)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session_id,
            timestamp,
            snapshot['total_value'],
            snapshot['cash'],
            positions_json
        ))

        conn.commit()
        conn.close()

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session summary including all metadata

        Args:
            session_id: Session identifier

        Returns:
            Session dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM paper_trading_sessions WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_all_sessions(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all paper trading sessions

        Args:
            status_filter: Optional status filter ('active', 'completed', 'interrupted')

        Returns:
            List of session dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if status_filter:
            cursor.execute("""
                SELECT * FROM paper_trading_sessions
                WHERE status = ?
                ORDER BY start_time DESC
            """, (status_filter,))
        else:
            cursor.execute("""
                SELECT * FROM paper_trading_sessions ORDER BY start_time DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def update_session(self, session_id: str, updates: Dict[str, Any]):
        """
        Update session metadata

        Args:
            session_id: Session identifier
            updates: Dictionary of fields to update
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Build SET clause dynamically
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [session_id]

        cursor.execute(f"""
            UPDATE paper_trading_sessions
            SET {set_clause}
            WHERE session_id = ?
        """, values)

        conn.commit()
        conn.close()

    def get_session_trades(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all trades for a session

        Args:
            session_id: Session identifier

        Returns:
            List of trade dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM trades WHERE session_id = ? ORDER BY timestamp
        """, (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_session_snapshots(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all portfolio snapshots for a session

        Args:
            session_id: Session identifier

        Returns:
            List of snapshot dictionaries with deserialized positions
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM portfolio_snapshots WHERE session_id = ? ORDER BY timestamp
        """, (session_id,))

        rows = cursor.fetchall()
        conn.close()

        snapshots = []
        for row in rows:
            snapshot = dict(row)
            # Deserialize positions JSON
            snapshot['positions'] = json.loads(snapshot['positions'])
            snapshots.append(snapshot)

        return snapshots

    def get_session_signals(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all signals for a session

        Args:
            session_id: Session identifier

        Returns:
            List of signal dictionaries with deserialized indicator values
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM strategy_signals WHERE session_id = ? ORDER BY timestamp
        """, (session_id,))

        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signal = dict(row)
            # Deserialize indicator values JSON
            signal['indicator_values'] = json.loads(signal['indicator_values'])
            signals.append(signal)

        return signals

    def recover_zombie_sessions(self) -> int:
        """
        Recover zombie sessions (sessions that are 'active' but not running)

        This should be called when the application starts to mark any
        sessions that were interrupted by container restart or crash.

        Returns:
            Number of sessions recovered
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Find all active sessions
        cursor.execute("""
            SELECT session_id FROM paper_trading_sessions
            WHERE status = 'active'
        """)

        active_sessions = cursor.fetchall()
        count = len(active_sessions)

        if count > 0:
            # Mark them as interrupted
            cursor.execute("""
                UPDATE paper_trading_sessions
                SET status = 'interrupted',
                    end_time = ?
                WHERE status = 'active'
            """, (datetime.now().isoformat(),))

            conn.commit()

        conn.close()
        return count

    def terminate_session(self, session_id: str, final_metrics: Optional[Dict[str, Any]] = None):
        """
        Manually terminate a session

        Args:
            session_id: Session identifier
            final_metrics: Optional final performance metrics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        updates = {
            'status': 'terminated',
            'end_time': datetime.now().isoformat()
        }

        if final_metrics:
            updates.update(final_metrics)

        # Build SET clause
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [session_id]

        cursor.execute(f"""
            UPDATE paper_trading_sessions
            SET {set_clause}
            WHERE session_id = ?
        """, values)

        conn.commit()
        conn.close()

    def get_session_status_counts(self) -> Dict[str, int]:
        """
        Get count of sessions by status

        Returns:
            Dictionary mapping status to count
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM paper_trading_sessions
            GROUP BY status
        """)

        rows = cursor.fetchall()
        conn.close()

        return {row[0]: row[1] for row in rows}

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get all currently active sessions

        Returns:
            List of active session dictionaries
        """
        return self.get_all_sessions(status_filter='active')
