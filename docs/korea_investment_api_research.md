# 한국투자증권 OpenAPI 조사 보고서

## 1. 개요

한국투자증권 OpenAPI(KIS Developers)는 대한민국 증권사 최초로 2022년 4월부터 제공되기 시작한 REST API 기반의 오픈 트레이딩 플랫폼입니다.

- **공식 명칭**: KIS Developers (한국투자증권 오픈API 개발자센터)
- **타입**: REST API + WebSocket
- **개발 지원**: 모든 플랫폼 (Windows, Linux, macOS)
- **공식 문서**: [KIS Developers 포털](https://apiportal.koreainvestment.com/intro)
- **GitHub 샘플**: [공식 샘플 코드](https://github.com/koreainvestment/open-trading-api)

## 2. 핵심 장점 - 키움증권 대비

### 2.1 크로스 플랫폼 지원

- ✅ **REST API 기반**: HTTP 프로토콜 사용으로 플랫폼 독립적
- ✅ **Windows/Linux/macOS**: 모든 운영체제에서 동작
- ✅ **64-bit 지원**: 메모리 제약 없음
- ✅ **Docker/Container 친화적**: 서버 배포 용이
- ✅ **GUI 프레임워크 불필요**: PyQt5/PySide2 의존성 없음

### 2.2 해외주식 완전 지원

키움증권과 달리 **단일 API로 국내 + 해외주식 통합 거래** 가능:

| 시장 | 키움증권 | 한국투자증권 |
|------|---------|-------------|
| 국내주식 | ✅ OpenAPI+ | ✅ REST API |
| 미국주식 | ❌ (HTS/MTS만) | ✅ REST API |
| 홍콩주식 | ❌ | ✅ REST API |
| 일본주식 | ❌ | ✅ REST API |
| 중국주식 | ❌ | ✅ REST API |

### 2.3 현대적인 기술 스택

- **OAuth 2.0 인증**: AppKey + AppSecret → 액세스 토큰 발급
- **JSON 기반 통신**: 파싱 용이
- **WebSocket 실시간 데이터**: 양방향 스트리밍
- **자동 재연결**: 네트워크 장애 시 복구 가능

## 3. Python 라이브러리

### 3.1 mojito2 (sharebook-kr)

- **GitHub**: [sharebook-kr/mojito](https://github.com/sharebook-kr/mojito)
- **GitHub Stars**: 89개 ⭐
- **설치**: `pip install mojito2` (pypi에 mojito 이름 선점되어 mojito2 사용)
- **Python 버전**: 3.7+
- **취지**: "돈 벌어서 몰디브가서 모히토 한 잔 하자"

**주요 기능**:
- OAuth 인증 (Hashkey, 접근토큰 발급)
- 국내주식 주문 및 잔고 조회
- 현재가, 일봉 데이터 조회
- 주문 생성/취소
- WebSocket 실시간 데이터 스트림
- **미국주식 거래 지원**

**특징**:
- ✅ 초보자 친화적
- ✅ 간단한 API 인터페이스
- ✅ 활발한 커뮤니티 (43개 포크, 7명 기여자)

**사용 예제**:
```python
import mojito

key = "발급받은 API KEY"
secret = "발급받은 API SECRET"
acc_no = "12345678-01"

broker = mojito.KoreaInvestment(
    api_key=key,
    api_secret=secret,
    acc_no=acc_no
)

# 현재가 조회 (삼성전자)
resp = broker.fetch_price("005930")

# 일봉 데이터 조회
resp = broker.fetch_ohlcv("005930", timeframe="D")

# 시장가 매수
resp = broker.create_market_buy_order("005930", 10)

# 미국주식 거래
resp = broker.create_market_buy_order("AAPL", 5, overseas=True)
```

### 3.2 python-kis (Soju06)

- **GitHub**: [Soju06/python-kis](https://github.com/Soju06/python-kis)
- **GitHub Stars**: 250개 ⭐⭐⭐ (가장 인기)
- **설치**: `pip install python-kis`
- **Python 버전**: 3.11 권장
- **최신 버전**: v2.1.3

**주요 기능**:
- 국내/해외주식 시세 조회
- 계좌 관리 (잔고, 예수금 조회)
- 주문 처리 (매수/매도/정정/취소)
- 실시간 데이터 스트리밍
- 자동 재연결 WebSocket

**주요 특징**:
1. ⭐ **완벽한 타입 힌팅**: 모든 함수/클래스에 Type Hints 적용 → IDE 자동완성 지원
2. ⭐ **복구 가능한 WebSocket**: 네트워크 장애 시 자동 재연결 + 이전 구독 복원
3. ⭐ **표준 영어 네이밍**: 한글 발음 대신 직관적인 영어 함수명

**사용 예제**:
```python
from pykis import KoreaInvestment

# 인증
api = KoreaInvestment(
    appkey="YOUR_APP_KEY",
    appsecret="YOUR_APP_SECRET",
    account="12345678-01"
)

# 시세 조회
quote = api.stock.quote("005930")

# 잔고 조회
balance = api.account.balance()

# 매수 주문
api.stock.buy("005930", price=70000, qty=10)

# 실시간 체결가 수신
def on_price(data):
    print(f"체결가: {data.price}")

api.stock.on('price', on_price)
api.stock.subscribe('005930')
```

### 3.3 pykis (pjueon)

- **GitHub**: [pjueon/pykis](https://github.com/pjueon/pykis)
- **GitHub Stars**: 56개 ⭐
- **설치**: `pip3 install pykis` 또는 GitHub 클론
- **Python 버전**: 3.7+
- **라이선스**: Apache-2.0

**주요 기능**:
- 국내주식: 현재가, OHLCV, 잔고, 주문
- 해외주식: 9개 거래소 지원 (홍콩, 뉴욕, 나스닥, 도쿄 등)
- 주문 취소/정정

**특징**:
- ✅ Web API 방식 (HTS 불필요)
- ✅ OS 제한 없음
- ⚠️ 개발 단계 소프트웨어
- ⚠️ 개인 투자 용도 권장

### 3.4 한국투자증권 공식 샘플 코드

- **GitHub**: [koreainvestment/open-trading-api](https://github.com/koreainvestment/open-trading-api)
- **특징**: ChatGPT, Claude 등 LLM 및 Python 개발자를 위한 100+ 샘플 코드

**권장 사용 순서**:
1. 공식 샘플 코드로 API 이해
2. 라이브러리 선택 (python-kis 또는 mojito2)
3. 프로덕션 코드 개발

### 3.5 라이브러리 비교표

| 라이브러리 | Stars | 타입힌팅 | 실시간 | 해외주식 | 커뮤니티 | 권장도 |
|-----------|-------|---------|--------|---------|---------|--------|
| **python-kis** | 250⭐⭐⭐ | ✅ 완벽 | ✅ 자동재연결 | ✅ | 활발 | ⭐⭐⭐⭐⭐ |
| **mojito2** | 89⭐⭐ | ⚠️ 부분 | ✅ | ✅ | 활발 | ⭐⭐⭐⭐ |
| **pykis** | 56⭐ | ⚠️ 부분 | ❓ | ✅ 9개 거래소 | 보통 | ⭐⭐⭐ |

**결론**: **python-kis**가 타입 안정성, 기능, 커뮤니티 측면에서 가장 우수

## 4. API 기능 상세

### 4.1 실시간 시세 수신

**WebSocket API**:
- **접속 방식**: 액세스 키로 WebSocket 연결
- **데이터 타입**:
  - 실시간 체결가
  - 실시간 호가
  - 실시간 체결내역
  - 실시간 잔고 변경
- **자동 재연결**: 네트워크 장애 시 복구
- **주의사항**: 무한루프 WebSocket 호출 시 자동 차단

**python-kis 예제**:
```python
api.stock.on('price', callback)  # 실시간 체결가
api.stock.on('orderbook', callback)  # 실시간 호가
api.stock.on('execution', callback)  # 실시간 체결내역
api.stock.subscribe('005930')
```

### 4.2 과거 데이터 조회

**지원 데이터**:

#### 국내주식
- **일봉/주봉/월봉**: 제한 없음 (전체 과거 데이터)
- **분봉**: 당일 분봉 데이터
- **틱**: 실시간만 제공

#### 해외주식 (미국, 홍콩, 일본 등)
- **일봉**: 과거 데이터 조회 가능
- **분봉**: 당일 데이터
- **제약**: 국내주식 대비 데이터 제공 범위 다를 수 있음

**API 예제**:
```python
# 일봉 데이터 (국내)
broker.fetch_ohlcv("005930", timeframe="D", count=100)

# 분봉 데이터 (당일)
broker.fetch_ohlcv("005930", timeframe="1", count=60)

# 해외주식 일봉 (미국)
broker.fetch_ohlcv("AAPL", timeframe="D", count=100, overseas=True)
```

**키움증권 대비 제약**:
- ⚠️ 키움은 분봉 160일 (60,000분), 한투는 당일만
- ⚠️ 대량 과거 데이터 수집 시 호출 제한 고려 필요

### 4.3 주문 실행

**지원 주문 유형**:

#### 국내주식
- 신규매수 (지정가, 시장가)
- 신규매도 (지정가, 시장가)
- 매수정정
- 매도정정
- 매수취소
- 매도취소
- 조건부지정가

#### 해외주식
- 신규매수 (지정가, 시장가)
- 신규매도 (지정가, 시장가)
- 주문 취소/정정
- **지원 시장**: 미국, 홍콩, 중국, 일본, 싱가포르, 독일, 베트남 등

**주문 예제**:
```python
# 국내주식 시장가 매수
api.stock.buy("005930", qty=10, order_type="market")

# 국내주식 지정가 매수
api.stock.buy("005930", price=70000, qty=10, order_type="limit")

# 미국주식 시장가 매수
api.stock_overseas.buy("AAPL", qty=5, market="nasdaq")

# 주문 취소
api.stock.cancel(order_id="12345678")
```

### 4.4 계좌 정보 조회

**조회 가능 정보**:
- 예수금 (현금 잔고)
- 보유 종목 (국내/해외 구분)
- 매수/매도 가능 금액
- 체결 내역
- 미체결 주문
- 계좌 수익률

**예제**:
```python
# 잔고 조회
balance = api.account.balance()
print(f"예수금: {balance.cash}")
print(f"총 평가금액: {balance.total_value}")

# 보유 종목
holdings = api.account.holdings()
for stock in holdings:
    print(f"{stock.symbol}: {stock.qty}주, 평가손익: {stock.profit}")
```

### 4.5 지원 마켓 상세

#### 해외 거래소 운영시간 (한국시간 기준)

| 시장 | 거래소 | 운영시간 (한국시간) |
|------|--------|------------------|
| 미국 | 뉴욕증권거래소 (NYSE) | 23:30 ~ 06:00 (썸머타임: 22:30 ~ 05:00) |
| 미국 | 나스닥 (NASDAQ) | 23:30 ~ 06:00 (썸머타임: 22:30 ~ 05:00) |
| 일본 | 도쿄증권거래소 | 오전: 09:00 ~ 11:30, 오후: 12:30 ~ 15:00 |
| 홍콩 | 홍콩증권거래소 | 오전: 10:30 ~ 13:00, 오후: 14:00 ~ 17:00 |
| 중국 | 상해증권거래소 | 10:30 ~ 16:00 |

**주의**: 해외주식 서비스는 한국투자증권 계좌에서 별도 신청 필요

## 5. 인증 방식 및 제약사항

### 5.1 API 키 발급 방법

**절차**:
1. **한국투자증권 계좌 개설**: [한국투자증권 홈페이지](https://securities.koreainvestment.com)
2. **KIS Developers 서비스 신청**: [KIS Developers 포털](https://apiportal.koreainvestment.com) 접속
3. **API 키 발급**:
   - AppKey (앱 키)
   - AppSecret (앱 시크릿)
   - 발급 즉시 사용 가능
4. **실전/모의투자 선택**:
   - 실전투자: 실제 계좌 연동
   - 모의투자: 가상 계좌 (테스트용)

**갱신**:
- 유효기간: 신청일로부터 **1년**
- 갱신 시: 1년 연장, AppKey/AppSecret 재발급

### 5.2 인증 방식 (OAuth 2.0)

**토큰 발급 플로우**:
```
1. AppKey + AppSecret → POST /oauth2/tokenP
2. 액세스 토큰 발급 (24시간 유효)
3. 액세스 토큰으로 API 호출 (Header: Authorization: Bearer {token})
4. 만료 전 재발급 (refresh)
```

**코드 예제**:
```python
# 라이브러리가 자동 처리
api = KoreaInvestment(
    appkey="YOUR_APP_KEY",
    appsecret="YOUR_APP_SECRET",
    account="12345678-01"
)
# 토큰 자동 발급 + 갱신
```

### 5.3 API 호출 제한 (Rate Limit)

**호출 유량 제한**:
- **방식**: 슬라이딩 윈도우 (Sliding Window)
- **제한**: **초당 15회** 요청
- **위반 시**: HTTP 429 (Too Many Requests) + 일시적 차단

**주의사항**:
- 경계점에 요청이 몰리면 제한 위배 가능
- 대량 데이터 수집 시 쓰로틀링(Throttling) 구현 필요

**쓰로틀링 예제** (참고: [쓰로틀링 블로그 글](https://hky035.github.io/web/kis-api-throttling/)):
```python
import time
from collections import deque

class APIThrottler:
    def __init__(self, max_calls=15, period=1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def wait(self):
        now = time.time()
        # 1초 이전 호출 기록 제거
        while self.calls and self.calls[0] < now - self.period:
            self.calls.popleft()

        # 제한 초과 시 대기
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            time.sleep(sleep_time)

        self.calls.append(time.time())

# 사용
throttler = APIThrottler(max_calls=15, period=1.0)
for symbol in symbols:
    throttler.wait()
    data = api.fetch_price(symbol)
```

**키움증권 대비**:
- 키움: 1초당 5회 (더 엄격)
- 한투: 1초당 15회 (3배 여유)

### 5.4 플랫폼 호환성

| 플랫폼 | 키움증권 | 한국투자증권 |
|--------|---------|-------------|
| Windows | ✅ (32-bit 전용) | ✅ (64-bit 포함) |
| Linux | ❌ | ✅ |
| macOS | ❌ | ✅ |
| Docker | ⚠️ (Windows Container) | ✅ |
| 클라우드 (AWS/GCP/Azure) | ⚠️ (Windows 서버) | ✅ |

**결론**: 한국투자증권은 **크로스 플랫폼 배포에 최적화**

### 5.5 기타 제약사항

**중복 로그인**:
- 실전투자: 중복 로그인 가능 (여러 프로그램 동시 실행)
- 모의투자: 중복 로그인 제한 가능 (서버 정책에 따름)

**WebSocket 주의**:
- 무한루프 호출 시 자동 차단
- 재연결 로직 필수 구현

**데이터 제한**:
- 분봉: 당일만 (키움 160일 대비 제약)
- 틱: 실시간만, 과거 틱 데이터 미제공

## 6. 수수료 구조 및 비용

### 6.1 국내주식 거래 수수료

#### 매매 수수료
- **온라인 거래**: 0.015% (표준)

#### 세금 (매도 시)
- **거래세**: 0.20%
- **농어촌특별세**: 0.05% (코스피만)

#### 총 비용 (매도 시)
- 수수료 (0.015%) + 세금 (0.20%) = **약 0.215%**

### 6.2 해외주식 거래 수수료

#### 기본 수수료
- **미국 주식**: 0.25% (온라인 기준)
- **홍콩 주식**: 0.25%
- **일본 주식**: 0.25%
- **중국 주식**: 0.48% (매도 시 최소수수료: USD 50 또는 HKD 400)

#### 우대 수수료 프로모션
신규 고객 대상 우대 혜택:
- **첫 3개월**: 파격 할인 (프로모션에 따라 변동)
- **이후 9개월**: 0.09% (미국시장 기준)
- **적용 국가**: 미국, 홍콩, 중국, 일본 (기타 거래세 별도)

**키움증권 대비**:
- 키움: 해외주식 API 미지원 (HTS/MTS로만 거래)
- 한투: API로 해외주식 자동매매 가능 ⭐

### 6.3 API 이용료

- **무료**: API 사용에 별도 비용 없음
- **KIS Developers 서비스**: 무료 제공
- **모의투자**: 무료

### 6.4 프로그램 매매 시 고려사항

**슬리피지 (Slippage)**:
- 주문 시점과 체결 시점의 가격 차이
- 시장가 주문 시 특히 주의

**시장 충격 (Market Impact)**:
- 대량 주문 시 호가 변동 유발
- 분할 매매 전략 권장

**환율 리스크 (해외주식)**:
- USD, HKD, JPY 등 환전 필요
- 환전 수수료 별도 발생
- 환율 변동 리스크

**기타 수수료**:
- 결제 수수료 (국가별 상이)
- 현지 거래세 (SEC fee 등)
- 계좌 유지 비용 (일부 서비스)

## 7. 개발 워크플로우

### 7.1 권장 개발 순서

```
1. 한국투자증권 계좌 개설
   ↓
2. KIS Developers 서비스 신청
   ↓
3. AppKey/AppSecret 발급
   ↓
4. 모의투자 계좌 생성 (테스트용)
   ↓
5. Python 환경 구성 (Python 3.11+)
   ↓
6. 라이브러리 선택 및 설치 (python-kis 권장)
   ↓
7. 공식 샘플 코드로 API 학습
   ↓
8. 인증 테스트 (토큰 발급)
   ↓
9. 시세 조회 구현
   ↓
10. 계좌 조회 구현
   ↓
11. 모의투자에서 주문 테스트
   ↓
12. 백테스팅 및 전략 검증
   ↓
13. 실전 투자 (신중하게!)
```

### 7.2 모의투자 활용

**장점**:
- ✅ 실제 시세 데이터 사용
- ✅ 리스크 없이 전략 검증
- ✅ API 기능 전체 테스트 가능
- ✅ 무료 제공

**제약**:
- ⚠️ 실서버와 약간의 차이 있을 수 있음
- ⚠️ 중복 로그인 제한 가능

**권장 사용 기간**:
- 최소 **1개월** 이상 모의투자 테스트
- 다양한 시장 상황에서 안정성 검증
- 수익률보다 **안정성** 우선 평가

### 7.3 프로젝트 통합 예제

**현재 프로젝트 구조에 통합**:

```python
# trading_bot/brokers/korea_investment.py

from pykis import KoreaInvestment

class KoreaInvestmentBroker:
    """한국투자증권 브로커 어댑터"""

    def __init__(self, appkey, appsecret, account):
        self.api = KoreaInvestment(
            appkey=appkey,
            appsecret=appsecret,
            account=account
        )

    def fetch_ohlcv(self, symbol, timeframe='D', limit=100):
        """OHLCV 데이터 조회 (ccxt 인터페이스 호환)"""
        data = self.api.stock.ohlcv(
            symbol=symbol,
            interval=timeframe,
            count=limit
        )
        return self._format_ohlcv(data)

    def create_order(self, symbol, order_type, side, amount, price=None):
        """주문 생성 (ccxt 인터페이스 호환)"""
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

    def fetch_balance(self):
        """잔고 조회 (ccxt 인터페이스 호환)"""
        balance = self.api.account.balance()
        return {
            'free': balance.cash,
            'used': balance.total_value - balance.cash,
            'total': balance.total_value
        }
```

## 8. 프로젝트 통합 시 고려사항

### 8.1 아키텍처 통합

현재 프로젝트는 CCXT 기반 암호화폐 거래 봇이므로, 한국투자증권 API 통합 시 다음을 고려:

#### 브로커 추상화 계층
```
Broker Interface (Abstract)
    ├── CCXT Broker (암호화폐)
    ├── Kiwoom Broker (국내주식 - Windows 전용)
    └── KoreaInvestment Broker (국내/해외주식 - 크로스 플랫폼) ⭐
```

#### 데이터 핸들러 통합
```
Data Handler Interface
    ├── CCXT Data Handler (암호화폐)
    └── KoreaInvestment Data Handler (국내/해외주식) ⭐
```

### 8.2 크로스 플랫폼 전략

#### ✅ 권장: 단일 플랫폼 통합
- 암호화폐 + 국내주식 + 해외주식을 **한국투자증권 API**로 통합
- Linux/macOS/Docker 모두 지원
- 단일 코드베이스 유지

#### ⚠️ 대안: 멀티 브로커 (키움 + 한투)
- 키움: 국내주식 전용 (Windows)
- 한투: 해외주식 전용
- 브로커 추상화 계층 필수

**권장**: 키움 대신 **한국투자증권으로 단일화** (크로스 플랫폼 장점)

### 8.3 배포 환경

#### Docker 배포 (권장)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 한국투자증권 API 라이브러리 설치
RUN pip install python-kis

COPY . .

CMD ["python", "main.py"]
```

#### 클라우드 배포
- ✅ AWS EC2 (Linux)
- ✅ Google Cloud Compute Engine
- ✅ Azure VM
- ✅ Heroku
- ✅ Digital Ocean

**키움증권 대비 장점**: Windows 서버 불필요 → **비용 절감**

### 8.4 테스트 전략

1. **단위 테스트**: 각 브로커 어댑터 독립 테스트
2. **통합 테스트**: 전략 엔진과 브로커 연동 테스트
3. **모의투자 테스트**: 실제 API로 1개월 이상 검증
4. **페이퍼 트레이딩**: 실시간 데이터 + 가상 자금
5. **실전 투자**: 소액으로 시작

## 9. 한국투자증권 vs 키움증권 비교

### 9.1 종합 비교표

| 항목 | 키움증권 OpenAPI+ | 한국투자증권 KIS Developers | 우위 |
|------|------------------|---------------------------|------|
| **플랫폼** | Windows 전용 | Windows/Linux/macOS | ⭐⭐⭐ 한투 |
| **아키텍처** | 32-bit 전용 | 64-bit 지원 | ⭐⭐⭐ 한투 |
| **기술 스택** | ActiveX/COM | REST API + WebSocket | ⭐⭐⭐ 한투 |
| **국내주식** | ✅ 완벽 지원 | ✅ 완벽 지원 | 동등 |
| **해외주식** | ❌ 미지원 (HTS만) | ✅ 완벽 지원 (미국/홍콩/일본/중국) | ⭐⭐⭐ 한투 |
| **호출 제한** | 1초당 5회 | 1초당 15회 | ⭐⭐ 한투 |
| **분봉 데이터** | 160일 (60,000분) | 당일만 | ⭐⭐ 키움 |
| **일봉 데이터** | 무제한 | 무제한 | 동등 |
| **실시간 데이터** | ✅ | ✅ (WebSocket) | 동등 |
| **모의투자** | ✅ | ✅ | 동등 |
| **커뮤니티** | ⭐⭐⭐ 매우 활발 | ⭐⭐ 성장 중 | ⭐ 키움 |
| **API 이용료** | 무료 | 무료 | 동등 |
| **Docker 배포** | ❌ (Windows Container 복잡) | ✅ 간단 | ⭐⭐⭐ 한투 |
| **GUI 의존성** | PyQt5/PySide2 필수 | 불필요 | ⭐⭐⭐ 한투 |
| **타입 힌팅** | ⚠️ 라이브러리 의존 | ✅ python-kis 완벽 | ⭐⭐ 한투 |

### 9.2 장단점 요약

#### 한국투자증권 장점
- ✅ **크로스 플랫폼**: 어디서나 실행 가능
- ✅ **해외주식 지원**: 미국/홍콩/일본 등 API로 자동매매
- ✅ **현대적 기술**: REST API + WebSocket
- ✅ **배포 용이**: Docker, 클라우드 친화적
- ✅ **느슨한 제한**: 1초당 15회
- ✅ **타입 안전성**: python-kis 라이브러리 우수

#### 한국투자증권 단점
- ❌ **분봉 제약**: 당일만 (키움 160일 대비)
- ❌ **신규 플랫폼**: 2022년 시작 (키움 대비 짧은 역사)
- ❌ **커뮤니티**: 키움 대비 작음 (하지만 빠르게 성장 중)

#### 키움증권 장점
- ✅ **분봉 데이터**: 160일 (60,000분)
- ✅ **커뮤니티**: 매우 활발, 자료 풍부
- ✅ **안정성**: 오랜 역사

#### 키움증권 단점
- ❌ **Windows 전용**: 크로스 플랫폼 불가
- ❌ **32-bit 전용**: 메모리 제약
- ❌ **해외주식 미지원**: API 없음
- ❌ **ActiveX**: 구식 기술
- ❌ **GUI 의존**: PyQt5 필수
- ❌ **엄격한 제한**: 1초당 5회

### 9.3 사용 사례별 권장

| 사용 사례 | 권장 브로커 | 이유 |
|----------|-----------|------|
| 국내주식 only + Windows 환경 | 키움 또는 한투 | 둘 다 가능, 분봉 필요 시 키움 |
| 국내주식 + 해외주식 | ⭐⭐⭐ 한투 | 해외주식 API 지원 |
| 크로스 플랫폼 배포 | ⭐⭐⭐ 한투 | Linux/macOS/Docker 지원 |
| 클라우드 배포 | ⭐⭐⭐ 한투 | Linux 서버 사용 가능 |
| 대량 분봉 데이터 수집 | 키움 | 160일 분봉 vs 당일 |
| 모던 기술 스택 | ⭐⭐⭐ 한투 | REST API + 타입힌팅 |

## 10. 학습 리소스

### 10.1 공식 문서

- [KIS Developers 포털](https://apiportal.koreainvestment.com/intro) - 공식 개발자 센터
- [API 문서](https://apiportal.koreainvestment.com/apiservice) - API 상세 문서
- [공식 GitHub 샘플](https://github.com/koreainvestment/open-trading-api) - 100+ 샘플 코드
- [ChatGPT GPTs 통합](https://apiportal.koreainvestment.com/intro) - 24/7 AI 도우미

### 10.2 Python 라이브러리 문서

- [python-kis GitHub](https://github.com/Soju06/python-kis) - 가장 인기 있는 라이브러리
- [python-kis Wiki](https://github.com/Soju06/python-kis/wiki/Tutorial) - 튜토리얼
- [mojito2 GitHub](https://github.com/sharebook-kr/mojito) - 초보자 친화적 라이브러리
- [pykis GitHub](https://github.com/pjueon/pykis) - 9개 해외 거래소 지원

### 10.3 커뮤니티 리소스

- [WikiDocs - 한국투자증권 오픈API](https://wikidocs.net/165185) - 한국/미국 주식 자동매매
- [WikiDocs - KIS Developers 소개](https://wikidocs.net/159296) - 초급 예제
- [WikiDocs - 모히토 모듈](https://wikidocs.net/165190) - mojito 사용법
- [WikiDocs - WebSocket 사용](https://wikidocs.net/164056) - 실시간 데이터

### 10.4 기술 블로그

- [쓰로틀링 대응 전략](https://hky035.github.io/web/kis-api-throttling/) - Rate Limit 관리
- [자동매매 시스템 개발 튜토리얼](https://tgparkk.github.io/stock/2025/03/08/auto-stock-1-init.html)

### 10.5 비교 자료

- 키움증권 조사 보고서: [docs/kiwoom_api_research.md](kiwoom_api_research.md)

## 11. 결론 및 권장사항

### 11.1 한국투자증권 API 평가

#### 장점
- ✅ **크로스 플랫폼**: Linux/macOS/Docker 지원으로 배포 자유도 높음
- ✅ **해외주식 지원**: 미국/홍콩/일본/중국 등 API로 자동매매 가능
- ✅ **현대적 기술**: REST API + WebSocket + OAuth 2.0
- ✅ **타입 안전성**: python-kis 라이브러리 타입힌팅 완벽
- ✅ **느슨한 제한**: 1초당 15회 (키움 5회 대비)
- ✅ **무료 제공**: API 이용료 없음
- ✅ **모의투자**: 리스크 없이 전략 검증 가능

#### 단점
- ❌ **분봉 제약**: 당일만 (키움 160일 대비)
- ❌ **신규 플랫폼**: 2022년 시작 (안정성 검증 필요)
- ❌ **커뮤니티**: 키움 대비 작음 (하지만 빠르게 성장)

### 11.2 프로젝트 통합 권장사항

#### ⭐ 최우선 권장: 한국투자증권 단일 통합

```
현재 프로젝트 (CCXT 암호화폐)
    ↓
    + 한국투자증권 API 통합
    ↓
멀티-에셋 트레이딩 봇
    ├── 암호화폐 (CCXT)
    └── 주식 (한국투자증권)
        ├── 국내주식 (코스피/코스닥)
        └── 해외주식 (미국/홍콩/일본/중국)
```

**이유**:
1. ✅ 크로스 플랫폼으로 현재 프로젝트와 호환
2. ✅ 해외주식까지 커버 (키움 불가능)
3. ✅ Docker/클라우드 배포 용이
4. ✅ 단일 코드베이스 유지 가능

#### 단계별 통합 계획 (Phase 1-3)

**Phase 1: 기반 구축 (1-2주)**
1. python-kis 설치 및 테스트
2. 브로커 추상화 계층 설계
3. KoreaInvestmentBroker 어댑터 구현
4. 모의투자 계정으로 인증 테스트

**Phase 2: 국내주식 통합 (2-3주)**
1. 국내주식 데이터 핸들러 구현
2. 기존 전략을 국내주식에 적용
3. 백테스팅 프레임워크 확장
4. 모의투자에서 충분한 테스트

**Phase 3: 해외주식 확장 (2-3주)**
1. 해외주식 데이터 핸들러 구현
2. 환율 리스크 관리 로직 추가
3. 멀티-에셋 포트폴리오 최적화
4. 통합 대시보드 구현

**Phase 4: 프로덕션 배포 (1-2주)**
1. Docker 이미지 빌드
2. 클라우드 배포 (AWS/GCP 등)
3. 모니터링 시스템 구축
4. 실전 투자 (소액 시작)

### 11.3 키움증권 vs 한국투자증권 선택 가이드

#### 한국투자증권 선택 ⭐⭐⭐ (강력 권장)
- ✅ 해외주식 자동매매 필요
- ✅ Linux/macOS 환경에서 개발
- ✅ Docker/클라우드 배포 계획
- ✅ 크로스 플랫폼 확장성 중요
- ✅ 현대적 기술 스택 선호
- ✅ 분봉 당일 데이터로 충분

#### 키움증권 선택 (특정 상황)
- ⚠️ Windows 전용 환경 확정
- ⚠️ 국내주식만 거래
- ⚠️ 160일 분봉 데이터 필수
- ⚠️ 32-bit 환경 수용 가능

#### ⭐ 본 프로젝트 최종 권장: 한국투자증권

**근거**:
1. 프로젝트가 이미 **크로스 플랫폼** (Python)
2. **해외주식** 지원으로 글로벌 시장 진출 가능
3. **Docker 배포**로 클라우드 확장 용이
4. **REST API**가 CCXT와 유사한 구조 → 통합 용이
5. **타입 안전성** (python-kis)으로 코드 품질 향상

### 11.4 다음 단계

#### 즉시 실행
1. [한국투자증권 계좌 개설](https://securities.koreainvestment.com)
2. [KIS Developers 서비스 신청](https://apiportal.koreainvestment.com)
3. 모의투자 계정 생성
4. python-kis 설치: `pip install python-kis`

#### 단기 (1-2주)
5. 브로커 추상화 인터페이스 설계 문서 작성
6. KoreaInvestmentBroker 어댑터 프로토타입 구현
7. 모의투자에서 시세 조회 + 주문 테스트

#### 중기 (1-2개월)
8. 기존 전략을 국내주식에 적용 및 백테스트
9. 해외주식 지원 추가 (미국 우선)
10. 통합 대시보드 구현

#### 장기 (3-6개월)
11. 프로덕션 배포 및 모니터링
12. 멀티-에셋 포트폴리오 최적화
13. 실전 투자 및 지속적 개선

### 11.5 최종 의견

한국투자증권 OpenAPI는 **대한민국 증권사 최초의 REST API 기반 오픈 트레이딩 플랫폼**으로, 크로스 플랫폼 지원과 해외주식 거래 기능으로 키움증권의 한계를 극복했습니다.

본 프로젝트는 이미 Python 기반 크로스 플랫폼 구조이므로, 한국투자증권 API 통합 시 **최소한의 아키텍처 변경**으로 국내주식 + 해외주식까지 확장 가능합니다.

**최종 권장사항**: 키움증권 대신 **한국투자증권 API**를 선택하여, 멀티-에셋 (암호화폐 + 국내주식 + 해외주식) 트레이딩 봇으로 발전시키는 것을 강력히 권장합니다.

---

## Sources

### 공식 문서
- [KIS Developers 포털](https://apiportal.koreainvestment.com/intro)
- [API 문서 - 해외주식주문](https://apiportal.koreainvestment.com/apiservice/apiservice-overseas-stock)
- [GitHub 공식 샘플 코드](https://github.com/koreainvestment/open-trading-api)
- [한국투자증권 서비스 안내](https://securities.koreainvestment.com/main/customer/systemdown/OpenAPI.jsp)

### Python 라이브러리
- [python-kis GitHub](https://github.com/Soju06/python-kis)
- [python-kis PyPI](https://pypi.org/project/python-kis/)
- [mojito2 GitHub](https://github.com/sharebook-kr/mojito)
- [mojito2 PyPI](https://pypi.org/project/mojito2/)
- [pykis GitHub](https://github.com/pjueon/pykis)

### 커뮤니티 리소스
- [WikiDocs - 한국투자증권 오픈API](https://wikidocs.net/165185)
- [WikiDocs - KIS Developers 소개](https://wikidocs.net/159296)
- [WikiDocs - 모히토 모듈](https://wikidocs.net/165190)
- [WikiDocs - 오픈API 서비스 신청](https://wikidocs.net/165188)

### 기술 블로그
- [쓰로틀링 대응 전략](https://hky035.github.io/web/kis-api-throttling/)
- [자동매매 시스템 개발 튜토리얼](https://tgparkk.github.io/stock/2025/03/08/auto-stock-1-init.html)

### 수수료 정보
- [한국투자증권 수수료안내](https://securities.koreainvestment.com/main/customer/guide/_static/TF04ae010000.jsp)
- [시장별 매매안내](https://www.truefriend.com/main/bond/research/_static/TF03ca050000.jsp)

**작성일**: 2026-02-07
**작성자**: korea-investment-researcher (trading-dev team)
