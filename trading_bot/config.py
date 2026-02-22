"""
Configuration management for the trading bot
"""

import os
from typing import Any
import json


class Config:
    """Configuration class for trading bot settings"""

    # Default configuration
    DEFAULT_CONFIG = {
        'exchange': 'binance',
        'symbol': 'BTC/USDT',
        'timeframe': '1h',
        'fast_ma_period': 10,
        'slow_ma_period': 30,
        'initial_capital': 10000.0,
        'position_size': 0.95,  # Use 95% of capital per trade
        'api_key': '',
        'api_secret': '',
        'backtesting': {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        },
        'paper_trading': {
            'enabled': True,
            'log_trades': True,
            'equity_history_max_size': 5000,
        },
        'database': {
            'path': 'data/paper_trading.db',
            'busy_timeout': 5000,
        },
        'scheduler': {
            'log_file': 'logs/scheduler.log',
            'log_max_bytes': 10 * 1024 * 1024,  # 10MB
            'log_backup_count': 5,
        },
    }

    def __init__(self, config_path: str = None):
        """
        Initialize configuration

        Args:
            config_path: Path to JSON config file (optional)
        """
        self.config = self._deep_copy(self.DEFAULT_CONFIG)

        # Apply environment variable overrides
        self._apply_env_overrides()

        if config_path and os.path.exists(config_path):
            self.load_from_file(config_path)

    @staticmethod
    def _deep_copy(d: dict) -> dict:
        """Deep copy a nested dict (avoids importing copy)"""
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = Config._deep_copy(v)
            else:
                result[k] = v
        return result

    def _apply_env_overrides(self):
        """Apply environment variable overrides to config.

        Supported env vars:
            TRADING_DB_PATH         -> database.path
            TRADING_DB_BUSY_TIMEOUT -> database.busy_timeout
            SCHEDULER_LOG_FILE      -> scheduler.log_file
            SCHEDULER_LOG_MAX_BYTES -> scheduler.log_max_bytes
            SCHEDULER_LOG_BACKUP_COUNT -> scheduler.log_backup_count
            EQUITY_HISTORY_MAX_SIZE -> paper_trading.equity_history_max_size
        """
        env_map = [
            ('TRADING_DB_PATH', 'database', 'path', str),
            ('TRADING_DB_BUSY_TIMEOUT', 'database', 'busy_timeout', int),
            ('SCHEDULER_LOG_FILE', 'scheduler', 'log_file', str),
            ('SCHEDULER_LOG_MAX_BYTES', 'scheduler', 'log_max_bytes', int),
            ('SCHEDULER_LOG_BACKUP_COUNT', 'scheduler', 'log_backup_count', int),
            ('EQUITY_HISTORY_MAX_SIZE', 'paper_trading', 'equity_history_max_size', int),
        ]
        for env_var, section, key, cast in env_map:
            val = os.environ.get(env_var)
            if val is not None:
                self.config.setdefault(section, {})[key] = cast(val)

    def load_from_file(self, config_path: str):
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            user_config = json.load(f)
            self._deep_update(self.config, user_config)

    @staticmethod
    def _deep_update(base: dict, override: dict):
        """Recursively update base dict with override dict"""
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                Config._deep_update(base[k], v)
            else:
                base[k] = v

    def save_to_file(self, config_path: str):
        """Save current configuration to JSON file"""
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot-notation support.

        Examples:
            config.get('database.path')
            config.get('scheduler.log_max_bytes')
            config.get('exchange')
        """
        if '.' in key:
            parts = key.split('.', 1)
            section = self.config.get(parts[0])
            if isinstance(section, dict):
                return section.get(parts[1], default)
            return default
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.config[key] = value

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access"""
        return self.config[key]

    def __setitem__(self, key: str, value: Any):
        """Allow dictionary-style setting"""
        self.config[key] = value
