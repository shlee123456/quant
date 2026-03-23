"""
SQLite database for paper trading sessions, trades, signals, and portfolio snapshots
"""

import sqlite3
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_display_name(strategy_name: str, symbols: List[str], preset_name: Optional[str] = None) -> str:
    """세션 표시 이름 생성"""
    if not symbols:
        symbols_summary = ""
    elif len(symbols) == 1:
        symbols_summary = symbols[0]
    else:
        symbols_summary = f"{symbols[0]}외{len(symbols) - 1}"
    label = preset_name if preset_name else strategy_name
    return f"{label} | {symbols_summary}" if symbols_summary else label


class TradingDatabase:
    """
    SQLite database manager for paper trading

    Stores:
    - paper_trading_sessions: Session metadata and performance metrics
    - trades: Individual trade records
    - portfolio_snapshots: Time-series portfolio values
    - strategy_signals: Signal generation history
    """

    def __init__(self, db_path: str = None, busy_timeout: int = None):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file (default from Config)
            busy_timeout: SQLite busy timeout in ms (default from Config)
        """
        from trading_bot.config import Config
        _cfg = Config()

        self.db_path = db_path if db_path is not None else _cfg.get('database.path', 'data/paper_trading.db')
        self.busy_timeout = busy_timeout if busy_timeout is not None else _cfg.get('database.busy_timeout', 5000)

        # Create data directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Initialize database
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for connection reuse with WAL mode"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Enable WAL mode and busy timeout
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")

            # Paper trading sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trading_sessions (
                    session_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    display_name TEXT,
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

            # Indexes for query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_session_id ON trades(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session_id ON portfolio_snapshots(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON portfolio_snapshots(session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_session_id ON strategy_signals(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON strategy_signals(session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON paper_trading_sessions(status)")

            # Regime history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regime_history (
                    regime_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    adx REAL,
                    trend_direction REAL,
                    volatility_percentile REAL,
                    recommended_strategies TEXT,
                    details TEXT,
                    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions (session_id)
                )
            """)

            # LLM decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS llm_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    request_context TEXT,
                    response TEXT,
                    latency_ms REAL,
                    model_name TEXT,
                    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions (session_id)
                )
            """)

            # Indexes for regime_history
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_session_id ON regime_history(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_session_ts ON regime_history(session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_symbol_ts ON regime_history(symbol, timestamp)")

            # Indexes for llm_decisions
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_session_id ON llm_decisions(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_session_ts ON llm_decisions(session_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_type ON llm_decisions(decision_type)")

            # Scheduler commands table (Phase 1)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduler_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    target_label TEXT,
                    created_at TEXT NOT NULL,
                    processed_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_processed ON scheduler_commands(processed_at)")

            # Pending orders table (limit orders)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_orders (
                    order_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    limit_price REAL NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    filled_at TEXT,
                    fill_price REAL,
                    expires_at TEXT,
                    trigger_order TEXT,
                    broker_order_id TEXT,
                    source TEXT DEFAULT 'manual',
                    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions(session_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_session_status ON pending_orders(session_id, status)")

            # -- 시그널 성과 추적 테이블 (Market Intelligence v2) --

            # 일별 시장 시그널 (종목 × 날짜 1행)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_market_signals (
                    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    overall_score REAL,
                    overall_signal TEXT,
                    layer_scores TEXT,
                    indicators TEXT,
                    market_price REAL NOT NULL,
                    fear_greed_value REAL,
                    news_sentiment_score REAL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(date, symbol)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_date ON daily_market_signals(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_symbol ON daily_market_signals(symbol)")

            # 시그널 이후 실제 수익률 (1d/5d/20d 후 비동기 측정)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL UNIQUE,
                    return_1d REAL,
                    return_5d REAL,
                    return_20d REAL,
                    max_drawdown_5d REAL,
                    outcome_correct INTEGER,
                    measured_at TEXT,
                    FOREIGN KEY (signal_id) REFERENCES daily_market_signals(signal_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_so_signal_id ON signal_outcomes(signal_id)")

            # 레이어별 정확도 통계 (일별 스냅샷)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_accuracy_stats (
                    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    layer_name TEXT NOT NULL,
                    lookback_days INTEGER NOT NULL DEFAULT 30,
                    total_signals INTEGER,
                    correct_count INTEGER,
                    accuracy_pct REAL,
                    avg_return_when_bullish REAL,
                    avg_return_when_bearish REAL,
                    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(date, layer_name, lookback_days)
                )
            """)

            # Migrate existing DB: add display_name column if missing
            try:
                cursor.execute("SELECT display_name FROM paper_trading_sessions LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute("ALTER TABLE paper_trading_sessions ADD COLUMN display_name TEXT")

            # Migrate existing DB: add side column to trades if missing
            try:
                cursor.execute("SELECT side FROM trades LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute("ALTER TABLE trades ADD COLUMN side TEXT")

            # -- Live Trading Tables (DB-001) --

            # Live trading sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_trading_sessions (
                    session_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    display_name TEXT,
                    mode TEXT NOT NULL DEFAULT 'dry_run',
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    initial_capital REAL NOT NULL,
                    final_capital REAL,
                    total_return REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    win_rate REAL,
                    status TEXT NOT NULL DEFAULT 'active',
                    kill_switch_reason TEXT,
                    broker_name TEXT,
                    market_type TEXT
                )
            """)

            # Live orders table (NO FK to live_trading_sessions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_orders (
                    internal_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    broker_order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    requested_amount REAL NOT NULL,
                    requested_price REAL,
                    filled_amount REAL DEFAULT 0.0,
                    filled_price REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT,
                    submitted_at TEXT,
                    filled_at TEXT,
                    commission REAL DEFAULT 0.0,
                    slippage_pct REAL DEFAULT 0.0,
                    error_message TEXT
                )
            """)

            # Live trading state table (key-value store)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_trading_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Indexes for live trading tables
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_orders_session ON live_orders(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_orders_status ON live_orders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_trading_sessions(status)")

            conn.commit()
        finally:
            conn.close()

    def create_session(self, strategy_name: str, initial_capital: float, display_name: Optional[str] = None) -> str:
        """
        Create a new paper trading session

        Args:
            strategy_name: Name of the trading strategy
            initial_capital: Starting capital
            display_name: Display name for the session

        Returns:
            session_id: Unique session identifier
        """
        session_id = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO paper_trading_sessions
                (session_id, strategy_name, display_name, start_time, initial_capital, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            """, (session_id, strategy_name, display_name, start_time, initial_capital))

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
        # Convert timestamp to ISO format if datetime
        timestamp = trade['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
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
        # Convert timestamp to ISO format if datetime
        timestamp = signal['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Serialize indicator values to JSON
        indicator_values_json = json.dumps(signal['indicator_values'])

        with self._get_connection() as conn:
            cursor = conn.cursor()
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
        # Convert timestamp to ISO format if datetime
        timestamp = snapshot['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Serialize positions to JSON
        positions_json = json.dumps(snapshot['positions'])

        with self._get_connection() as conn:
            cursor = conn.cursor()
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

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session summary including all metadata

        Args:
            session_id: Session identifier

        Returns:
            Session dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM paper_trading_sessions WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()

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
        with self._get_connection() as conn:
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

        return [dict(row) for row in rows]

    def update_session(self, session_id: str, updates: Dict[str, Any]):
        """
        Update session metadata

        Args:
            session_id: Session identifier
            updates: Dictionary of fields to update
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Build SET clause dynamically
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [session_id]
            cursor.execute(f"""
                UPDATE paper_trading_sessions
                SET {set_clause}
                WHERE session_id = ?
            """, values)

    def get_session_trades(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all trades for a session

        Args:
            session_id: Session identifier

        Returns:
            List of trade dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trades WHERE session_id = ? ORDER BY timestamp
            """, (session_id,))
            rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_session_snapshots(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all portfolio snapshots for a session

        Args:
            session_id: Session identifier

        Returns:
            List of snapshot dictionaries with deserialized positions
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM portfolio_snapshots WHERE session_id = ? ORDER BY timestamp
            """, (session_id,))
            rows = cursor.fetchall()

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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_signals WHERE session_id = ? ORDER BY timestamp
            """, (session_id,))
            rows = cursor.fetchall()

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
        with self._get_connection() as conn:
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

        return count

    def terminate_session(self, session_id: str, final_metrics: Optional[Dict[str, Any]] = None):
        """
        Manually terminate a session

        Args:
            session_id: Session identifier
            final_metrics: Optional final performance metrics
        """
        updates = {
            'status': 'terminated',
            'end_time': datetime.now().isoformat()
        }

        if final_metrics:
            updates.update(final_metrics)

        # Build SET clause
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [session_id]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE paper_trading_sessions
                SET {set_clause}
                WHERE session_id = ?
            """, values)

    def get_session_status_counts(self) -> Dict[str, int]:
        """
        Get count of sessions by status

        Returns:
            Dictionary mapping status to count
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM paper_trading_sessions
                GROUP BY status
            """)
            rows = cursor.fetchall()

        return {row['status']: row['count'] for row in rows}

    def delete_session(self, session_id: str) -> bool:
        """
        세션과 관련 데이터를 완전히 삭제

        Args:
            session_id: 삭제할 세션 ID

        Returns:
            bool: 삭제 성공 여부

        Note:
            active 상태 세션은 삭제 불가
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 세션 존재 여부 및 상태 확인
                cursor.execute(
                    "SELECT status FROM paper_trading_sessions WHERE session_id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()

                if row is None:
                    return False

                if row['status'] == 'active':
                    return False

                # 관련 데이터 삭제 (자식 테이블 먼저)
                cursor.execute("DELETE FROM pending_orders WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM regime_history WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM llm_decisions WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM trades WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM portfolio_snapshots WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM strategy_signals WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM paper_trading_sessions WHERE session_id = ?", (session_id,))

            return True

        except sqlite3.Error as e:
            logger.error("세션 삭제 실패 (session_id=%s): %s", session_id, e)
            return False

    def log_regime(self, session_id: str, regime_data: Dict[str, Any]):
        """
        Log regime detection result

        Args:
            session_id: Session identifier
            regime_data: Dict with keys:
                - symbol: str
                - timestamp: datetime or str
                - regime: str (BULLISH/BEARISH/SIDEWAYS/VOLATILE)
                - confidence: float
                - adx: float
                - trend_direction: float
                - volatility_percentile: float
                - recommended_strategies: list
                - details: dict
        """
        timestamp = regime_data['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        recommended = json.dumps(regime_data.get('recommended_strategies', []))
        details = json.dumps(regime_data.get('details', {}), default=str)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO regime_history
                (session_id, symbol, timestamp, regime, confidence, adx,
                 trend_direction, volatility_percentile, recommended_strategies, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                regime_data.get('symbol', 'UNKNOWN'),
                timestamp,
                regime_data['regime'],
                regime_data['confidence'],
                regime_data.get('adx'),
                regime_data.get('trend_direction'),
                regime_data.get('volatility_percentile'),
                recommended,
                details
            ))

    def get_regime_history(self, session_id: str, symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get regime history for a session

        Args:
            session_id: Session identifier
            symbol: Optional symbol filter
            limit: Maximum number of records

        Returns:
            List of regime dicts with deserialized JSON fields
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute("""
                    SELECT * FROM regime_history
                    WHERE session_id = ? AND symbol = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (session_id, symbol, limit))
            else:
                cursor.execute("""
                    SELECT * FROM regime_history
                    WHERE session_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (session_id, limit))
            rows = cursor.fetchall()

        results = []
        for row in rows:
            r = dict(row)
            r['recommended_strategies'] = json.loads(r['recommended_strategies']) if r['recommended_strategies'] else []
            r['details'] = json.loads(r['details']) if r['details'] else {}
            results.append(r)

        return results

    def log_llm_decision(self, session_id: str, decision_data: Dict[str, Any]):
        """
        Log LLM decision

        Args:
            session_id: Session identifier
            decision_data: Dict with keys:
                - symbol: str
                - timestamp: datetime or str
                - decision_type: str ("signal_filter" or "regime_judge")
                - request_context: dict
                - response: dict
                - latency_ms: float
                - model_name: str
        """
        timestamp = decision_data['timestamp']
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        request_ctx = json.dumps(decision_data.get('request_context', {}), default=str)
        response = json.dumps(decision_data.get('response', {}), default=str)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO llm_decisions
                (session_id, symbol, timestamp, decision_type, request_context,
                 response, latency_ms, model_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                decision_data.get('symbol', 'UNKNOWN'),
                timestamp,
                decision_data['decision_type'],
                request_ctx,
                response,
                decision_data.get('latency_ms'),
                decision_data.get('model_name')
            ))

    def get_llm_decisions(self, session_id: str, decision_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get LLM decisions for a session

        Args:
            session_id: Session identifier
            decision_type: Optional filter ("signal_filter" or "regime_judge")
            limit: Maximum number of records

        Returns:
            List of decision dicts with deserialized JSON fields
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if decision_type:
                cursor.execute("""
                    SELECT * FROM llm_decisions
                    WHERE session_id = ? AND decision_type = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (session_id, decision_type, limit))
            else:
                cursor.execute("""
                    SELECT * FROM llm_decisions
                    WHERE session_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (session_id, limit))
            rows = cursor.fetchall()

        results = []
        for row in rows:
            r = dict(row)
            r['request_context'] = json.loads(r['request_context']) if r['request_context'] else {}
            r['response'] = json.loads(r['response']) if r['response'] else {}
            results.append(r)

        return results

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get all currently active sessions

        Returns:
            List of active session dictionaries
        """
        return self.get_all_sessions(status_filter='active')

    # ── Pending Orders (Limit Orders) CRUD ──────────────────────────

    def create_pending_order(self, order: Dict[str, Any]):
        """지정가 주문 생성

        Args:
            order: 주문 딕셔너리 (order_id, session_id, symbol, side,
                   limit_price, amount, status, created_at 필수,
                   filled_at, fill_price, expires_at, trigger_order,
                   broker_order_id, source 선택)
        """
        created_at = order['created_at']
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        expires_at = order.get('expires_at')
        if isinstance(expires_at, datetime):
            expires_at = expires_at.isoformat()

        trigger_order = order.get('trigger_order')
        if trigger_order is not None and not isinstance(trigger_order, str):
            trigger_order = json.dumps(trigger_order)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_orders
                (order_id, session_id, symbol, side, limit_price, amount,
                 status, created_at, filled_at, fill_price, expires_at,
                 trigger_order, broker_order_id, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order['order_id'],
                order['session_id'],
                order['symbol'],
                order['side'],
                order['limit_price'],
                order['amount'],
                order.get('status', 'pending'),
                created_at,
                order.get('filled_at'),
                order.get('fill_price'),
                expires_at,
                trigger_order,
                order.get('broker_order_id'),
                order.get('source', 'manual'),
            ))

    def update_pending_order(self, order_id: str, updates: Dict[str, Any]):
        """지정가 주문 상태 업데이트

        Args:
            order_id: 주문 ID
            updates: 업데이트할 필드 딕셔너리
                     (status, filled_at, fill_price, broker_order_id 등)
        """
        if not updates:
            return

        # datetime → ISO 변환
        for key in ('filled_at', 'expires_at', 'created_at'):
            if key in updates and isinstance(updates[key], datetime):
                updates[key] = updates[key].isoformat()

        # trigger_order dict → JSON
        if 'trigger_order' in updates:
            val = updates['trigger_order']
            if val is not None and not isinstance(val, str):
                updates['trigger_order'] = json.dumps(val)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [order_id]
            cursor.execute(f"""
                UPDATE pending_orders
                SET {set_clause}
                WHERE order_id = ?
            """, values)

    def get_pending_orders(self, session_id: str, symbol: Optional[str] = None,
                           status: str = 'pending') -> List[Dict[str, Any]]:
        """세션의 대기 중 주문 조회

        Args:
            session_id: 세션 ID
            symbol: 심볼 필터 (None이면 전체)
            status: 상태 필터 (기본 'pending')

        Returns:
            주문 딕셔너리 리스트 (trigger_order JSON 디시리얼라이즈 포함)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute("""
                    SELECT * FROM pending_orders
                    WHERE session_id = ? AND status = ? AND symbol = ?
                    ORDER BY created_at
                """, (session_id, status, symbol))
            else:
                cursor.execute("""
                    SELECT * FROM pending_orders
                    WHERE session_id = ? AND status = ?
                    ORDER BY created_at
                """, (session_id, status))
            rows = cursor.fetchall()

        return [self._deserialize_order(row) for row in rows]

    def get_all_orders(self, session_id: str) -> List[Dict[str, Any]]:
        """세션의 모든 주문 조회 (상태 무관)

        Args:
            session_id: 세션 ID

        Returns:
            주문 딕셔너리 리스트
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pending_orders
                WHERE session_id = ?
                ORDER BY created_at
            """, (session_id,))
            rows = cursor.fetchall()

        return [self._deserialize_order(row) for row in rows]

    def _deserialize_order(self, row: sqlite3.Row) -> Dict[str, Any]:
        """주문 Row를 딕셔너리로 변환 (trigger_order JSON 파싱)"""
        order = dict(row)
        if order.get('trigger_order'):
            try:
                order['trigger_order'] = json.loads(order['trigger_order'])
            except (json.JSONDecodeError, TypeError):
                pass
        return order

    def insert_command(self, command: str, target_label: Optional[str] = None) -> int:
        """스케줄러 제어 명령 삽입

        Args:
            command: 명령 종류 (stop_session, cleanup_zombies, status_dump)
            target_label: 대상 세션 라벨 (stop_session 시 필수)

        Returns:
            삽입된 명령 ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scheduler_commands (command, target_label, created_at)
                VALUES (?, ?, ?)
            """, (command, target_label, datetime.now().isoformat()))
            return cursor.lastrowid

    def get_pending_commands(self) -> List[Dict[str, Any]]:
        """미처리 명령 조회

        Returns:
            미처리 명령 리스트
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, command, target_label, created_at
                FROM scheduler_commands
                WHERE processed_at IS NULL
                ORDER BY created_at
            """)
            return [dict(row) for row in cursor.fetchall()]

    def mark_command_processed(self, command_id: int):
        """명령 처리 완료 마킹

        Args:
            command_id: 처리된 명령 ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE scheduler_commands
                SET processed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), command_id))

    def prune_old_data(self, days_to_keep: int = 30) -> Dict[str, int]:
        """오래된 세션 데이터 정리 (스냅샷, 시그널 삭제, 세션/거래 유지)

        Args:
            days_to_keep: 유지할 일수

        Returns:
            삭제된 레코드 수 딕셔너리
        """
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        deleted = {}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 완료/중단된 세션 중 cutoff 이전 세션 ID 조회
            cursor.execute("""
                SELECT session_id FROM paper_trading_sessions
                WHERE status IN ('completed', 'interrupted', 'terminated')
                AND end_time < ?
            """, (cutoff,))
            old_session_ids = [row['session_id'] for row in cursor.fetchall()]

            if not old_session_ids:
                return {'snapshots': 0, 'signals': 0, 'regimes': 0, 'llm_decisions': 0, 'pending_orders': 0}

            placeholders = ','.join('?' * len(old_session_ids))

            # 스냅샷 삭제
            cursor.execute(f"DELETE FROM portfolio_snapshots WHERE session_id IN ({placeholders})", old_session_ids)
            deleted['snapshots'] = cursor.rowcount

            # 시그널 삭제
            cursor.execute(f"DELETE FROM strategy_signals WHERE session_id IN ({placeholders})", old_session_ids)
            deleted['signals'] = cursor.rowcount

            # 레짐 이력 삭제
            cursor.execute(f"DELETE FROM regime_history WHERE session_id IN ({placeholders})", old_session_ids)
            deleted['regimes'] = cursor.rowcount

            # LLM 결정 삭제
            cursor.execute(f"DELETE FROM llm_decisions WHERE session_id IN ({placeholders})", old_session_ids)
            deleted['llm_decisions'] = cursor.rowcount

            # 지정가 주문 삭제
            cursor.execute(f"DELETE FROM pending_orders WHERE session_id IN ({placeholders})", old_session_ids)
            deleted['pending_orders'] = cursor.rowcount

        return deleted

    def downsample_completed_sessions(self, hours_interval: int = 1) -> Dict[str, int]:
        """완료된 세션의 스냅샷을 시간 간격으로 다운샘플링하고, 미실행 시그널을 삭제

        종료된 세션(completed/interrupted/terminated)의 1분 단위 스냅샷을
        hours_interval 시간 간격으로 축소합니다. 각 시간대별 마지막 스냅샷만 유지합니다.
        시그널은 executed=True(실제 실행된 것)만 유지하고 나머지를 삭제합니다.

        Args:
            hours_interval: 다운샘플링 간격 (시간 단위, 기본 1시간)

        Returns:
            {'snapshots_removed': N, 'signals_removed': N}
        """
        result = {'snapshots_removed': 0, 'signals_removed': 0}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 완료된 세션 ID 조회
            cursor.execute("""
                SELECT session_id FROM paper_trading_sessions
                WHERE status IN ('completed', 'interrupted', 'terminated')
            """)
            completed_sessions = [row['session_id'] for row in cursor.fetchall()]

            if not completed_sessions:
                return result

            for session_id in completed_sessions:
                # 스냅샷 다운샘플링: 각 시간대별 마지막 스냅샷만 유지
                # strftime으로 시간대 그룹을 만들고 각 그룹의 MAX(snapshot_id)만 유지
                interval_seconds = hours_interval * 3600
                cursor.execute(f"""
                    DELETE FROM portfolio_snapshots
                    WHERE session_id = ?
                    AND snapshot_id NOT IN (
                        SELECT MAX(snapshot_id)
                        FROM portfolio_snapshots
                        WHERE session_id = ?
                        GROUP BY CAST(strftime('%s', timestamp) / {interval_seconds} AS INTEGER)
                    )
                """, (session_id, session_id))
                result['snapshots_removed'] += cursor.rowcount

                # 시그널: executed=False만 삭제
                cursor.execute("""
                    DELETE FROM strategy_signals
                    WHERE session_id = ?
                    AND executed = 0
                """, (session_id,))
                result['signals_removed'] += cursor.rowcount

        return result

    def get_db_stats(self) -> Dict[str, Any]:
        """DB 통계 반환 (각 테이블 row 수, DB 파일 크기)

        Returns:
            {
                'tables': {'paper_trading_sessions': N, 'trades': N, ...},
                'file_size_bytes': N,
                'file_size_mb': N.N
            }
        """
        stats: Dict[str, Any] = {'tables': {}}

        table_names = [
            'paper_trading_sessions', 'trades', 'portfolio_snapshots',
            'strategy_signals', 'regime_history', 'llm_decisions',
            'scheduler_commands', 'pending_orders'
        ]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for table in table_names:
                try:
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                    row = cursor.fetchone()
                    stats['tables'][table] = row['cnt']
                except sqlite3.OperationalError as e:
                    logger.warning("테이블 '%s' 통계 조회 실패: %s", table, e)
                    stats['tables'][table] = 0

        # DB 파일 크기
        try:
            file_size = os.path.getsize(self.db_path)
            stats['file_size_bytes'] = file_size
            stats['file_size_mb'] = round(file_size / (1024 * 1024), 2)
        except OSError:
            stats['file_size_bytes'] = 0
            stats['file_size_mb'] = 0.0

        return stats

    def vacuum(self):
        """VACUUM 실행으로 DB 파일 크기 최적화"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("VACUUM")
        conn.close()

    def backup(self, backup_dir: str = 'data/backups') -> str:
        """DB 백업 (WAL 체크포인트 후 파일 복사)

        Args:
            backup_dir: 백업 디렉토리

        Returns:
            백업 파일 경로
        """
        import shutil

        os.makedirs(backup_dir, exist_ok=True)

        # WAL 체크포인트
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        # 파일 복사
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"paper_trading_{timestamp}.db")
        shutil.copy2(self.db_path, backup_path)

        return backup_path

    # ── Live Trading CRUD (DB-001) ──────────────────────────────────

    def create_live_session(self, session_id: str, strategy_name: str,
                            display_name: Optional[str], mode: str,
                            initial_capital: float,
                            broker_name: Optional[str] = None,
                            market_type: Optional[str] = None):
        """라이브 트레이딩 세션 생성

        Args:
            session_id: 세션 ID
            strategy_name: 전략 이름
            display_name: 표시 이름
            mode: 실행 모드 ('dry_run' | 'live')
            initial_capital: 초기 자본금
            broker_name: 브로커 이름
            market_type: 마켓 타입
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO live_trading_sessions
                (session_id, strategy_name, display_name, mode, start_time,
                 initial_capital, broker_name, market_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, strategy_name, display_name, mode,
                  datetime.now().isoformat(), initial_capital,
                  broker_name, market_type))

    def update_live_session(self, session_id: str, updates: Dict[str, Any]):
        """라이브 트레이딩 세션 업데이트

        Args:
            session_id: 세션 ID
            updates: 업데이트할 필드 딕셔너리
        """
        if not updates:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [session_id]
            cursor.execute(f"""
                UPDATE live_trading_sessions
                SET {set_clause}
                WHERE session_id = ?
            """, values)

    def get_live_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """라이브 트레이딩 세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            세션 딕셔너리 또는 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM live_trading_sessions WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def log_live_order(self, order_dict: Dict[str, Any]):
        """라이브 주문 기록

        Args:
            order_dict: 주문 딕셔너리 (컬럼 키 매칭)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO live_orders
                (internal_id, session_id, broker_order_id, symbol, side,
                 order_type, requested_amount, requested_price, filled_amount,
                 filled_price, status, reason, submitted_at, filled_at,
                 commission, slippage_pct, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_dict['internal_id'],
                order_dict['session_id'],
                order_dict.get('broker_order_id'),
                order_dict['symbol'],
                order_dict['side'],
                order_dict['order_type'],
                order_dict['requested_amount'],
                order_dict.get('requested_price'),
                order_dict.get('filled_amount', 0.0),
                order_dict.get('filled_price', 0.0),
                order_dict.get('status', 'pending'),
                order_dict.get('reason'),
                order_dict.get('submitted_at'),
                order_dict.get('filled_at'),
                order_dict.get('commission', 0.0),
                order_dict.get('slippage_pct', 0.0),
                order_dict.get('error_message'),
            ))

    def update_live_order(self, internal_id: str, updates: Dict[str, Any]):
        """라이브 주문 업데이트

        Args:
            internal_id: 내부 주문 ID
            updates: 업데이트할 필드 딕셔너리
        """
        if not updates:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [internal_id]
            cursor.execute(f"""
                UPDATE live_orders
                SET {set_clause}
                WHERE internal_id = ?
            """, values)

    def get_live_orders(self, session_id: str,
                        status: Optional[str] = None) -> List[Dict[str, Any]]:
        """라이브 주문 조회

        Args:
            session_id: 세션 ID
            status: 상태 필터 (None이면 전체)

        Returns:
            주문 딕셔너리 리스트
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT * FROM live_orders
                    WHERE session_id = ? AND status = ?
                """, (session_id, status))
            else:
                cursor.execute("""
                    SELECT * FROM live_orders
                    WHERE session_id = ?
                """, (session_id,))
            rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_live_state(self, key: str) -> Optional[str]:
        """라이브 트레이딩 상태값 조회

        Args:
            key: 상태 키

        Returns:
            값 문자열 또는 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT value FROM live_trading_state WHERE key = ? LIMIT 1
            """, (key,))
            row = cursor.fetchone()

        if row:
            return row['value']
        return None

    def set_live_state(self, key: str, value: str):
        """라이브 트레이딩 상태값 설정 (INSERT OR REPLACE)

        Args:
            key: 상태 키
            value: 상태 값
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO live_trading_state (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, datetime.now().isoformat()))
