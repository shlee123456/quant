# trading_bot/market_intelligence/ - 5-Layer 시장 인텔리전스 엔진

> **상위 문서**: [루트 CLAUDE.md](../../CLAUDE.md)를 먼저 참조하세요.

## 목적

ETF 프록시 기반의 수치적 시장 분석 시스템. 모든 계산은 Python(numpy/pandas)에서 수행하며,
Claude는 결과 해석만 담당합니다.

## 디렉토리 구조

```
market_intelligence/
├── __init__.py              # 패키지 공개 API (US/KR 오케스트레이터)
├── base_layer.py            # LayerResult, BaseIntelligenceLayer (ABC)
├── scoring.py               # 공유 점수 유틸리티 (percentile, z-score, RSI 등)
├── data_fetcher.py          # MarketDataCache (yfinance 통합, US)
├── fred_fetcher.py          # FRED 경제 데이터 (US)
├── cboe_fetcher.py          # CBOE Put/Call Ratio CSV (US 수급)
├── kr_data_fetcher.py       # KRMarketDataCache (yfinance 한국 심볼)
├── bok_fetcher.py           # 한국은행 API (KR 매크로)
├── kr_flow_fetcher.py       # pykrx 투자자 수급 + 공매도 (KR 수급)
├── layer1_macro_regime.py   # Layer 1 US: 매크로 레짐
├── layer2_market_structure.py # Layer 2 US: 시장 구조 (VIX/breadth/McClellan)
├── layer3_sector_rotation.py # Layer 3 US: 섹터/팩터 로테이션
├── layer4_technicals.py     # Layer 4 공통: 기술적 분석
├── layer5_sentiment.py      # Layer 5 US: 심리 + 포지셔닝 (options_flow 포함)
├── kr_layer1_macro_regime.py # Layer 1 KR
├── kr_layer2_market_structure.py # Layer 2 KR (investor_flow 포함)
├── kr_layer3_sector_rotation.py # Layer 3 KR
├── kr_layer5_sentiment.py   # Layer 5 KR (VKOSPI/한글뉴스/원달러)
└── CLAUDE.md                # 이 문서
```

## 핵심 클래스

| 클래스 | 파일 | 역할 |
|--------|------|------|
| `LayerResult` | base_layer.py | 모든 레이어의 표준 출력 (score, signal, confidence) |
| `BaseIntelligenceLayer` | base_layer.py | 레이어 추상 기본 클래스 (ABC) |
| `MarketDataCache` | data_fetcher.py | yfinance 데이터 캐시 (단일 download 호출) |
| `MacroRegimeLayer` | layer1_macro_regime.py | 매크로 환경 분석 (5개 서브 메트릭) |
| `MarketStructureLayer` | layer2_market_structure.py | 시장 구조 분석 (6개 서브 메트릭) |
| `SectorRotationLayer` | layer3_sector_rotation.py | 섹터/팩터 로테이션 분석 |
| `TechnicalsLayer` | layer4_technicals.py | 개별 종목 기술적 분석 |
| `SentimentLayer` | layer5_sentiment.py | US 심리 + 포지셔닝 분석 (options_flow 포함) |
| `KRMacroRegimeLayer` | kr_layer1_macro_regime.py | KR 매크로 레짐 (BOK 기준금리/원달러 등) |
| `KRMarketStructureLayer` | kr_layer2_market_structure.py | KR 시장 구조 (VKOSPI/breadth/investor_flow) |
| `KRSectorRotationLayer` | kr_layer3_sector_rotation.py | KR 섹터 로테이션 (KODEX ETF) |
| `KRSentimentLayer` | kr_layer5_sentiment.py | KR 심리 분석 (VKOSPI/한글뉴스/원달러) |
| `CBOEFetcher` | cboe_fetcher.py | CBOE Put/Call Ratio CSV 수집 (US 수급) |
| `KRFlowFetcher` | kr_flow_fetcher.py | pykrx 투자자 수급 + 시장 공매도 (KR 수급) |
| `FREDDataFetcher` | fred_fetcher.py | FRED 경제 데이터 (US 매크로) |
| `BOKDataFetcher` | bok_fetcher.py | 한국은행 경제 데이터 (KR 매크로) |
| `MarketIntelligence` | __init__.py | 5-Layer 오케스트레이터 (US/KR 분기) + 포지션 사이징 |

## 포지션 사이징 추천

```python
from trading_bot.market_intelligence import MarketIntelligence

mi = MarketIntelligence()
report = mi.analyze(stock_symbols=['AAPL'], ...)
rec = MarketIntelligence.get_position_size_recommendation(
    report, fear_greed_value=20.0  # F&G 지수
)
# rec = {'multiplier': 1.25, 'reason': '극단적 공포(20): +25%', 'adjustments': [...]}
```

멀티플라이어 규칙:
- F&G < 25 (극단적 공포): +0.25
- F&G > 75 (극단적 탐욕): -0.25
- Overall score > +30 (강세): +0.15
- Overall score < -30 (역발상): +0.10
- 최종 범위: clamp(0.5, 1.5)

env: `SENTIMENT_SIZING_ENABLED=false` (기본값)

## 사용법

```python
from trading_bot.market_intelligence import (
    MarketDataCache,
    MacroRegimeLayer,
    MarketStructureLayer,
)

# 1. 데이터 캐시 로드
cache = MarketDataCache(period='6mo')
cache.fetch()

# 2. 레이어 분석
macro = MacroRegimeLayer()
result1 = macro.analyze({'cache': cache})

structure = MarketStructureLayer()
result2 = structure.analyze({'cache': cache})

# 3. 결과 사용
print(result1.score, result1.signal, result1.interpretation)
print(result2.score, result2.signal, result2.interpretation)
```

## 새 레이어 추가

1. `BaseIntelligenceLayer`를 상속
2. `analyze(data) -> LayerResult` 구현
3. `__init__.py`에 export 추가
4. `tests/test_market_intelligence/`에 테스트 작성

## 수급 데이터 (Supply/Demand Flow)

### US: CBOE Put/Call Ratio
```
CBOEFetcher.get_latest()  →  context['pcr_data']  →  SentimentLayer._calc_options_flow()
```
- 환경변수: `CBOE_PCR_ENABLED=true`
- 데이터: CBOE CSV (무료, 인증 불필요)
- 스코어 범위: ±100 (역발상 — 높은 PCR = contrarian bullish)

### KR: 외국인/기관 순매수 + 공매도
```
KRFlowFetcher.get_latest_summary()  →  context['kr_flow_data']  →  KRMarketStructureLayer._score_investor_flow()
KRFlowFetcher.get_short_selling_summary()  →  _score_investor_flow() 내 ±5 보너스
```
- 환경변수: `KR_INVESTOR_FLOW_ENABLED=true`
- 데이터: pykrx (KRX 웹 스크래핑, 무료, YYYYMMDD 형식)
- 스코어 범위: ±100 (aligned_buying/selling ± 규모 보너스 ± 공매도 보너스)
- 공매도는 시장 전체 비율만 사용 (종목별 pykrx 미지원)

## 테스트

```bash
python3 -m pytest tests/test_market_intelligence/ -v 2>&1 | tee .context/terminal/test_mi_$(date +%s).log
```
