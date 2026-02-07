"""
Broker Module

트레이딩 봇의 브로커 통합 모듈입니다.
다양한 브로커 (CCXT, 한국투자증권 등)를 통일된 인터페이스로 제공합니다.

Available Brokers:
    - BaseBroker: 모든 브로커의 추상 인터페이스
    - CCXTBroker: 암호화폐 거래소 브로커 (100+ 거래소 지원)
    - KoreaInvestmentBroker: 한국투자증권 브로커 (국내/해외주식)

Example:
    >>> from trading_bot.brokers import CCXTBroker, KoreaInvestmentBroker
    >>>
    >>> # 암호화폐 브로커
    >>> crypto_broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')
    >>> df = crypto_broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)
    >>>
    >>> # 주식 브로커
    >>> stock_broker = KoreaInvestmentBroker(
    ...     appkey='APPKEY',
    ...     appsecret='APPSECRET',
    ...     account='12345678-01'
    ... )
    >>> df = stock_broker.fetch_ohlcv('005930', '1d', limit=100)
"""

from .base_broker import (
    BaseBroker,
    BrokerError,
    AuthenticationError,
    InsufficientFunds,
    OrderNotFound,
    RateLimitExceeded
)

from .ccxt_broker import CCXTBroker
from .korea_investment_broker import KoreaInvestmentBroker

__all__ = [
    # Base classes
    'BaseBroker',

    # Broker implementations
    'CCXTBroker',
    'KoreaInvestmentBroker',

    # Exceptions
    'BrokerError',
    'AuthenticationError',
    'InsufficientFunds',
    'OrderNotFound',
    'RateLimitExceeded',
]

__version__ = '0.1.0'
