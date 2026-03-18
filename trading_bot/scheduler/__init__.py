"""
Scheduler package - modular scheduler components

This package splits the monolithic scheduler.py into focused modules:
- scheduler_core: APScheduler setup, job registration, heartbeat, watchdog
- session_manager: Paper trading session start/stop/report
- db_maintenance: Database downsampling, cleanup, backup
"""

from trading_bot.scheduler.scheduler_state import (
    STRATEGY_CLASS_MAP,
    SchedulerContext,
    ctx,
    active_traders,
    trader_threads,
    traders_lock,
    preset_configs,
    notifier,
    preset_manager,
    scheduler_health,
    anomaly_detector,
    global_db,
    global_regime_detector,
    global_llm_client,
)
from trading_bot.scheduler.session_manager import (
    start_paper_trading,
    stop_paper_trading,
    run_market_analysis,
    run_kr_market_analysis,
    _start_single_session,
    _stop_single_session,
    _is_trading_day,
    _is_kr_trading_day,
)
from trading_bot.scheduler.db_maintenance import db_maintenance
from trading_bot.scheduler.scheduler_core import (
    signal_handler,
    _handle_status,
    _handle_stop,
    _handle_stop_all,
    _handle_cleanup,
    _validate_environment,
)

__all__ = [
    'STRATEGY_CLASS_MAP',
    'SchedulerContext',
    'ctx',
    'active_traders',
    'trader_threads',
    'traders_lock',
    'preset_configs',
    'notifier',
    'preset_manager',
    'scheduler_health',
    'anomaly_detector',
    'global_db',
    'global_regime_detector',
    'global_llm_client',
    'start_paper_trading',
    'stop_paper_trading',
    'run_market_analysis',
    'run_kr_market_analysis',
    '_start_single_session',
    '_stop_single_session',
    '_is_trading_day',
    '_is_kr_trading_day',
    'db_maintenance',
    'signal_handler',
    '_handle_status',
    '_handle_stop',
    '_handle_stop_all',
    '_handle_cleanup',
    '_validate_environment',
]
