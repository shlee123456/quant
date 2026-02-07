"""
CCXT Broker Implementation

CCXT 라이브러리를 사용한 암호화폐 거래소 브로커 구현입니다.
100+ 암호화폐 거래소를 단일 인터페이스로 지원합니다.

Supported Exchanges:
    - Binance, Upbit, Coinbase, Kraken, Bitfinex 등 100+ 거래소

Example:
    >>> broker = CCXTBroker('binance', api_key='YOUR_KEY', secret='YOUR_SECRET')
    >>> df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)
    >>> balance = broker.fetch_balance()
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import ccxt
from datetime import datetime

from .base_broker import (
    BaseBroker,
    BrokerError,
    AuthenticationError,
    InsufficientFunds,
    OrderNotFound,
    RateLimitExceeded
)


class CCXTBroker(BaseBroker):
    """
    CCXT 기반 암호화폐 거래소 브로커.

    Attributes:
        exchange_id (str): 거래소 ID (예: 'binance', 'upbit')
        exchange (ccxt.Exchange): CCXT 거래소 인스턴스
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        password: Optional[str] = None,
        testnet: bool = False
    ):
        """
        CCXT 브로커 초기화.

        Args:
            exchange_id: CCXT 거래소 ID (예: 'binance', 'upbit', 'coinbase')
            api_key: API 키 (선택, 공개 API만 사용 시 생략 가능)
            secret: API Secret
            password: API 비밀번호 (일부 거래소에서 필요)
            testnet: 테스트넷 사용 여부

        Raises:
            BrokerError: 거래소 초기화 실패 시

        Example:
            >>> # 공개 API만 사용 (시세 조회만)
            >>> broker = CCXTBroker('binance')
            >>> # 인증 필요한 API 사용 (주문, 잔고 조회 등)
            >>> broker = CCXTBroker('binance', api_key='KEY', secret='SECRET')
        """
        super().__init__(name=f'CCXT-{exchange_id}', market_type='crypto')

        self.exchange_id = exchange_id

        try:
            # CCXT 거래소 인스턴스 생성
            exchange_class = getattr(ccxt, exchange_id)
            config = {
                'enableRateLimit': True,  # 자동 rate limiting
            }

            if api_key and secret:
                config['apiKey'] = api_key
                config['secret'] = secret

            if password:
                config['password'] = password

            if testnet:
                config['sandbox'] = True

            self.exchange = exchange_class(config)

        except AttributeError:
            raise BrokerError(f"지원하지 않는 거래소입니다: {exchange_id}")
        except Exception as e:
            raise BrokerError(f"거래소 초기화 실패: {str(e)}")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[int] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        OHLCV 데이터 조회.

        Args:
            symbol: 거래 쌍 (예: 'BTC/USDT', 'ETH/USDT')
            timeframe: 캔들 간격 ('1m', '5m', '15m', '1h', '4h', '1d' 등)
            since: 시작 타임스탬프 (밀리초)
            limit: 최대 캔들 개수

        Returns:
            OHLCV DataFrame.

        Example:
            >>> df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)

            # pandas DataFrame으로 변환
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            return df

        except ccxt.BadSymbol as e:
            raise BrokerError(f"잘못된 심볼: {symbol}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"OHLCV 조회 실패: {str(e)}")

    def fetch_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회.

        Returns:
            잔고 딕셔너리.

        Example:
            >>> balance = broker.fetch_balance()
            >>> print(balance['total']['BTC'])
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance

        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"잔고 조회 실패: {str(e)}")

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        주문 생성.

        Args:
            symbol: 거래 쌍
            order_type: 'market' 또는 'limit'
            side: 'buy' 또는 'sell'
            amount: 수량
            price: 가격 (limit 주문 시 필수)

        Returns:
            주문 정보 딕셔너리.

        Example:
            >>> # 시장가 매수
            >>> order = broker.create_order('BTC/USDT', 'market', 'buy', 0.01)
            >>> # 지정가 매도
            >>> order = broker.create_order('BTC/USDT', 'limit', 'sell', 0.01, 50000)
        """
        try:
            order = self.exchange.create_order(symbol, order_type, side, amount, price)
            return order

        except ccxt.InsufficientFunds as e:
            raise InsufficientFunds(f"잔고 부족: {str(e)}")
        except ccxt.BadSymbol as e:
            raise BrokerError(f"잘못된 심볼: {symbol}")
        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"주문 생성 실패: {str(e)}")

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        주문 취소.

        Args:
            order_id: 주문 ID
            symbol: 거래 쌍 (일부 거래소에서 필수)

        Returns:
            취소된 주문 정보.

        Example:
            >>> result = broker.cancel_order('12345', 'BTC/USDT')
        """
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            return result

        except ccxt.OrderNotFound as e:
            raise OrderNotFound(f"주문을 찾을 수 없음: {order_id}")
        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"주문 취소 실패: {str(e)}")

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        현재가 정보 조회.

        Args:
            symbol: 거래 쌍

        Returns:
            현재가 딕셔너리.

        Example:
            >>> ticker = broker.fetch_ticker('BTC/USDT')
            >>> print(ticker['last'])
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker

        except ccxt.BadSymbol as e:
            raise BrokerError(f"잘못된 심볼: {symbol}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"현재가 조회 실패: {str(e)}")

    def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        주문 상태 조회.

        Args:
            order_id: 주문 ID
            symbol: 거래 쌍 (일부 거래소에서 필수)

        Returns:
            주문 정보.

        Example:
            >>> order = broker.fetch_order('12345', 'BTC/USDT')
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order

        except ccxt.OrderNotFound as e:
            raise OrderNotFound(f"주문을 찾을 수 없음: {order_id}")
        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"주문 조회 실패: {str(e)}")

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        미체결 주문 목록 조회.

        Args:
            symbol: 거래 쌍 (None이면 모든 거래쌍)

        Returns:
            미체결 주문 리스트.

        Example:
            >>> orders = broker.fetch_open_orders('BTC/USDT')
        """
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            return orders

        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"미체결 주문 조회 실패: {str(e)}")

    def fetch_closed_orders(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        체결 완료 주문 목록 조회.

        Args:
            symbol: 거래 쌍
            since: 시작 타임스탬프
            limit: 최대 개수

        Returns:
            체결 완료 주문 리스트.

        Example:
            >>> orders = broker.fetch_closed_orders('BTC/USDT', limit=50)
        """
        try:
            orders = self.exchange.fetch_closed_orders(symbol, since, limit)
            return orders

        except ccxt.AuthenticationError as e:
            raise AuthenticationError(f"인증 실패: {str(e)}")
        except ccxt.RateLimitExceeded as e:
            raise RateLimitExceeded(f"API 호출 제한 초과: {str(e)}")
        except Exception as e:
            raise BrokerError(f"체결 완료 주문 조회 실패: {str(e)}")
