"""
Base Broker Interface

모든 브로커 구현체의 추상 인터페이스입니다.
CCXT (암호화폐), 키움증권 (국내주식), 한국투자증권 (국내/해외주식) 등
모든 브로커는 이 인터페이스를 구현해야 합니다.

Design:
    - 통일된 API로 다양한 브로커 지원
    - pandas DataFrame 기반 데이터 포맷
    - 에러 처리 및 타입 힌팅
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime


class BaseBroker(ABC):
    """
    모든 브로커의 추상 인터페이스.

    모든 브로커 구현체는 이 클래스를 상속하고 추상 메서드를 구현해야 합니다.

    Attributes:
        name (str): 브로커 이름 (예: 'CCXT', 'Kiwoom', 'KoreaInvestment')
        market_type (str): 시장 타입 (예: 'crypto', 'stock_kr', 'stock_global')
    """

    def __init__(self, name: str, market_type: str):
        """
        브로커 초기화.

        Args:
            name: 브로커 이름
            market_type: 시장 타입 ('crypto', 'stock_kr', 'stock_global')
        """
        self.name = name
        self.market_type = market_type

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[int] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        OHLCV (Open, High, Low, Close, Volume) 데이터 조회.

        Args:
            symbol: 거래 심볼 (예: 'BTC/USDT', '005930', 'AAPL')
            timeframe: 시간 프레임 ('1m', '5m', '1h', '1d' 등)
            since: 시작 타임스탬프 (밀리초, None이면 최근 데이터)
            limit: 조회할 최대 개수

        Returns:
            OHLCV 데이터를 담은 pandas DataFrame.
            컬럼: ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        Raises:
            BrokerError: 데이터 조회 실패 시
            ValueError: 잘못된 파라미터 입력 시

        Example:
            >>> broker = SomeBroker()
            >>> df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)
            >>> print(df.head())
                      timestamp    open    high     low   close    volume
            0 2024-01-01 00:00  42000  42100  41900  42050  1000.0
            ...
        """
        pass

    @abstractmethod
    def fetch_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회.

        Returns:
            잔고 정보를 담은 딕셔너리.
            {
                'free': 사용 가능한 자산 (Dict[str, float]),
                'used': 주문 중인 자산 (Dict[str, float]),
                'total': 총 자산 (Dict[str, float])
            }

        Raises:
            BrokerError: 잔고 조회 실패 시
            AuthenticationError: 인증 실패 시

        Example:
            >>> balance = broker.fetch_balance()
            >>> print(balance['total']['KRW'])
            1000000.0
        """
        pass

    @abstractmethod
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
            symbol: 거래 심볼
            order_type: 주문 타입 ('market', 'limit')
            side: 주문 방향 ('buy', 'sell')
            amount: 주문 수량
            price: 주문 가격 (limit 주문 시 필수)

        Returns:
            주문 정보를 담은 딕셔너리.
            {
                'id': 주문 ID (str),
                'symbol': 거래 심볼 (str),
                'type': 주문 타입 (str),
                'side': 주문 방향 (str),
                'amount': 주문 수량 (float),
                'price': 주문 가격 (float),
                'status': 주문 상태 (str, 'open'/'closed'/'canceled'),
                'timestamp': 주문 시각 (int, 밀리초)
            }

        Raises:
            BrokerError: 주문 생성 실패 시
            InsufficientFunds: 잔고 부족 시
            ValueError: 잘못된 파라미터 입력 시

        Example:
            >>> order = broker.create_order('BTC/USDT', 'limit', 'buy', 1.0, 42000)
            >>> print(order['id'])
            '12345678'
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        주문 취소.

        Args:
            order_id: 취소할 주문 ID
            symbol: 거래 심볼 (일부 브로커에서 필요)

        Returns:
            취소된 주문 정보를 담은 딕셔너리.

        Raises:
            BrokerError: 주문 취소 실패 시
            OrderNotFound: 주문을 찾을 수 없을 시

        Example:
            >>> result = broker.cancel_order('12345678', 'BTC/USDT')
            >>> print(result['status'])
            'canceled'
        """
        pass

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        현재가 정보 조회.

        Args:
            symbol: 거래 심볼

        Returns:
            현재가 정보를 담은 딕셔너리.
            {
                'symbol': 거래 심볼 (str),
                'last': 최종 체결가 (float),
                'bid': 매수 호가 (float),
                'ask': 매도 호가 (float),
                'high': 고가 (float),
                'low': 저가 (float),
                'volume': 거래량 (float),
                'timestamp': 시각 (int, 밀리초)
            }

        Raises:
            BrokerError: 조회 실패 시

        Example:
            >>> ticker = broker.fetch_ticker('BTC/USDT')
            >>> print(ticker['last'])
            42050.0
        """
        pass

    @abstractmethod
    def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        주문 상태 조회.

        Args:
            order_id: 조회할 주문 ID
            symbol: 거래 심볼 (일부 브로커에서 필요)

        Returns:
            주문 정보를 담은 딕셔너리 (create_order와 동일한 포맷).

        Raises:
            BrokerError: 조회 실패 시
            OrderNotFound: 주문을 찾을 수 없을 시

        Example:
            >>> order = broker.fetch_order('12345678', 'BTC/USDT')
            >>> print(order['status'])
            'closed'
        """
        pass

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        미체결 주문 목록 조회 (선택 구현).

        Args:
            symbol: 거래 심볼 (None이면 모든 심볼)

        Returns:
            미체결 주문 목록.

        Raises:
            NotImplementedError: 브로커가 지원하지 않을 시
        """
        raise NotImplementedError(f"{self.name} 브로커는 미체결 주문 조회를 지원하지 않습니다.")

    def fetch_closed_orders(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        체결 완료 주문 목록 조회 (선택 구현).

        Args:
            symbol: 거래 심볼 (None이면 모든 심볼)
            since: 시작 타임스탬프 (밀리초)
            limit: 조회할 최대 개수

        Returns:
            체결 완료 주문 목록.

        Raises:
            NotImplementedError: 브로커가 지원하지 않을 시
        """
        raise NotImplementedError(f"{self.name} 브로커는 체결 완료 주문 조회를 지원하지 않습니다.")

    def __repr__(self) -> str:
        """문자열 표현."""
        return f"<{self.__class__.__name__}(name='{self.name}', market_type='{self.market_type}')>"


class BrokerError(Exception):
    """브로커 관련 일반 오류."""
    pass


class AuthenticationError(BrokerError):
    """인증 실패 오류."""
    pass


class InsufficientFunds(BrokerError):
    """잔고 부족 오류."""
    pass


class OrderNotFound(BrokerError):
    """주문을 찾을 수 없음 오류."""
    pass


class RateLimitExceeded(BrokerError):
    """API 호출 제한 초과 오류."""
    pass
