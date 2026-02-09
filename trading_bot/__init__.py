"""
Cryptocurrency Trading Bot - Core Trading System
"""

__version__ = "1.0.0"
__author__ = "Agent Team"

from .config import Config
from .simulation_data import SimulationDataGenerator
from .strategy import MovingAverageCrossover
from .strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy
from .backtester import Backtester
from .optimizer import StrategyOptimizer
from .notifications import NotificationService
from .strategy_presets import StrategyPresetManager
from .custom_combo_strategy import CustomComboStrategy

# Optional imports (require additional dependencies)
try:
    from .data_handler import DataHandler
    _has_ccxt = True
except ImportError:
    DataHandler = None
    _has_ccxt = False

try:
    from .paper_trader import PaperTrader
    _has_paper_trader = True
except ImportError:
    PaperTrader = None
    _has_paper_trader = False

__all__ = [
    'Config',
    'SimulationDataGenerator',
    'MovingAverageCrossover',
    'RSIStrategy',
    'MACDStrategy',
    'BollingerBandsStrategy',
    'Backtester',
    'StrategyOptimizer',
    'NotificationService',
    'StrategyPresetManager',
    'CustomComboStrategy',
]

if _has_ccxt:
    __all__.append('DataHandler')
if _has_paper_trader:
    __all__.append('PaperTrader')
