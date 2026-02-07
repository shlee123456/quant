"""
Configuration management for the trading bot
"""

import os
from typing import Dict, Any
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
        }
    }

    def __init__(self, config_path: str = None):
        """
        Initialize configuration

        Args:
            config_path: Path to JSON config file (optional)
        """
        self.config = self.DEFAULT_CONFIG.copy()

        if config_path and os.path.exists(config_path):
            self.load_from_file(config_path)

    def load_from_file(self, config_path: str):
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            user_config = json.load(f)
            self.config.update(user_config)

    def save_to_file(self, config_path: str):
        """Save current configuration to JSON file"""
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
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
