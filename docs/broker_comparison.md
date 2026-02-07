# 브로커 비교 및 통합 전략

본 문서는 암호화폐 거래(CCXT), 국내주식 거래(키움증권), 국내/해외주식 거래(한국투자증권) 브로커를 비교하고 통합 전략을 제시합니다.

---

## 1. 브로커 개요

### 1.1 CCXT (암호화폐)

- **공식 사이트**: [CCXT GitHub](https://github.com/ccxt/ccxt)
- **타입**: REST API + WebSocket 통합 라이브러리
- **지원 거래소**: 100+ 암호화폐 거래소 (Binance, Upbit, Coinbase 등)
- **사용 언어**: Python, JavaScript
- **플랫폼**: Windows, Linux, macOS

### 1.2 키움증권 OpenAPI+

- **공식 사이트**: [키움증권 OpenAPI](https://www.kiwoom.com/h/customer/download/VOpenApiInfoView)
- **타입**: ActiveX Control (OCX) 기반
- **지원 시장**: 국내주식 (코스피, 코스닥, 코넥스), 파생상품
- **사용 언어**: Python (PyQt5/PySide2 필요)
- **플랫폼**: Windows 전용 (32-bit)

### 1.3 한국투자증권 KIS Developers

- **공식 사이트**: [KIS Developers](https://apiportal.koreainvestment.com/intro)
- **타입**: REST API + WebSocket
- **지원 시장**: 국내주식 + 해외주식 (미국, 홍콩, 일본, 중국 등)
- **사용 언어**: Python (python-kis, mojito2 등)
- **플랫폼**: Windows, Linux, macOS

---

## 2. 종합 비교표

| 항목 | CCXT (암호화폐) | 키움증권 | 한국투자증권 |
|------|----------------|---------|-------------|
| **시장** | 암호화폐 (BTC, ETH 등) | 국내주식 | 국내주식 + 해외주식 |
| **플랫폼** | ✅ 크로스 플랫폼 | ❌ Windows 전용 | ✅ 크로스 플랫폼 |
| **아키텍처** | 64-bit 지원 | ❌ 32-bit 전용 | ✅ 64-bit 지원 |
| **기술 스택** | REST API + WebSocket | ActiveX/COM | REST API + WebSocket |
| **해외주식** | N/A | ❌ 미지원 | ✅ 지원 |
| **호출 제한** | 거래소별 상이 | 1초당 5회 | 1초당 15회 |
| **분봉 데이터** | 거래소별 상이 | 160일 (60,000분) | 당일만 |
| **일봉 데이터** | 거래소별 제한 | 무제한 | 무제한 |
| **실시간 데이터** | ✅ | ✅ | ✅ |
| **모의투자** | 일부 거래소 지원 | ✅ | ✅ |
| **커뮤니티** | ⭐⭐⭐ 매우 활발 | ⭐⭐⭐ 매우 활발 | ⭐⭐ 성장 중 |
| **이용료** | 무료 (API 키 필요) | 무료 | 무료 |
| **Docker 배포** | ✅ | ❌ (Windows Container 복잡) | ✅ |
| **타입 힌팅** | ✅ 완벽 | ⚠️ 라이브러리 의존 | ✅ python-kis 완벽 |
| **GUI 의존성** | 불필요 | PyQt5/PySide2 필수 | 불필요 |
| **인증 방식** | API Key + Secret | 수동 로그인 (공인인증서) | OAuth 2.0 (자동) |

---

## 3. 각 브로커의 장단점

### 3.1 CCXT (암호화폐)

#### 장점
- ✅ **멀티-거래소 지원**: 단일 인터페이스로 100+ 거래소 접근
- ✅ **크로스 플랫폼**: Windows, Linux, macOS 모두 지원
- ✅ **통일된 API**: 거래소별 차이를 추상화
- ✅ **활발한 커뮤니티**: 풍부한 문서 및 예제
- ✅ **24/7 거래**: 암호화폐는 24시간 거래 가능

#### 단점
- ❌ **거래소별 제약**: 각 거래소마다 기능 차이
- ❌ **높은 변동성**: 암호화폐 시장의 높은 위험
- ❌ **규제 리스크**: 국가별 규제 변화 가능
- ❌ **수수료**: 거래소별 수수료 구조 상이

#### 추천 사용 사례
- 암호화폐 자동매매
- 다중 거래소 아비트라지
- 24시간 트레이딩 봇
- 글로벌 시장 접근

---

### 3.2 키움증권 OpenAPI+

#### 장점
- ✅ **국내주식 전문**: 코스피/코스닥 완벽 지원
- ✅ **풍부한 분봉 데이터**: 160일 (60,000분) 과거 데이터
- ✅ **활발한 커뮤니티**: 다양한 Python 라이브러리 (pykiwoom, koapy 등)
- ✅ **안정성**: 오랜 역사와 검증된 플랫폼
- ✅ **무료**: 모의투자 및 실전 API 무료 제공

#### 단점
- ❌ **Windows 전용**: 크로스 플랫폼 불가
- ❌ **32-bit 전용**: 메모리 제약 (최대 4GB)
- ❌ **ActiveX 기반**: 구식 기술, 설치 복잡
- ❌ **해외주식 미지원**: 국내주식만 API 지원
- ❌ **GUI 필수**: PyQt5/PySide2 의존성
- ❌ **엄격한 제한**: 1초당 5회 호출
- ❌ **배포 어려움**: Docker/클라우드 배포 복잡

#### 추천 사용 사례
- Windows 전용 국내주식 자동매매
- 대량 분봉 데이터 수집 (백테스팅)
- 국내주식만 거래하는 경우

---

### 3.3 한국투자증권 KIS Developers

#### 장점
- ✅ **크로스 플랫폼**: Windows, Linux, macOS 지원
- ✅ **해외주식 완전 지원**: 미국, 홍콩, 일본, 중국 등
- ✅ **현대적 기술**: REST API + WebSocket + OAuth 2.0
- ✅ **타입 안전성**: python-kis 라이브러리 타입힌팅 완벽
- ✅ **느슨한 제한**: 1초당 15회 (키움 대비 3배)
- ✅ **배포 용이**: Docker, 클라우드 친화적
- ✅ **GUI 불필요**: PyQt5 의존성 없음
- ✅ **단일 API**: 국내 + 해외주식 통합

#### 단점
- ❌ **분봉 제약**: 당일만 (키움 160일 대비)
- ❌ **신규 플랫폼**: 2022년 시작 (안정성 검증 필요)
- ❌ **커뮤니티**: 키움 대비 작음 (빠르게 성장 중)

#### 추천 사용 사례
- 국내 + 해외주식 통합 자동매매
- 크로스 플랫폼 배포 필요
- Docker/클라우드 환경
- Linux/macOS 개발 환경
- 현대적 기술 스택 선호

---

## 4. 통합 전략

### 4.1 통합 아키텍처

본 프로젝트는 **브로커 추상화 계층**을 통해 모든 브로커를 통합합니다.

```
┌─────────────────────────────────────────────────┐
│           Trading Strategy Layer                 │
│     (RSI, MACD, MA Crossover 등)                 │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│          Broker Interface (추상 클래스)           │
│  - fetch_ohlcv()                                 │
│  - fetch_balance()                               │
│  - create_order()                                │
│  - cancel_order()                                │
│  - fetch_ticker()                                │
└─────────────────────────────────────────────────┘
                      ↓
        ┌──────────────┬──────────────┬──────────────┐
        │              │              │              │
┌───────▼──────┐ ┌────▼─────┐ ┌──────▼───────────┐
│CCXT Broker   │ │Kiwoom    │ │Korea Investment  │
│(암호화폐)     │ │Broker    │ │Broker            │
│              │ │(국내주식)│ │(국내+해외주식)   │
└──────────────┘ └──────────┘ └──────────────────┘
```

### 4.2 통합 방식

#### Option 1: 한국투자증권 단일 통합 ⭐⭐⭐ (강력 권장)

**구조**:
```
프로젝트
├── CCXT Broker (암호화폐)
└── Korea Investment Broker (국내/해외주식)
```

**장점**:
- ✅ 크로스 플랫폼 유지
- ✅ 단일 코드베이스
- ✅ 해외주식 지원
- ✅ Docker/클라우드 배포 용이

**단점**:
- ⚠️ 분봉 데이터 당일만 (백테스팅 제약)

**권장 사유**:
- 프로젝트가 이미 크로스 플랫폼 (Python)
- 해외주식까지 확장 가능
- 현대적 기술 스택
- 배포 자유도 높음

---

#### Option 2: 멀티 브로커 (키움 + 한투)

**구조**:
```
프로젝트
├── CCXT Broker (암호화폐)
├── Kiwoom Broker (국내주식 - Windows 전용)
└── Korea Investment Broker (해외주식)
```

**장점**:
- ✅ 키움의 160일 분봉 데이터 활용
- ✅ 해외주식도 지원

**단점**:
- ❌ Windows 의존성 발생
- ❌ 복잡한 아키텍처
- ❌ 배포 제약 (Docker 복잡)
- ❌ 유지보수 비용 증가

**권장하지 않는 이유**:
- 크로스 플랫폼 장점 상실
- 아키텍처 복잡도 증가
- 분봉 데이터 활용도 낮음 (실전 트레이딩에서)

---

#### Option 3: CCXT Only (현재 상태 유지)

**구조**:
```
프로젝트
└── CCXT Broker (암호화폐만)
```

**장점**:
- ✅ 단순함
- ✅ 검증된 코드베이스

**단점**:
- ❌ 주식 시장 접근 불가
- ❌ 포트폴리오 다각화 제한

---

### 4.3 최종 권장사항

#### ⭐ 한국투자증권 단일 통합 (Option 1)

**근거**:
1. **크로스 플랫폼 유지**: Linux/macOS/Docker 지원
2. **해외주식 지원**: 글로벌 시장 진출 가능
3. **단일 코드베이스**: 유지보수 용이
4. **현대적 기술**: REST API, 타입힌팅
5. **배포 자유도**: 클라우드 배포 간편

**trade-off**:
- 분봉 데이터 당일만 (백테스팅 제약)
- **해결책**: 일봉 데이터 활용 또는 외부 데이터 소스 (Yahoo Finance 등) 보완

---

## 5. 단계별 통합 로드맵

### Phase 1: 기반 구축 (1-2주)

1. **브로커 추상화 계층 설계**
   - `BaseBroker` 추상 클래스 작성
   - 공통 인터페이스 정의 (fetch_ohlcv, create_order 등)

2. **한국투자증권 브로커 구현**
   - python-kis 라이브러리 설치
   - `KoreaInvestmentBroker` 클래스 구현
   - 모의투자 계정으로 인증 테스트

3. **CCXT 브로커 어댑터**
   - 기존 CCXT 코드를 `CCXTBroker` 클래스로 래핑
   - `BaseBroker` 인터페이스 준수

### Phase 2: 국내주식 통합 (2-3주)

4. **국내주식 데이터 핸들러**
   - 일봉/분봉 데이터 조회
   - 현재가/호가 조회
   - 데이터 포맷 통일 (pandas DataFrame)

5. **전략 적용**
   - 기존 RSI, MACD 전략을 국내주식에 적용
   - 백테스팅 실행
   - 모의투자 테스트

### Phase 3: 해외주식 확장 (2-3주)

6. **해외주식 데이터 핸들러**
   - 미국/홍콩/일본 주식 데이터 조회
   - 환율 리스크 관리
   - 거래소별 운영시간 처리

7. **멀티-에셋 포트폴리오**
   - 암호화폐 + 국내주식 + 해외주식 통합
   - 리스크 관리 (position sizing, stop-loss)
   - 통합 대시보드

### Phase 4: 프로덕션 배포 (1-2주)

8. **배포 준비**
   - Docker 이미지 빌드
   - 환경변수 관리 (API 키, Secret)
   - 로깅 및 모니터링

9. **실전 투자**
   - 소액으로 시작
   - 성과 모니터링
   - 지속적 개선

---

## 6. 기술 스택 비교

### 6.1 데이터 조회 API

| 기능 | CCXT | 키움증권 | 한국투자증권 |
|------|------|---------|-------------|
| 일봉 | `fetch_ohlcv(symbol, '1d')` | `opt10081.TR_REQ` | `api.stock.ohlcv(timeframe='D')` |
| 분봉 | `fetch_ohlcv(symbol, '1m')` | `opt10080.TR_REQ` | `api.stock.ohlcv(timeframe='1')` |
| 현재가 | `fetch_ticker(symbol)` | `opt10001.TR_REQ` | `api.stock.quote(symbol)` |
| 실시간 | WebSocket | `SetRealReg()` | WebSocket |

### 6.2 주문 API

| 기능 | CCXT | 키움증권 | 한국투자증권 |
|------|------|---------|-------------|
| 시장가 매수 | `create_market_buy_order()` | `SendOrder(매수, 03)` | `api.stock.buy(order_type='market')` |
| 지정가 매수 | `create_limit_buy_order()` | `SendOrder(매수, 00)` | `api.stock.buy(price=X)` |
| 시장가 매도 | `create_market_sell_order()` | `SendOrder(매도, 03)` | `api.stock.sell(order_type='market')` |
| 주문 취소 | `cancel_order(order_id)` | `SendOrder(취소, 02)` | `api.stock.cancel(order_id)` |

### 6.3 계좌 조회 API

| 기능 | CCXT | 키움증권 | 한국투자증권 |
|------|------|---------|-------------|
| 잔고 | `fetch_balance()` | `opw00018.TR_REQ` | `api.account.balance()` |
| 보유 종목 | `fetch_balance()` | `opw00018.TR_REQ` | `api.account.holdings()` |

---

## 7. 수수료 비교

### 7.1 거래 수수료

| 시장 | CCXT (암호화폐) | 키움증권 | 한국투자증권 |
|------|----------------|---------|-------------|
| **국내주식** | N/A | 0.015% (매수/매도) | 0.015% (매수/매도) |
| **국내주식 세금** | N/A | 0.20% (매도 시) | 0.20% (매도 시) |
| **미국주식** | N/A | HTS/MTS만 (0.25%) | 0.25% (API 지원) |
| **암호화폐** | 거래소별 (0.1~0.5%) | N/A | N/A |

### 7.2 총 거래 비용 (왕복 기준)

| 시장 | 매수 + 매도 총 비용 |
|------|-------------------|
| 암호화폐 (Binance) | ~0.2% (0.1% × 2) |
| 국내주식 (키움/한투) | ~0.245% (0.015% + 0.015% + 0.20% 세금) |
| 미국주식 (한투) | ~0.5% (0.25% × 2) |

---

## 8. 프로젝트 통합 예제 코드

### 8.1 브로커 추상화 인터페이스

```python
# trading_bot/brokers/base_broker.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class BaseBroker(ABC):
    """모든 브로커의 추상 인터페이스"""

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1d',
                    since: Optional[int] = None, limit: int = 100) -> pd.DataFrame:
        """OHLCV 데이터 조회"""
        pass

    @abstractmethod
    def fetch_balance(self) -> Dict:
        """계좌 잔고 조회"""
        pass

    @abstractmethod
    def create_order(self, symbol: str, order_type: str, side: str,
                    amount: float, price: Optional[float] = None) -> Dict:
        """주문 생성"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict:
        """주문 취소"""
        pass

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Dict:
        """현재가 조회"""
        pass
```

### 8.2 CCXT 브로커 어댑터 (예시)

```python
# trading_bot/brokers/ccxt_broker.py

from .base_broker import BaseBroker
import ccxt
import pandas as pd

class CCXTBroker(BaseBroker):
    """암호화폐 거래소 브로커 (CCXT)"""

    def __init__(self, exchange_id: str, api_key: str = None, secret: str = None):
        self.exchange = getattr(ccxt, exchange_id)({
            'apiKey': api_key,
            'secret': secret,
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1d',
                    since: Optional[int] = None, limit: int = 100) -> pd.DataFrame:
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def fetch_balance(self) -> Dict:
        return self.exchange.fetch_balance()

    def create_order(self, symbol: str, order_type: str, side: str,
                    amount: float, price: Optional[float] = None) -> Dict:
        return self.exchange.create_order(symbol, order_type, side, amount, price)

    def cancel_order(self, order_id: str) -> Dict:
        return self.exchange.cancel_order(order_id)

    def fetch_ticker(self, symbol: str) -> Dict:
        return self.exchange.fetch_ticker(symbol)
```

### 8.3 한국투자증권 브로커 어댑터 (예시)

```python
# trading_bot/brokers/korea_investment_broker.py

from .base_broker import BaseBroker
from pykis import KoreaInvestment
import pandas as pd

class KoreaInvestmentBroker(BaseBroker):
    """한국투자증권 브로커 (국내/해외주식)"""

    def __init__(self, appkey: str, appsecret: str, account: str):
        self.api = KoreaInvestment(
            appkey=appkey,
            appsecret=appsecret,
            account=account
        )

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1d',
                    since: Optional[int] = None, limit: int = 100) -> pd.DataFrame:
        # 한국투자증권 API로 OHLCV 조회
        data = self.api.stock.ohlcv(symbol, interval=timeframe, count=limit)
        # pandas DataFrame으로 변환 (CCXT와 동일한 포맷)
        return self._format_ohlcv(data)

    def fetch_balance(self) -> Dict:
        balance = self.api.account.balance()
        return {
            'free': balance.cash,
            'used': balance.total_value - balance.cash,
            'total': balance.total_value
        }

    def create_order(self, symbol: str, order_type: str, side: str,
                    amount: float, price: Optional[float] = None) -> Dict:
        if side == 'buy':
            if order_type == 'market':
                return self.api.stock.buy(symbol, qty=amount)
            else:
                return self.api.stock.buy(symbol, price=price, qty=amount)
        else:
            if order_type == 'market':
                return self.api.stock.sell(symbol, qty=amount)
            else:
                return self.api.stock.sell(symbol, price=price, qty=amount)

    def cancel_order(self, order_id: str) -> Dict:
        return self.api.stock.cancel(order_id)

    def fetch_ticker(self, symbol: str) -> Dict:
        quote = self.api.stock.quote(symbol)
        return {
            'symbol': symbol,
            'last': quote.price,
            'bid': quote.bid,
            'ask': quote.ask,
            'volume': quote.volume
        }

    def _format_ohlcv(self, data) -> pd.DataFrame:
        # 한국투자증권 데이터를 CCXT 포맷으로 변환
        # 구현 세부 사항은 실제 API 응답 구조에 따름
        pass
```

---

## 9. 결론

### 9.1 최종 권장사항

본 프로젝트는 **한국투자증권 API를 통한 단일 통합 전략**을 권장합니다.

**핵심 이유**:
1. ✅ **크로스 플랫폼**: 현재 프로젝트 구조와 호환
2. ✅ **해외주식 지원**: 글로벌 시장 확장 가능
3. ✅ **현대적 기술**: REST API, 타입힌팅, Docker 친화적
4. ✅ **단일 코드베이스**: 유지보수 용이
5. ✅ **배포 자유도**: Linux/macOS/클라우드 배포 가능

### 9.2 키움증권을 선택하지 않는 이유

- ❌ Windows 전용 제약으로 배포 자유도 하락
- ❌ 해외주식 미지원으로 확장성 제한
- ❌ ActiveX 기반 구식 기술
- ❌ Docker/클라우드 배포 복잡
- ⚠️ 분봉 160일 장점은 있으나, 실전 트레이딩에서 활용도 낮음

### 9.3 다음 단계

1. **즉시 실행**:
   - 한국투자증권 계좌 개설
   - KIS Developers 서비스 신청
   - python-kis 설치: `pip install python-kis`

2. **단기 (1-2주)**:
   - 브로커 추상화 계층 구현 (`BaseBroker`)
   - 한국투자증권 브로커 어댑터 구현
   - 모의투자 테스트

3. **중기 (1-2개월)**:
   - 기존 전략 국내주식 적용
   - 해외주식 지원 추가
   - 통합 대시보드

4. **장기 (3-6개월)**:
   - 프로덕션 배포
   - 멀티-에셋 포트폴리오 최적화
   - 실전 투자

---

## Sources

- [CCXT GitHub](https://github.com/ccxt/ccxt)
- [키움증권 OpenAPI](https://www.kiwoom.com/h/customer/download/VOpenApiInfoView)
- [한국투자증권 KIS Developers](https://apiportal.koreainvestment.com/intro)
- [python-kis GitHub](https://github.com/Soju06/python-kis)
- [키움 API 조사 보고서](kiwoom_api_research.md)
- [한국투자증권 API 조사 보고서](korea_investment_api_research.md)

**작성일**: 2026-02-07
**작성자**: broker-integration-architect (trading-dev team)
