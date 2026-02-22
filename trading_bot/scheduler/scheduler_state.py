"""
Shared scheduler state - global variables and constants used across scheduler modules.

This module centralizes all mutable global state that was previously scattered
throughout the monolithic scheduler.py.
"""

import os
import threading
import logging
from typing import Dict, List, Optional

from trading_bot.strategies import (
    RSIStrategy, MACDStrategy, BollingerBandsStrategy,
    RSIMACDComboStrategy, StochasticStrategy,
)
from trading_bot.database import TradingDatabase
from trading_bot.notifications import NotificationService
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.health import SchedulerHealth
from trading_bot.anomaly_detector import AnomalyDetector

# Regime detection + LLM (optional)
try:
    from trading_bot.regime_detector import RegimeDetector
    _has_regime = True
except ImportError:
    RegimeDetector = None
    _has_regime = False

try:
    from trading_bot.llm_client import LLMClient, LLMConfig
    _has_llm = True
except ImportError:
    LLMClient = LLMConfig = None
    _has_llm = False

# Market analysis (optional)
try:
    from trading_bot.market_analyzer import MarketAnalyzer
    _has_market_analyzer = True
except ImportError:
    MarketAnalyzer = None
    _has_market_analyzer = False

logger = logging.getLogger(__name__)

# Strategy name -> class mapping
STRATEGY_CLASS_MAP = {
    'RSI Strategy': RSIStrategy,
    'MACD Strategy': MACDStrategy,
    'Bollinger Bands': BollingerBandsStrategy,
    'Stochastic': StochasticStrategy,
    'RSI+MACD Combo': RSIMACDComboStrategy,
    'RSI+MACD Combo Strategy': RSIMACDComboStrategy,
}

# Multi-session management (label -> PaperTrader)
active_traders: Dict = {}
trader_threads: Dict = {}
traders_lock = threading.Lock()

# Global notification service
notifier = NotificationService()

# Global preset manager
preset_manager = StrategyPresetManager()

# Optimized parameters (loaded from optimization)
optimized_params = None
optimized_strategy_class = None

# Global health + anomaly detector
scheduler_health = SchedulerHealth()
anomaly_detector = AnomalyDetector()

# Global DB (for command polling, zombie recovery)
global_db = TradingDatabase()

# Maximum concurrent sessions (0 = unlimited)
max_sessions = 0

# Global regime detector + LLM client (optional)
global_regime_detector = RegimeDetector() if _has_regime else None
global_llm_client = None
if _has_llm:
    _llm_config = LLMConfig(
        base_url=os.getenv('LLM_BASE_URL', 'http://192.168.45.222:8080'),
        enabled=os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes'),
    )
    global_llm_client = LLMClient(_llm_config)

# Preset configs loaded from CLI (--preset/--presets)
preset_configs: List[Dict] = []
