"""
Korea Investment Broker Implementation

한국투자증권 OpenAPI (python-kis)를 사용한 브로커 구현입니다.
국내주식 + 해외주식을 단일 API로 지원합니다.

Requirements:
    - python-kis 라이브러리 필요: pip install python-kis
    - 한국투자증권 계좌 및 API 키 필요

Supported Markets:
    - 국내주식: 코스피, 코스닥, 코넥스
    - 해외주식: 미국 (NYSE, NASDAQ), 홍콩, 일본, 중국 등

Example:
    >>> broker = KoreaInvestmentBroker(
    ...     appkey='YOUR_APPKEY',
    ...     appsecret='YOUR_APPSECRET',
    ...     account='12345678-01'
    ... )
    >>> # user_id를 명시할 수도 있음
    >>> broker = KoreaInvestmentBroker(
    ...     appkey='YOUR_APPKEY',
    ...     appsecret='YOUR_APPSECRET',
    ...     account='12345678-01',
    ...     user_id='@1234567'
    ... )
    >>> # 국내주식 조회
    >>> df = broker.fetch_ohlcv('005930', '1d', limit=100)  # 삼성전자
    >>> # 해외주식 조회
    >>> df_us = broker.fetch_ohlcv('AAPL', '1d', limit=100, overseas=True)
"""

from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime, timedelta
import time

from .base_broker import (
    BaseBroker,
    BrokerError,
    AuthenticationError,
    InsufficientFunds,
    OrderNotFound,
    RateLimitExceeded
)
from ..logging_config import get_broker_logger, log_exception

logger = get_broker_logger()


class KoreaInvestmentBroker(BaseBroker):
    """
    한국투자증권 브로커 (국내/해외주식).

    python-kis 라이브러리를 사용하여 한국투자증권 OpenAPI에 접근합니다.

    Attributes:
        appkey (str): 한국투자증권 AppKey
        appsecret (str): 한국투자증권 AppSecret
        account (str): 계좌번호 (예: '12345678-01')
        api: python-kis 라이브러리 API 인스턴스
    """

    def __init__(
        self,
        appkey: str,
        appsecret: str,
        account: str,
        user_id: Optional[str] = None,
        mock: bool = False
    ):
        """
        한국투자증권 브로커 초기화.

        Args:
            appkey: 한국투자증권 AppKey
            appsecret: 한국투자증권 AppSecret
            account: 계좌번호 (예: '12345678-01')
            user_id: 한국투자증권 사용자 ID (기본: account 값 사용)
            mock: 모의투자 계좌 사용 여부 (기본: False)

        Raises:
            BrokerError: 초기화 실패 시
            AuthenticationError: 인증 실패 시

        Example:
            >>> # 실전 계좌 (user_id 생략)
            >>> broker = KoreaInvestmentBroker(
            ...     appkey='YOUR_APPKEY',
            ...     appsecret='YOUR_APPSECRET',
            ...     account='12345678-01'
            ... )
            >>> # 실전 계좌 (user_id 명시)
            >>> broker = KoreaInvestmentBroker(
            ...     appkey='YOUR_APPKEY',
            ...     appsecret='YOUR_APPSECRET',
            ...     account='12345678-01',
            ...     user_id='@1234567'
            ... )
            >>> # 모의투자 계좌
            >>> broker = KoreaInvestmentBroker(
            ...     appkey='YOUR_APPKEY',
            ...     appsecret='YOUR_APPSECRET',
            ...     account='12345678-01',
            ...     mock=True
            ... )
        """
        super().__init__(name='KoreaInvestment', market_type='stock_global')

        self.user_id = user_id if user_id is not None else account
        self.appkey = appkey
        self.appsecret = appsecret
        self.account = account
        self.mock = mock

        logger.info(f"Initializing Korea Investment Broker - Account: {account}, Mock: {mock}")

        try:
            # python-kis 라이브러리 임포트 (지연 로딩)
            from pykis import PyKis

            # PyKis 객체 생성 (실전과 모의투자 설정 모두 제공)
            self.api = PyKis(
                id=self.user_id,
                appkey=appkey,
                secretkey=appsecret,
                virtual_id=self.user_id,
                virtual_appkey=appkey,
                virtual_secretkey=appsecret,
                account=account
            )

            # Rate Limiter 초기화 (1초당 15회)
            self._rate_limiter = RateLimiter(max_calls=15, period=1.0)

        except ImportError:
            logger.error("python-kis library not found")
            raise BrokerError(
                "python-kis 라이브러리가 설치되지 않았습니다. "
                "'pip install python-kis'를 실행하세요."
            )
        except Exception as e:
            error_msg = str(e)

            # Rate limit 에러 감지 (EGW00133: 1분당 1회 제한)
            if "EGW00133" in error_msg or "1분당 1회" in error_msg:
                logger.warning(f"Rate limit exceeded during authentication: {error_msg}")
                raise AuthenticationError(
                    "한국투자증권 토큰 발급 제한 초과: 1분에 1회만 허용됩니다. "
                    "잠시 후 다시 시도해주세요. (에러 코드: EGW00133)"
                )

            log_exception(logger, f"Authentication failed: {error_msg}")
            raise AuthenticationError(f"한국투자증권 인증 실패: {error_msg}")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[int] = None,
        limit: int = 100,
        overseas: bool = False,
        market: str = 'NASDAQ'
    ) -> pd.DataFrame:
        """
        OHLCV 데이터 조회.

        Args:
            symbol: 종목 코드
                    - 국내: '005930' (삼성전자), '035720' (카카오) 등
                    - 해외: 'AAPL', 'TSLA', 'GOOGL' 등
            timeframe: 시간 프레임
                      - 'D' 또는 '1d': 일봉
                      - '1' 또는 '1m': 1분봉 (당일만)
            since: 시작 타임스탬프 (밀리초) 또는 datetime 객체
            limit: 조회할 최대 개수
            overseas: 해외주식 여부 (기본: False)
            market: 해외주식 마켓 (NASDAQ, NYSE, AMEX 등)

        Returns:
            OHLCV DataFrame.

        Example:
            >>> # 국내주식 일봉
            >>> df = broker.fetch_ohlcv('005930', '1d', limit=100)
            >>> # 미국주식 일봉
            >>> df = broker.fetch_ohlcv('AAPL', '1d', limit=100, overseas=True)
            >>> # 특정 날짜부터 조회
            >>> from datetime import datetime
            >>> df = broker.fetch_ohlcv('AAPL', '1d', since=datetime(2024,1,1), limit=100, overseas=True)
        """
        self._rate_limiter.wait()

        try:
            # 주식 객체 생성
            if overseas:
                stock = self.api.stock(symbol, market=market)
            else:
                stock = self.api.stock(symbol)

            # since를 datetime으로 변환 (타임스탬프인 경우)
            start_date = None
            if since is not None:
                if isinstance(since, int):
                    # 밀리초 타임스탬프를 datetime으로 변환
                    start_date = datetime.fromtimestamp(since / 1000).date()
                elif isinstance(since, datetime):
                    start_date = since.date()
                elif hasattr(since, 'date'):
                    # pandas Timestamp 등
                    start_date = since.date()

            # limit 기반으로 기간 계산 (python-kis는 count 대신 기간 표현식 사용)
            # timeframe에 따라 기간 표현식 생성
            if timeframe in ['1d', 'D']:
                period_type = "day"
                
                # start_date가 지정된 경우 end_date 계산
                if start_date:
                    end_date = start_date + timedelta(days=limit)
                    # start/end 방식으로 조회
                    chart = stock.chart(start=start_date, end=end_date, period=period_type)
                else:
                    # 기간 표현식 사용
                    period_expr = f"{limit}d"
                    chart = stock.chart(period_expr, period=period_type)
                    
            elif timeframe in ['1h']:
                # 시간봉: python-kis는 시간봉 미지원, 일봉으로 대체
                period_type = "day"
                if start_date:
                    end_date = start_date + timedelta(days=limit)
                    chart = stock.chart(start=start_date, end=end_date, period=period_type)
                else:
                    period_expr = f"{limit}d"
                    chart = stock.chart(period_expr, period=period_type)
                    
            elif timeframe in ['1m', '1']:
                # 분봉: 당일 분봉만 가능
                period_type = 1  # 1분봉
                chart = stock.chart(period=period_type)
            else:
                # 기본값: 일봉
                period_type = "day"
                if start_date:
                    end_date = start_date + timedelta(days=limit)
                    chart = stock.chart(start=start_date, end=end_date, period=period_type)
                else:
                    period_expr = f"{limit}d"
                    chart = stock.chart(period_expr, period=period_type)

            # KisChart 객체를 DataFrame으로 변환
            df = chart.df()
            
            # DataFrame으로 변환
            return self._format_ohlcv(df)

        except Exception as e:
            raise BrokerError(f"OHLCV 조회 실패: {str(e)}")

    def fetch_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회.

        Returns:
            잔고 딕셔너리.

        Example:
            >>> balance = broker.fetch_balance()
            >>> print(balance['total']['KRW'])
        """
        self._rate_limiter.wait()

        try:
            # 계좌 정보 조회
            account = self.api.account(self.account)
            balance = account.balance()

            # 표준 포맷으로 변환
            # balance 객체의 속성: cash (현금), total_value (총 평가금액) 등
            cash = float(getattr(balance, 'cash', 0))
            total_value = float(getattr(balance, 'total_value', 0))
            used = total_value - cash

            return {
                'free': {'KRW': cash, 'USD': 0.0},
                'used': {'KRW': used, 'USD': 0.0},
                'total': {'KRW': total_value, 'USD': 0.0}
            }

        except Exception as e:
            raise BrokerError(f"잔고 조회 실패: {str(e)}")

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        overseas: bool = False,
        market: str = 'NASDAQ'
    ) -> Dict[str, Any]:
        """
        주문 생성.

        Args:
            symbol: 종목 코드
            order_type: 'market' 또는 'limit'
            side: 'buy' 또는 'sell'
            amount: 주문 수량
            price: 주문 가격 (limit 주문 시 필수)
            overseas: 해외주식 여부
            market: 해외주식 마켓 (NASDAQ, NYSE, AMEX 등)

        Returns:
            주문 정보 딕셔너리.

        Example:
            >>> # 국내주식 시장가 매수
            >>> order = broker.create_order('005930', 'market', 'buy', 10)
            >>> # 미국주식 지정가 매수
            >>> order = broker.create_order('AAPL', 'limit', 'buy', 5, 150.0, overseas=True)
        """
        self._rate_limiter.wait()

        try:
            # 주식 객체 생성
            if overseas:
                stock = self.api.stock(symbol, market=market)
            else:
                stock = self.api.stock(symbol)

            # 주문 수량 (정수로 변환)
            qty = int(amount)

            # 주문 실행
            if side == 'buy':
                if order_type == 'market':
                    # 시장가 매수
                    result = stock.buy(qty=qty, price=None)
                else:
                    # 지정가 매수
                    if price is None:
                        raise BrokerError("limit 주문 시 price는 필수입니다.")
                    result = stock.buy(qty=qty, price=price)
            else:  # sell
                if order_type == 'market':
                    # 시장가 매도
                    result = stock.sell(qty=qty, price=None)
                else:
                    # 지정가 매도
                    if price is None:
                        raise BrokerError("limit 주문 시 price는 필수입니다.")
                    result = stock.sell(qty=qty, price=price)

            # 표준 포맷으로 변환
            return self._format_order(result, symbol, order_type, side, amount, price)

        except Exception as e:
            # 잔고 부족 에러 감지
            if '잔고부족' in str(e) or 'insufficient' in str(e).lower():
                raise InsufficientFunds(f"잔고 부족: {str(e)}")
            raise BrokerError(f"주문 생성 실패: {str(e)}")

    def cancel_order(
        self,
        order_id: str,
        symbol: Optional[str] = None,
        overseas: bool = False,
        market: str = 'NASDAQ'
    ) -> Dict[str, Any]:
        """
        주문 취소.

        Args:
            order_id: 주문 번호
            symbol: 종목 코드 (필수)
            overseas: 해외주식 여부
            market: 해외주식 마켓

        Returns:
            취소된 주문 정보.

        Example:
            >>> result = broker.cancel_order('12345678', '005930')
        """
        self._rate_limiter.wait()

        if symbol is None:
            raise BrokerError("cancel_order에서 symbol은 필수입니다.")

        try:
            # 주식 객체 생성
            if overseas:
                stock = self.api.stock(symbol, market=market)
            else:
                stock = self.api.stock(symbol)

            # 주문 취소
            result = stock.cancel(order_id)

            return {
                'id': order_id,
                'symbol': symbol,
                'status': 'canceled',
                'timestamp': int(datetime.now().timestamp() * 1000),
                'info': result
            }

        except Exception as e:
            if '주문번호' in str(e) or 'not found' in str(e).lower():
                raise OrderNotFound(f"주문을 찾을 수 없음: {order_id}")
            raise BrokerError(f"주문 취소 실패: {str(e)}")

    def fetch_ticker(self, symbol: str, overseas: bool = False, market: str = 'NASDAQ') -> Dict[str, Any]:
        """
        현재가 정보 조회.

        Args:
            symbol: 종목 코드
            overseas: 해외주식 여부
            market: 해외주식 마켓 (NASDAQ, NYSE, AMEX 등)

        Returns:
            현재가 딕셔너리.

        Example:
            >>> ticker = broker.fetch_ticker('005930')
            >>> print(ticker['last'])
            >>> ticker = broker.fetch_ticker('AAPL', overseas=True, market='NASDAQ')
        """
        self._rate_limiter.wait()

        try:
            # 해외주식인 경우
            if overseas:
                stock = self.api.stock(symbol, market=market)
            else:
                # 국내주식
                stock = self.api.stock(symbol)

            quote = stock.quote()

            return {
                'symbol': symbol,
                'last': float(quote.price),
                'open': float(quote.open),
                'high': float(quote.high),
                'low': float(quote.low),
                'volume': float(quote.volume),
                'change': float(quote.change),
                'rate': float(quote.rate),
                'timestamp': int(datetime.now().timestamp() * 1000)
            }

        except Exception as e:
            raise BrokerError(f"현재가 조회 실패: {str(e)}")

    def fetch_order(
        self,
        order_id: str,
        symbol: Optional[str] = None,
        overseas: bool = False,
        market: str = 'NASDAQ'
    ) -> Dict[str, Any]:
        """
        주문 상태 조회.

        Args:
            order_id: 주문 번호
            symbol: 종목 코드
            overseas: 해외주식 여부
            market: 해외주식 마켓

        Returns:
            주문 정보.

        Example:
            >>> order = broker.fetch_order('12345678', '005930')
        """
        self._rate_limiter.wait()

        if symbol is None:
            raise BrokerError("fetch_order에서 symbol은 필수입니다.")

        try:
            # 주식 객체 생성
            if overseas:
                stock = self.api.stock(symbol, market=market)
            else:
                stock = self.api.stock(symbol)

            # 주문 조회
            order = stock.order(order_id)

            # 표준 포맷으로 변환
            return {
                'id': order_id,
                'symbol': symbol,
                'type': getattr(order, 'order_type', 'unknown'),
                'side': getattr(order, 'side', 'unknown'),
                'amount': float(getattr(order, 'qty', 0)),
                'price': float(getattr(order, 'price', 0)),
                'status': getattr(order, 'status', 'unknown'),
                'timestamp': int(datetime.now().timestamp() * 1000),
                'info': order
            }

        except Exception as e:
            if '주문번호' in str(e) or 'not found' in str(e).lower():
                raise OrderNotFound(f"주문을 찾을 수 없음: {order_id}")
            raise BrokerError(f"주문 조회 실패: {str(e)}")

    def _format_ohlcv(self, data: Any) -> pd.DataFrame:
        """
        한국투자증권 API 응답을 표준 OHLCV DataFrame으로 변환.

        Args:
            data: 한국투자증권 API 응답 데이터 (DataFrame 또는 list)

        Returns:
            표준 포맷의 OHLCV DataFrame.
        """
        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            # 빈 DataFrame 반환
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # DataFrame으로 변환 (이미 DataFrame이면 그대로 사용)
        if not isinstance(data, pd.DataFrame):
            df = pd.DataFrame(data)
        else:
            df = data.copy()

        # 컬럼 매핑 (PyKis 컬럼명 -> 표준 컬럼명)
        # PyKis는 일반적으로 'date', 'open', 'high', 'low', 'close', 'volume' 컬럼 사용
        column_map = {
            'date': 'timestamp',
            'stck_bsop_date': 'timestamp',  # 국내주식 일자
            'stck_clpr': 'close',            # 국내주식 종가
            'stck_oprc': 'open',             # 국내주식 시가
            'stck_hgpr': 'high',             # 국내주식 고가
            'stck_lwpr': 'low',              # 국내주식 저가
            'acml_vol': 'volume'             # 국내주식 거래량
        }

        # 컬럼 이름 변경
        for old_col, new_col in column_map.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})

        # 필수 컬럼 확인
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            # 컬럼이 없으면 기본값 추가 (단, timestamp는 필수)
            if 'timestamp' in missing_cols:
                raise BrokerError(f"OHLCV 데이터에 timestamp 컬럼이 없습니다. 컬럼: {df.columns.tolist()}")

            for col in missing_cols:
                if col in ['open', 'high', 'low', 'close']:
                    df[col] = 0.0
                elif col == 'volume':
                    df[col] = 0

        # timestamp 변환 (문자열 -> Unix timestamp in milliseconds)
        if df['timestamp'].dtype == 'object' or df['timestamp'].dtype == 'string':
            # 날짜 문자열을 datetime으로 변환
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        if df['timestamp'].dtype == 'datetime64[ns]':
            # datetime -> Unix timestamp (milliseconds)
            df['timestamp'] = (df['timestamp'].astype(int) // 10**6).astype(int)

        # 데이터 타입 변환
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # 필수 컬럼만 선택
        df = df[required_cols]

        # 인덱스 리셋
        df = df.reset_index(drop=True)

        return df

    def _format_order(
        self,
        data: Any,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float]
    ) -> Dict[str, Any]:
        """
        한국투자증권 API 주문 응답을 표준 포맷으로 변환.

        Args:
            data: 한국투자증권 API 주문 응답
            symbol: 종목 코드
            order_type: 주문 타입
            side: 주문 방향
            amount: 주문 수량
            price: 주문 가격

        Returns:
            표준 포맷의 주문 딕셔너리.
        """
        # PyKis 주문 응답에서 주문 번호 추출
        order_id = getattr(data, 'order_id', None) or getattr(data, 'odno', None) or 'unknown'

        return {
            'id': str(order_id),
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': amount,
            'price': price,
            'status': 'open',  # 기본값: open
            'timestamp': int(datetime.now().timestamp() * 1000),
            'info': data  # 원본 데이터 보존
        }


class RateLimiter:
    """
    API 호출 제한을 관리하는 Rate Limiter.

    한국투자증권 API는 1초당 15회 제한이 있으므로,
    슬라이딩 윈도우 방식으로 호출 제한을 관리합니다.
    """

    def __init__(self, max_calls: int = 15, period: float = 1.0):
        """
        Rate Limiter 초기화.

        Args:
            max_calls: 최대 호출 횟수 (기본: 15)
            period: 기간 (초, 기본: 1.0)
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []

    def wait(self):
        """
        API 호출 전 대기 (필요 시).

        호출 제한을 초과할 경우 자동으로 대기합니다.
        """
        now = time.time()

        # 기간 이전의 호출 기록 제거
        self.calls = [call_time for call_time in self.calls if call_time > now - self.period]

        # 호출 제한 초과 시 대기
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        # 현재 호출 기록 추가
        self.calls.append(time.time())
