# trading_bot/market_intelligence/ - 5-Layer 시장 인텔리전스 엔진

> **상위 문서**: [루트 CLAUDE.md](../../CLAUDE.md)를 먼저 참조하세요.

## 목적

ETF 프록시 기반의 수치적 시장 분석 시스템. 모든 계산은 Python(numpy/pandas)에서 수행하며,
Claude는 결과 해석만 담당합니다.

## 디렉토리 구조

```
market_intelligence/
├── __init__.py              # 패키지 공개 API
├── base_layer.py            # LayerResult, BaseIntelligenceLayer (ABC)
├── scoring.py               # 공유 점수 유틸리티 (percentile, z-score, RSI 등)
├── data_fetcher.py          # MarketDataCache (yfinance 통합)
├── layer1_macro_regime.py   # Layer 1: 매크로 레짐 (금리/신용/달러/제조업)
├── layer2_market_structure.py # Layer 2: 시장 구조 (VIX/breadth/McClellan)
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
| `SentimentLayer` | layer5_sentiment.py | 심리 + 포지셔닝 분석 |
| `MarketIntelligence` | __init__.py | 5-Layer 오케스트레이터 + 포지션 사이징 추천 |

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

## 테스트

```bash
python3 -m pytest tests/test_market_intelligence/ -v 2>&1 | tee .context/terminal/test_mi_$(date +%s).log
```
