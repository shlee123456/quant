"""
yfinance Helper for Dashboard

Yahoo Finance API를 사용하여 모든 미국 주식의 시세와 OHLCV 데이터를 조회합니다.
"""

import logging
import yfinance as yf
import pandas as pd
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def fetch_ticker_yfinance(symbol: str) -> Optional[Dict]:
    """
    yfinance로 주식 시세 조회

    Args:
        symbol: 주식 심볼 (예: 'AAPL', 'PLTR', 'SHOP')

    Returns:
        시세 정보 딕셔너리 또는 None (조회 실패 시)
        {
            'symbol': str,
            'last': float,
            'open': float,
            'high': float,
            'low': float,
            'volume': int,
            'change': float,
            'rate': float,
            'timestamp': str,
            'name': str  # 회사명
        }

    Example:
        >>> ticker = fetch_ticker_yfinance('PLTR')
        >>> if ticker:
        ...     print(f"{ticker['name']}: ${ticker['last']:.2f}")
    """
    try:
        # yfinance Ticker 객체 생성
        stock = yf.Ticker(symbol)

        # 현재 정보 조회
        info = stock.info

        # 최근 1일 데이터 조회 (현재가 포함)
        hist = stock.history(period='1d')

        if hist.empty or not info:
            return None

        # 최근 데이터 추출
        latest = hist.iloc[-1]

        # 현재가
        current_price = latest['Close']

        # 시가
        open_price = latest['Open']

        # 고가
        high_price = latest['High']

        # 저가
        low_price = latest['Low']

        # 거래량
        volume = int(latest['Volume'])

        # 전일 종가 (변동률 계산용)
        prev_close = info.get('previousClose', open_price)

        # 변동액과 변동률
        change = current_price - prev_close
        rate = (change / prev_close * 100) if prev_close > 0 else 0.0

        # 회사명
        company_name = info.get('longName', symbol)

        # 타임스탬프
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return {
            'symbol': symbol,
            'last': float(current_price),
            'open': float(open_price),
            'high': float(high_price),
            'low': float(low_price),
            'volume': volume,
            'change': float(change),
            'rate': float(rate),
            'timestamp': timestamp,
            'name': company_name
        }

    except Exception as e:
        print(f"yfinance 조회 실패 ({symbol}): {e}")
        return None


def fetch_ohlcv_yfinance(
    symbol: str,
    period: str = '1mo',
    interval: str = '1d'
) -> Optional[pd.DataFrame]:
    """
    yfinance로 OHLCV 데이터 조회

    Args:
        symbol: 주식 심볼
        period: 조회 기간 ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
        interval: 시간 간격 ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')

    Returns:
        OHLCV DataFrame 또는 None
        Columns: timestamp, open, high, low, close, volume

    Example:
        >>> df = fetch_ohlcv_yfinance('PLTR', period='1mo', interval='1d')
        >>> if df is not None:
        ...     print(df.tail())
    """
    try:
        # yfinance Ticker 객체 생성
        stock = yf.Ticker(symbol)

        # OHLCV 데이터 조회
        hist = stock.history(period=period, interval=interval)

        if hist.empty:
            return None

        # DataFrame 변환 (컬럼명 소문자로 통일)
        df = hist.reset_index()

        # 컬럼명 매핑
        column_mapping = {
            'Date': 'timestamp',
            'Datetime': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }

        # 컬럼명 변경
        df = df.rename(columns=column_mapping)

        # 필수 컬럼만 선택
        required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = df[required_columns]

        # timestamp를 datetime으로 변환
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        return df

    except Exception as e:
        print(f"yfinance OHLCV 조회 실패 ({symbol}): {e}")
        return None


def get_company_info(symbol: str) -> Optional[Dict]:
    """
    yfinance로 회사 정보 조회

    Args:
        symbol: 주식 심볼

    Returns:
        회사 정보 딕셔너리 또는 None

    Example:
        >>> info = get_company_info('PLTR')
        >>> if info:
        ...     print(f"{info['name']} - {info['sector']}")
    """
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        if not info:
            return None

        return {
            'symbol': symbol,
            'name': info.get('longName', symbol),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'exchange': info.get('exchange', 'Unknown'),
            'market_cap': info.get('marketCap', 0),
            'employees': info.get('fullTimeEmployees', 0),
            'description': info.get('longBusinessSummary', '')
        }

    except Exception as e:
        print(f"yfinance 회사 정보 조회 실패 ({symbol}): {e}")
        return None


def validate_symbol(symbol: str) -> bool:
    """
    종목 심볼 유효성 검증

    Args:
        symbol: 주식 심볼

    Returns:
        유효한 심볼이면 True, 아니면 False

    Example:
        >>> validate_symbol('AAPL')
        True
        >>> validate_symbol('INVALID123')
        False
    """
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        # info가 비어있거나 중요 필드가 없으면 유효하지 않은 심볼
        if not info or 'symbol' not in info:
            return False

        return True

    except (ValueError, KeyError, ConnectionError) as e:
        logger.warning("심볼 유효성 검증 실패 (%s): %s", symbol, e)
        return False
    except Exception as e:
        logger.warning("심볼 유효성 검증 중 예상치 못한 오류 (%s): %s", symbol, e)
        return False
