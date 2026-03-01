"""
Cryptocurrency Trading Bot - Core Trading System
"""

__version__ = "1.0.0"
__author__ = "Agent Team"

from .config import Config
from .simulation_data import SimulationDataGenerator
from .strategy import MovingAverageCrossover
from .strategies import BaseStrategy, RSIStrategy, MACDStrategy, BollingerBandsStrategy
from .backtester import Backtester
from .optimizer import StrategyOptimizer
from .notifications import (
    NotificationService,
    NotificationChannel,
    SlackWebhookChannel,
    SlackBotChannel,
    EmailChannel,
)
from .strategy_presets import StrategyPresetManager
from .custom_combo_strategy import CustomComboStrategy
from .strategy_registry import StrategyRegistry
from .signal_validator import SignalValidator
from .execution_verifier import OrderExecutionVerifier

# Phase 2 automation modules
try:
    from .database import TradingDatabase
    from .reports import ReportGenerator
    _has_automation = True
except ImportError:
    TradingDatabase = None
    ReportGenerator = None
    _has_automation = False

# VBT backtester (requires vectorbt)
try:
    from .vbt_backtester import VBTBacktester
    _has_vbt = True
except ImportError:
    VBTBacktester = None
    _has_vbt = False

# Regime detection
try:
    from .regime_detector import RegimeDetector, MarketRegime, RegimeResult
    _has_regime = True
except ImportError:
    RegimeDetector = MarketRegime = RegimeResult = None
    _has_regime = False

# LLM client
try:
    from .llm_client import LLMClient, LLMConfig
    _has_llm = True
except ImportError:
    LLMClient = LLMConfig = None
    _has_llm = False

# Market analyzer
try:
    from .market_analyzer import MarketAnalyzer
    _has_market_analyzer = True
except ImportError:
    MarketAnalyzer = None
    _has_market_analyzer = False

# News collector
try:
    from .news_collector import NewsCollector
    _has_news_collector = True
except ImportError:
    NewsCollector = None
    _has_news_collector = False

# Fear & Greed collector
try:
    from .fear_greed_collector import FearGreedCollector
    _has_fear_greed = True
except ImportError:
    FearGreedCollector = None
    _has_fear_greed = False

# Market Intelligence (5-Layer analysis)
try:
    from .market_intelligence import MarketIntelligence
    _has_market_intelligence = True
except ImportError:
    MarketIntelligence = None
    _has_market_intelligence = False

# Optional imports (require additional dependencies)
try:
    from .data_handler import DataHandler
    _has_ccxt = True
except ImportError:
    DataHandler = None
    _has_ccxt = False

try:
    from .paper_trader import PaperTrader
    from .performance_calculator import PerformanceCalculator
    from .order_executor import OrderExecutor
    from .risk_manager import RiskManager
    from .portfolio_manager import PortfolioManager
    from .signal_pipeline import SignalPipeline
    _has_paper_trader = True
except ImportError:
    PaperTrader = None
    PerformanceCalculator = None
    OrderExecutor = None
    RiskManager = None
    PortfolioManager = None
    SignalPipeline = None
    _has_paper_trader = False

__all__ = [
    'Config',
    'SimulationDataGenerator',
    'MovingAverageCrossover',
    'BaseStrategy',
    'RSIStrategy',
    'MACDStrategy',
    'BollingerBandsStrategy',
    'Backtester',
    'StrategyOptimizer',
    'NotificationService',
    'NotificationChannel',
    'SlackWebhookChannel',
    'SlackBotChannel',
    'EmailChannel',
    'StrategyPresetManager',
    'CustomComboStrategy',
    'StrategyRegistry',
    'SignalValidator',
    'OrderExecutionVerifier',
]

if _has_vbt:
    __all__.append('VBTBacktester')
if _has_ccxt:
    __all__.append('DataHandler')
if _has_paper_trader:
    __all__.extend(['PaperTrader', 'PerformanceCalculator', 'OrderExecutor', 'RiskManager', 'PortfolioManager', 'SignalPipeline'])
if _has_automation:
    __all__.extend(['TradingDatabase', 'ReportGenerator'])
if _has_regime:
    __all__.extend(['RegimeDetector', 'MarketRegime', 'RegimeResult'])
if _has_llm:
    __all__.extend(['LLMClient', 'LLMConfig'])
if _has_market_analyzer:
    __all__.append('MarketAnalyzer')
if _has_news_collector:
    __all__.append('NewsCollector')
if _has_fear_greed:
    __all__.append('FearGreedCollector')
if _has_market_intelligence:
    __all__.append('MarketIntelligence')

# Limit order system
try:
    from .limit_order import LimitOrderManager, PendingOrder
    _has_limit_order = True
except ImportError:
    LimitOrderManager = None
    PendingOrder = None
    _has_limit_order = False

if _has_limit_order:
    __all__.extend(['LimitOrderManager', 'PendingOrder'])
