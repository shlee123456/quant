# Brokers Module - Developer Guide

브로커 모듈은 트레이딩 봇과 다양한 거래소/증권사를 연결하는 통합 인터페이스입니다.

---

## ⚠️ 필수 실행 규칙

> **루트 CLAUDE.md의 규칙을 준수합니다.**

### 이 모듈에서 특히 중요한 규칙
1. **터미널 로그 기록**: 브로커 테스트 실행 시 `.context/terminal/broker_test_$(date +%s).log`에 저장
2. **Git 커밋**: 한글 메시지 사용, `Co-Authored-By` 태그 금지
3. **타입 힌트**: 모든 public 메서드에 타입 힌트 필수
4. **Docstring**: Google 스타일 docstring 작성

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────┐
│           Trading Strategy Layer                 │
│     (RSI, MACD, MA Crossover 등)                 │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│          BaseBroker (추상 인터페이스)             │
│  - fetch_ohlcv()     : OHLCV 데이터 조회         │
│  - fetch_balance()   : 잔고 조회                 │
│  - create_order()    : 주문 생성                 │
│  - cancel_order()    : 주문 취소                 │
│  - fetch_ticker()    : 현재가 조회               │
│  - fetch_order()     : 주문 상태 조회            │
└─────────────────────────────────────────────────┘
                      ↓
        ┌──────────────┬──────────────────────────┐
        │              │                          │
┌───────▼──────┐ ┌────▼──────────────────┐ ┌─────▼──────┐
│CCXTBroker    │ │KoreaInvestmentBroker  │ │Future      │
│(암호화폐)     │ │(국내+해외주식)         │ │Brokers     │
└──────────────┘ └───────────────────────┘ └────────────┘
```

---

## 파일 구조

```
trading_bot/brokers/
├── __init__.py                    # 모듈 초기화 및 Export
├── base_broker.py                 # 추상 인터페이스 및 예외 정의
├── ccxt_broker.py                 # CCXT 암호화폐 브로커
├── korea_investment_broker.py     # 한국투자증권 브로커
└── CLAUDE.md                      # 이 문서
```

---

## 1. BaseBroker (추상 인터페이스)

### 1.1 설계 원칙

- **통일된 API**: 모든 브로커가 동일한 메서드 시그니처 사용
- **pandas 기반**: 데이터는 pandas DataFrame으로 반환
- **명확한 에러 처리**: 커스텀 예외 클래스 사용
- **타입 안전성**: 모든 메서드에 타입 힌트

### 1.2 필수 구현 메서드

모든 브로커 구현체는 다음 메서드를 **반드시** 구현해야 합니다:

#### `fetch_ohlcv(symbol, timeframe, since, limit) -> pd.DataFrame`
- OHLCV 데이터 조회
- 반환: `['timestamp', 'open', 'high', 'low', 'close', 'volume']` 컬럼을 가진 DataFrame

#### `fetch_balance() -> Dict[str, Any]`
- 계좌 잔고 조회
- 반환: `{'free': {...}, 'used': {...}, 'total': {...}}` 형식

#### `create_order(symbol, order_type, side, amount, price) -> Dict[str, Any]`
- 주문 생성
- 반환: 주문 정보 딕셔너리 (`id`, `symbol`, `type`, `side`, `amount`, `price`, `status`, `timestamp`)

#### `cancel_order(order_id, symbol) -> Dict[str, Any]`
- 주문 취소
- 반환: 취소된 주문 정보

#### `fetch_ticker(symbol) -> Dict[str, Any]`
- 현재가 정보 조회
- 반환: `{'symbol', 'last', 'bid', 'ask', 'high', 'low', 'volume', 'timestamp'}` 형식

#### `fetch_order(order_id, symbol) -> Dict[str, Any]`
- 주문 상태 조회
- 반환: 주문 정보 딕셔너리

### 1.3 선택 구현 메서드

다음 메서드는 선택적으로 구현할 수 있습니다 (기본: `NotImplementedError` 발생):

- `fetch_open_orders(symbol) -> List[Dict]`: 미체결 주문 목록
- `fetch_closed_orders(symbol, since, limit) -> List[Dict]`: 체결 완료 주문 목록

### 1.4 예외 클래스

브로커 모듈은 다음 예외 클래스를 정의합니다:

| 예외 클래스 | 설명 | 사용 상황 |
|------------|------|----------|
| `BrokerError` | 일반적인 브로커 오류 | API 호출 실패, 네트워크 오류 등 |
| `AuthenticationError` | 인증 실패 | API 키 오류, 토큰 만료 등 |
| `InsufficientFunds` | 잔고 부족 | 주문 시 자금 부족 |
| `OrderNotFound` | 주문을 찾을 수 없음 | 존재하지 않는 주문 ID 조회 |
| `RateLimitExceeded` | API 호출 제한 초과 | Rate limit 위반 |

**사용 예제**:
```python
try:
    broker.create_order('BTC/USDT', 'market', 'buy', 1.0)
except InsufficientFunds as e:
    print(f"잔고 부족: {e}")
except BrokerError as e:
    print(f"브로커 오류: {e}")
```

---

## 2. CCXTBroker (암호화폐)

### 2.1 개요

CCXT 라이브러리를 사용하여 100+ 암호화폐 거래소를 지원합니다.

**지원 거래소 예시**:
- Binance, Upbit, Coinbase, Kraken, Bitfinex, OKX, Bybit 등

### 2.2 초기화

```python
from trading_bot.brokers import CCXTBroker

# 공개 API만 사용 (시세 조회)
broker = CCXTBroker('binance')

# 인증 API 사용 (주문, 잔고 조회)
broker = CCXTBroker(
    exchange_id='binance',
    api_key='YOUR_API_KEY',
    secret='YOUR_API_SECRET'
)

# 테스트넷 사용
broker = CCXTBroker(
    exchange_id='binance',
    api_key='YOUR_API_KEY',
    secret='YOUR_API_SECRET',
    testnet=True
)
```

### 2.3 주요 기능

#### OHLCV 조회
```python
# 비트코인 1시간봉 100개 조회
df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)

# 특정 시점부터 조회
since = int(datetime(2024, 1, 1).timestamp() * 1000)
df = broker.fetch_ohlcv('BTC/USDT', '1d', since=since, limit=365)
```

#### 주문 생성
```python
# 시장가 매수
order = broker.create_order('BTC/USDT', 'market', 'buy', 0.01)

# 지정가 매도
order = broker.create_order('BTC/USDT', 'limit', 'sell', 0.01, 50000)
```

### 2.4 주의사항

- **Rate Limit**: 거래소별로 호출 제한이 다름 (enableRateLimit=True로 자동 관리)
- **심볼 포맷**: 'BTC/USDT', 'ETH/USDT' 형식 사용 (거래소별 차이 있음)
- **API 키 권한**: 주문 실행 시 거래 권한이 있는 API 키 필요

---

## 3. KoreaInvestmentBroker (국내/해외주식)

### 3.1 개요

한국투자증권 OpenAPI (python-kis)를 사용하여 국내주식 + 해외주식을 지원합니다.

**지원 시장**:
- 국내: 코스피, 코스닥, 코넥스
- 해외: 미국 (NYSE, NASDAQ), 홍콩, 일본, 중국 등

### 3.2 초기화

```python
from trading_bot.brokers import KoreaInvestmentBroker

# 실전 계좌
broker = KoreaInvestmentBroker(
    appkey='YOUR_APPKEY',
    appsecret='YOUR_APPSECRET',
    account='12345678-01'
)

# 모의투자 계좌
broker = KoreaInvestmentBroker(
    appkey='YOUR_APPKEY',
    appsecret='YOUR_APPSECRET',
    account='12345678-01',
    mock=True
)
```

### 3.3 주요 기능

#### 국내주식 OHLCV 조회
```python
# 삼성전자 일봉 100개
df = broker.fetch_ohlcv('005930', '1d', limit=100)

# 카카오 분봉 (당일만)
df = broker.fetch_ohlcv('035720', '1m', limit=60)
```

#### 해외주식 OHLCV 조회
```python
# 애플 일봉
df = broker.fetch_ohlcv('AAPL', '1d', limit=100, overseas=True)

# 테슬라 일봉
df = broker.fetch_ohlcv('TSLA', '1d', limit=100, overseas=True)
```

#### 주문 생성
```python
# 국내주식 시장가 매수 (삼성전자 10주)
order = broker.create_order('005930', 'market', 'buy', 10)

# 미국주식 지정가 매수 (애플 5주, $150)
order = broker.create_order('AAPL', 'limit', 'buy', 5, 150.0, overseas=True)
```

### 3.4 Rate Limiting

한국투자증권 API는 **1초당 15회** 호출 제한이 있습니다.

`KoreaInvestmentBroker`는 내부적으로 `RateLimiter` 클래스를 사용하여 자동으로 호출 제한을 관리합니다.

**동작 방식**:
- 슬라이딩 윈도우 방식
- 1초당 15회 초과 시 자동 대기
- 호출 기록 자동 관리

**커스텀 설정**:
```python
# RateLimiter 인스턴스는 broker._rate_limiter로 접근 가능
# 필요 시 max_calls, period 조정 가능
```

### 3.5 주의사항

- **분봉 데이터**: 당일만 조회 가능 (키움증권 160일 대비 제약)
- **심볼 포맷**: 국내 '005930', 해외 'AAPL' (거래소 구분 없음)
- **해외주식 시간**: 미국은 한국시간 23:30~06:00 (썸머타임: 22:30~05:00)
- **python-kis 설치 필요**: `pip install python-kis`

---

## 4. 새 브로커 추가하기

새로운 브로커를 추가하려면 다음 단계를 따르세요.

### Step 1: 브로커 클래스 작성

`trading_bot/brokers/my_broker.py` 파일 생성:

```python
from typing import Dict, Optional, Any
import pandas as pd

from .base_broker import BaseBroker, BrokerError

class MyBroker(BaseBroker):
    """
    내 브로커 구현.

    Attributes:
        api_key (str): API 키
        api_secret (str): API Secret
    """

    def __init__(self, api_key: str, api_secret: str):
        super().__init__(name='MyBroker', market_type='stock_kr')

        self.api_key = api_key
        self.api_secret = api_secret

        # 초기화 로직

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[int] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """OHLCV 조회 구현"""
        # 구현 로직
        pass

    # 나머지 추상 메서드 구현...
```

### Step 2: `__init__.py`에 추가

`trading_bot/brokers/__init__.py`:

```python
from .my_broker import MyBroker

__all__ = [
    # ...
    'MyBroker',
]
```

### Step 3: 테스트 작성

`tests/test_my_broker.py`:

```python
import pytest
from trading_bot.brokers import MyBroker

def test_my_broker_fetch_ohlcv():
    broker = MyBroker(api_key='TEST_KEY', api_secret='TEST_SECRET')
    df = broker.fetch_ohlcv('TEST_SYMBOL', '1d', limit=10)
    assert not df.empty
    assert len(df) == 10
```

### Step 4: 문서 업데이트

이 `CLAUDE.md` 파일에 새 브로커 섹션 추가.

---

## 5. 테스트 가이드

### 5.1 단위 테스트

각 브로커의 메서드를 개별적으로 테스트합니다.

```bash
# 특정 브로커 테스트
pytest tests/test_ccxt_broker.py -v

# 모든 브로커 테스트
pytest tests/test_brokers.py -v
```

### 5.2 통합 테스트

전략과 브로커를 연동하여 테스트합니다.

```bash
pytest tests/integration/test_strategy_broker.py -v
```

### 5.3 모의투자 테스트

실제 API를 사용하여 모의투자 환경에서 테스트합니다.

```python
# 한국투자증권 모의투자
broker = KoreaInvestmentBroker(
    appkey='YOUR_APPKEY',
    appsecret='YOUR_APPSECRET',
    account='12345678-01',
    mock=True  # 모의투자 활성화
)

# CCXT 테스트넷
broker = CCXTBroker(
    exchange_id='binance',
    api_key='YOUR_KEY',
    secret='YOUR_SECRET',
    testnet=True  # 테스트넷 활성화
)
```

### 5.4 Mock 테스트

외부 API 호출 없이 Mock 객체로 테스트합니다.

```python
from unittest.mock import Mock, patch

@patch('ccxt.binance')
def test_ccxt_broker_mock(mock_binance):
    mock_exchange = Mock()
    mock_exchange.fetch_ohlcv.return_value = [
        [1609459200000, 29000, 29500, 28500, 29200, 1000]
    ]
    mock_binance.return_value = mock_exchange

    broker = CCXTBroker('binance')
    df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=1)

    assert not df.empty
    assert df.iloc[0]['close'] == 29200
```

---

## 6. 에러 처리 가이드

### 6.1 에러 처리 원칙

- **구체적인 예외 사용**: `BrokerError` 보다 `InsufficientFunds`, `AuthenticationError` 등 구체적인 예외 사용
- **에러 메시지 명확화**: 사용자가 문제를 파악할 수 있도록 상세한 메시지 제공
- **원인 보존**: `raise ... from e` 패턴으로 원래 예외 보존

### 6.2 에러 처리 예제

```python
def create_order(self, symbol, order_type, side, amount, price=None):
    try:
        # API 호출
        result = self.api.create_order(...)
        return result

    except SomeAPIException as e:
        # 구체적인 예외로 변환
        if 'insufficient' in str(e).lower():
            raise InsufficientFunds(f"잔고 부족: {str(e)}") from e
        elif 'authentication' in str(e).lower():
            raise AuthenticationError(f"인증 실패: {str(e)}") from e
        elif 'rate limit' in str(e).lower():
            raise RateLimitExceeded(f"호출 제한 초과: {str(e)}") from e
        else:
            raise BrokerError(f"주문 생성 실패: {str(e)}") from e
```

### 6.3 호출 측 에러 처리

```python
from trading_bot.brokers import (
    KoreaInvestmentBroker,
    InsufficientFunds,
    AuthenticationError,
    RateLimitExceeded,
    BrokerError
)

broker = KoreaInvestmentBroker(...)

try:
    order = broker.create_order('005930', 'market', 'buy', 10)
    print(f"주문 성공: {order['id']}")

except InsufficientFunds:
    print("잔고가 부족합니다.")
except AuthenticationError:
    print("API 키를 확인하세요.")
except RateLimitExceeded:
    print("API 호출 제한 초과. 잠시 후 다시 시도하세요.")
except BrokerError as e:
    print(f"브로커 오류: {e}")
```

---

## 7. 코딩 컨벤션

### 7.1 네이밍

- **클래스**: `PascalCase` (예: `CCXTBroker`, `KoreaInvestmentBroker`)
- **메서드**: `snake_case` (예: `fetch_ohlcv`, `create_order`)
- **상수**: `UPPER_CASE` (예: `MAX_RETRIES`, `DEFAULT_TIMEOUT`)

### 7.2 타입 힌트

모든 public 메서드에 타입 힌트를 작성합니다.

```python
def fetch_ohlcv(
    self,
    symbol: str,
    timeframe: str = '1d',
    since: Optional[int] = None,
    limit: int = 100
) -> pd.DataFrame:
    pass
```

### 7.3 Docstring

Google 스타일 docstring을 사용합니다.

```python
def create_order(self, symbol: str, order_type: str, side: str,
                amount: float, price: Optional[float] = None) -> Dict[str, Any]:
    """
    주문 생성.

    Args:
        symbol: 거래 심볼
        order_type: 'market' 또는 'limit'
        side: 'buy' 또는 'sell'
        amount: 주문 수량
        price: 주문 가격 (limit 주문 시 필수)

    Returns:
        주문 정보를 담은 딕셔너리.

    Raises:
        BrokerError: 주문 생성 실패 시
        InsufficientFunds: 잔고 부족 시

    Example:
        >>> order = broker.create_order('BTC/USDT', 'limit', 'buy', 1.0, 42000)
    """
    pass
```

### 7.4 Import 순서

```python
# 1. 표준 라이브러리
from typing import Dict, List, Optional, Any
import time
from datetime import datetime

# 2. 서드파티 라이브러리
import pandas as pd
import ccxt

# 3. 로컬 모듈
from .base_broker import BaseBroker, BrokerError
```

---

## 8. 성능 최적화

### 8.1 Rate Limiting

모든 브로커는 API 호출 제한을 준수해야 합니다.

- **CCXT**: `enableRateLimit=True` 설정
- **한국투자증권**: `RateLimiter` 클래스 사용

### 8.2 캐싱

자주 조회되는 데이터는 캐싱하여 API 호출을 줄입니다.

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def fetch_symbol_info(self, symbol: str) -> Dict:
    """심볼 정보 조회 (캐싱)"""
    return self.api.fetch_symbol_info(symbol)
```

### 8.3 비동기 처리

대량 데이터 조회 시 비동기 처리를 고려합니다 (CCXT 비동기 버전).

```python
import ccxt.async_support as ccxt_async

class AsyncCCXTBroker(BaseBroker):
    async def fetch_ohlcv(self, symbol, timeframe, since, limit):
        ohlcv = await self.exchange.fetch_ohlcv(...)
        return self._format_ohlcv(ohlcv)
```

---

## 9. 보안 가이드

### 9.1 API 키 관리

API 키는 **절대 코드에 하드코딩하지 않습니다**.

**권장 방법**:

#### 환경변수 사용
```bash
# .env 파일
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
KIS_APPKEY=your_appkey
KIS_APPSECRET=your_appsecret
KIS_ACCOUNT=12345678-01
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

broker = CCXTBroker(
    exchange_id='binance',
    api_key=os.getenv('BINANCE_API_KEY'),
    secret=os.getenv('BINANCE_API_SECRET')
)
```

#### 설정 파일 사용
```yaml
# config.yaml (절대 Git에 커밋하지 않음!)
brokers:
  binance:
    api_key: your_api_key
    secret: your_api_secret
  korea_investment:
    appkey: your_appkey
    appsecret: your_appsecret
    account: 12345678-01
```

```python
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

broker = CCXTBroker(
    exchange_id='binance',
    api_key=config['brokers']['binance']['api_key'],
    secret=config['brokers']['binance']['secret']
)
```

### 9.2 .gitignore 설정

```gitignore
# API 키 파일
.env
config.yaml
secrets.json

# 로그 파일
*.log
```

### 9.3 권한 최소화

API 키 생성 시 필요한 권한만 부여합니다.

- 읽기 전용: `fetch_balance`, `fetch_ohlcv`, `fetch_ticker`
- 주문 권한: `create_order`, `cancel_order`
- **출금 권한은 절대 부여하지 않음**

---

## 10. 참고 자료

### 10.1 공식 문서

- [CCXT Documentation](https://docs.ccxt.com/)
- [한국투자증권 KIS Developers](https://apiportal.koreainvestment.com/)
- [python-kis GitHub](https://github.com/Soju06/python-kis)

### 10.2 관련 문서

- [docs/broker_comparison.md](../../docs/broker_comparison.md): 브로커 비교 및 통합 전략
- [docs/kiwoom_api_research.md](../../docs/kiwoom_api_research.md): 키움증권 조사 보고서
- [docs/korea_investment_api_research.md](../../docs/korea_investment_api_research.md): 한국투자증권 조사 보고서

### 10.3 테스트 파일

- `tests/test_brokers.py`: 브로커 통합 테스트
- `tests/test_ccxt_broker.py`: CCXT 브로커 테스트
- `tests/test_korea_investment_broker.py`: 한국투자증권 브로커 테스트

---

## 11. FAQ

### Q1: 새 거래소를 추가하려면 어떻게 해야 하나요?

**A**: CCXT가 지원하는 거래소라면 `CCXTBroker`로 바로 사용 가능합니다.
```python
broker = CCXTBroker('upbit', api_key='KEY', secret='SECRET')
```

CCXT가 지원하지 않는다면 `BaseBroker`를 상속하여 새 브로커 클래스를 작성하세요.

### Q2: 모의투자 환경에서 테스트하려면?

**A**: 각 브로커의 테스트 환경을 사용하세요.

- **CCXT**: `testnet=True` 옵션
- **한국투자증권**: `mock=True` 옵션

### Q3: Rate Limit 오류가 발생합니다.

**A**:
- **CCXT**: `enableRateLimit=True` 설정 확인
- **한국투자증권**: `RateLimiter`가 자동 동작하므로, 수동 sleep 제거
- 동시 호출 수 줄이기

### Q4: 분봉 데이터가 부족합니다.

**A**: 한국투자증권은 분봉 데이터가 당일만 제공됩니다.
- **해결책 1**: 일봉 데이터 사용
- **해결책 2**: 외부 데이터 소스 (Yahoo Finance, Investing.com) 활용
- **해결책 3**: 자체 데이터 수집 시스템 구축

### Q5: 해외주식 거래 시간은?

**A**: 각 시장별 거래 시간을 확인하세요 (한국 시간 기준).

- **미국**: 23:30~06:00 (썸머타임: 22:30~05:00)
- **일본**: 09:00~15:00 (점심시간 제외)
- **홍콩**: 10:30~17:00 (점심시간 제외)

---

**작성일**: 2026-02-07
**작성자**: broker-integration-architect (trading-dev team)
**버전**: 0.1.0
