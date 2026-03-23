"""
Shared scheduler state - global variables and constants used across scheduler modules.

This module centralizes all mutable global state that was previously scattered
throughout the monolithic scheduler.py. State is encapsulated in SchedulerContext
so that tests can create isolated instances.
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

try:
    from trading_bot.kr_market_analyzer import KRMarketAnalyzer
    _has_kr_market_analyzer = True
except ImportError:
    KRMarketAnalyzer = None
    _has_kr_market_analyzer = False

# Live trader (optional)
try:
    from trading_bot.live_trader import LiveTrader
    _has_live_trader = True
except ImportError:
    LiveTrader = None
    _has_live_trader = False

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


class SchedulerContext:
    """스케줄러 전역 상태를 캡슐화하는 컨텍스트 객체.

    테스트에서 독립 인스턴스를 생성하면 상태가 격리됩니다.
    """

    def __init__(self):
        self.active_traders: Dict = {}
        self.trader_threads: Dict = {}
        self.active_live_traders: Dict = {}
        self.live_trader_threads: Dict = {}
        self.traders_lock = threading.Lock()
        self.notifier = NotificationService()
        self.preset_manager = StrategyPresetManager()
        self.scheduler_health = SchedulerHealth()
        self.anomaly_detector = AnomalyDetector()
        self.global_db = TradingDatabase()
        self.max_sessions: int = 0
        self.preset_configs: List[Dict] = []
        self.global_regime_detector = RegimeDetector() if _has_regime else None
        self.global_llm_client = None
        if _has_llm:
            _llm_config = LLMConfig(
                base_url=os.getenv('LLM_BASE_URL', 'http://192.168.45.222:8080'),
                enabled=os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes'),
            )
            self.global_llm_client = LLMClient(_llm_config)
        self.global_broker = None


# Default singleton context used by the scheduler at runtime.
ctx = SchedulerContext()

# Module-level aliases for mutable objects (backward compatible).
# These point to the *same* mutable containers inside ctx, so mutations
# through either name are visible everywhere.
# NOTE: max_sessions and global_broker are reassigned (not mutated),
# so they CANNOT be aliased here — use ctx.max_sessions / ctx.global_broker.
active_traders = ctx.active_traders
trader_threads = ctx.trader_threads
active_live_traders = ctx.active_live_traders
live_trader_threads = ctx.live_trader_threads
traders_lock = ctx.traders_lock
notifier = ctx.notifier
preset_manager = ctx.preset_manager
scheduler_health = ctx.scheduler_health
anomaly_detector = ctx.anomaly_detector
global_db = ctx.global_db
preset_configs = ctx.preset_configs
global_regime_detector = ctx.global_regime_detector
global_llm_client = ctx.global_llm_client
