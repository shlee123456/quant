"""
Centralized Logging Configuration

Provides consistent logging setup across all trading bot modules.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logger(
    name: str,
    log_level: int = logging.INFO,
    log_to_file: bool = True,
    log_dir: Optional[str] = None
) -> logging.Logger:
    """
    Set up a logger with both console and file handlers.

    Args:
        name: Logger name (usually __name__ of the calling module)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file in addition to console
        log_dir: Directory for log files (defaults to .context/logs/)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(log_level)

    # Console handler - shorter format for readability
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(levelname)s - %(name)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler - detailed format with timestamps
    if log_to_file:
        if log_dir is None:
            log_dir = '.context/logs'

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime('%Y%m%d')
        log_file = log_path / f'{name.replace(".", "_")}_{timestamp}.log'

        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get or create a logger with standard configuration.

    Args:
        name: Logger name (usually __name__ of the calling module)
        level: Logging level

    Returns:
        Configured logger instance
    """
    return setup_logger(name, log_level=level)


def log_exception(logger: logging.Logger, message: str, exc_info: bool = True) -> None:
    """
    Log an exception with full stack trace.

    Args:
        logger: Logger instance
        message: Error message to log
        exc_info: Whether to include exception info (default: True)
    """
    logger.error(message, exc_info=exc_info)


# Pre-configured loggers for common modules
def get_broker_logger() -> logging.Logger:
    """Get logger for broker modules"""
    return get_logger('trading_bot.brokers', level=logging.INFO)


def get_strategy_logger() -> logging.Logger:
    """Get logger for strategy modules"""
    return get_logger('trading_bot.strategies', level=logging.INFO)


def get_backtester_logger() -> logging.Logger:
    """Get logger for backtester"""
    return get_logger('trading_bot.backtester', level=logging.INFO)


def get_optimizer_logger() -> logging.Logger:
    """Get logger for optimizer"""
    return get_logger('trading_bot.optimizer', level=logging.INFO)


def get_paper_trader_logger() -> logging.Logger:
    """Get logger for paper trader"""
    return get_logger('trading_bot.paper_trader', level=logging.INFO)


# Example usage:
if __name__ == '__main__':
    # Test logging configuration
    logger = setup_logger('test_logger', log_level=logging.DEBUG)

    logger.debug('This is a debug message')
    logger.info('This is an info message')
    logger.warning('This is a warning message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')

    # Test exception logging
    try:
        raise ValueError('Test exception')
    except ValueError:
        log_exception(logger, 'An error occurred during testing')

    print(f'\nLog files created in .context/logs/')
