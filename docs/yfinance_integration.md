# yfinance 통합 가이드

## 개요

Real-time Quotes 탭에서 **모든 미국 주식**을 조회할 수 있도록 yfinance 통합이 완료되었습니다.

기존에는 `stock_symbols.py`에 하드코딩된 ~100개 종목만 조회 가능했지만, 이제 PLTR, SHOP, COIN, UBER, ABNB, RBLX 등 **모든 미국 상장 주식**을 직접 입력하여 조회할 수 있습니다.

---

## 주요 변경사항

### 1. 새로운 파일

#### `dashboard/yfinance_helper.py`
yfinance API를 사용한 주식 데이터 조회 헬퍼 모듈

**주요 함수**:
- `fetch_ticker_yfinance(symbol)`: 실시간 시세 조회
- `fetch_ohlcv_yfinance(symbol, period, interval)`: OHLCV 데이터 조회
- `get_company_info(symbol)`: 회사 정보 조회
- `validate_symbol(symbol)`: 종목 심볼 유효성 검증

### 2. 수정된 파일

#### `dashboard/app.py`
Real-time Quotes 탭에 직접 입력 기능 추가

**주요 변경**:
- 종목 선택 방법 추가: "📋 목록에서 선택" vs "⌨️ 직접 입력 (모든 미국 주식)"
- Ticker 조회 로직: KIS API 우선 시도 → 실패 시 yfinance fallback
- OHLCV 조회 로직: KIS API 우선 시도 → 실패 시 yfinance fallback
- 데이터 소스 표시: "KIS API" 또는 "Yahoo Finance (yfinance)"

#### `requirements.txt`
yfinance 패키지 추가
```
yfinance>=0.2.50
```

---

## 사용 방법

### 1. 대시보드 실행

```bash
streamlit run dashboard/app.py
```

### 2. Real-time Quotes 탭 이동

좌측 사이드바에서 "Real-time Quotes" 탭 선택

### 3. 종목 선택 방법 선택

#### 방법 1: 목록에서 선택 (기존)
- "📋 목록에서 선택" 라디오 버튼 선택
- 드롭다운에서 종목 선택 (AAPL, MSFT, GOOGL 등)
- KIS API로 데이터 조회 (실패 시 yfinance로 자동 fallback)

#### 방법 2: 직접 입력 (신규 ✨)
- "⌨️ 직접 입력 (모든 미국 주식)" 라디오 버튼 선택
- 텍스트 입력창에 종목 심볼 입력 (예: PLTR, SHOP, COIN)
- 자동으로 yfinance로 데이터 조회
- 유효성 검증 후 조회 (유효하지 않은 심볼은 에러 표시)

### 4. 실시간 시세 확인

- 현재가, 시가, 고가, 저가, 거래량 표시
- 변동률 표시 (빨간색: 상승, 파란색: 하락)
- 데이터 소스 표시 (KIS API 또는 Yahoo Finance)

### 5. OHLCV 차트 확인

- 기간 선택: 30일, 90일, 180일
- 캔들스틱 차트 + 거래량 차트 표시
- 상승일: 초록색, 하락일: 빨간색
- 인터랙티브 줌/패닝 지원

---

## 예시 종목

### 기존 목록에 없던 인기 종목

| 심볼 | 회사명 | 섹터 |
|------|--------|------|
| PLTR | Palantir Technologies | Technology |
| SHOP | Shopify | Technology |
| COIN | Coinbase Global | Financial Services |
| UBER | Uber Technologies | Consumer Cyclical |
| ABNB | Airbnb | Consumer Cyclical |
| RBLX | Roblox Corporation | Communication Services |
| SNOW | Snowflake | Technology |
| DDOG | Datadog | Technology |
| NET | Cloudflare | Technology |
| CRWD | CrowdStrike | Technology |

---

## 기술 구조

### Ticker 조회 플로우

```
사용자가 심볼 입력
    ↓
선택 방법 확인
    ↓
"목록에서 선택" → KIS API 시도 → 성공 → 표시
                        ↓ 실패
                    yfinance fallback → 표시
    ↓
"직접 입력" → yfinance 조회 → 유효성 검증 → 표시
```

### OHLCV 조회 플로우

```
사용자가 기간 선택 (30일/90일/180일)
    ↓
선택 방법 확인
    ↓
"목록에서 선택" → KIS API 시도 (limit=days) → 성공 → 차트 표시
                        ↓ 실패
                    yfinance fallback (period='1mo/3mo/6mo') → 차트 표시
    ↓
"직접 입력" → yfinance 조회 (period='1mo/3mo/6mo') → 차트 표시
```

### 기간 변환 매핑

| 사용자 선택 | KIS API | yfinance |
|-------------|---------|----------|
| 30일 | limit=30 | period='1mo' |
| 90일 | limit=90 | period='3mo' |
| 180일 | limit=180 | period='6mo' |

---

## 장점

### 1. 무제한 종목 지원
- 기존: ~100개 하드코딩된 종목만 조회 가능
- 현재: 모든 미국 상장 주식 조회 가능

### 2. 안정성
- KIS API 장애 시 자동으로 yfinance로 fallback
- 두 데이터 소스를 redundancy로 활용

### 3. 사용자 친화성
- 직접 입력 방식으로 원하는 종목 즉시 조회
- 유효성 검증으로 잘못된 심볼 입력 방지
- 데이터 소스 투명하게 표시

### 4. 무료
- yfinance는 Yahoo Finance API를 사용하여 완전 무료
- API 키 불필요

---

## 주의사항

### 1. 데이터 정확도
- yfinance는 Yahoo Finance 데이터를 사용하므로 약간의 지연이 있을 수 있음
- 실전 트레이딩에는 KIS API 사용 권장

### 2. API Rate Limit
- yfinance는 공식 API가 아니므로 과도한 호출은 차단될 수 있음
- Auto-refresh는 60초 간격으로 설정하여 제한 회피

### 3. 시장 시간
- yfinance는 24/7 조회 가능하지만, 장 마감 시간에는 이전 종가 표시
- 실시간 데이터는 장 중에만 업데이트

---

## 테스트

### 단위 테스트

```bash
# yfinance helper 함수 테스트
python test_yfinance.py

# 통합 테스트 (ticker + OHLCV)
python test_yfinance_integration.py
```

### 수동 테스트

1. 대시보드 실행
2. Real-time Quotes 탭 이동
3. "⌨️ 직접 입력" 선택
4. PLTR 입력 → 시세 확인
5. OHLCV 차트 확인 (30일/90일/180일)
6. SHOP, COIN, UBER 등 다른 종목 시도

---

## 향후 개선 사항

### 1. 캐싱
현재는 매 요청마다 API 호출. 60초 TTL 캐싱으로 중복 호출 방지

```python
@st.cache_data(ttl=60)
def fetch_ticker_cached(symbol):
    return fetch_ticker_yfinance(symbol)
```

### 2. 종목 자동완성
사용자가 입력 시 자동완성 제안 (예: "A" 입력 → AAPL, AMZN, AMD 제안)

### 3. 다중 종목 비교
한 화면에 여러 종목의 차트를 동시 표시

### 4. Paper Trading 탭 통합
Paper Trading 탭에도 직접 입력 기능 추가

---

## 관련 파일

- `dashboard/yfinance_helper.py`: yfinance 헬퍼 모듈
- `dashboard/app.py`: Real-time Quotes 탭 (line 1794-2127)
- `test_yfinance.py`: 단위 테스트
- `test_yfinance_integration.py`: 통합 테스트
- `requirements.txt`: 의존성 목록

---

## 기여자

- yfinance 통합: Claude Sonnet 4.5 (2026-02-09)

---

## 라이선스

이 프로젝트는 기존 프로젝트 라이선스를 따릅니다.
