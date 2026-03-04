# Multi-Asset Trading Bot

Python 기반 멀티-마켓 자동매매 봇. 암호화폐 + 해외주식 백테스팅, 전략 최적화, 페이퍼 트레이딩, 5-Layer 시장 인텔리전스, TradingView Pine Script 자동 생성까지 지원합니다.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Streamlit Dashboard                            │
│   실시간 시세 │ 백테스트 │ 페이퍼트레이딩 │ 전략비교 │ 스케줄러 관리     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      Scheduler (APScheduler)                           │
│   미국 시장 시간 자동 실행 (23:30-06:00 KST) │ 멀티 프리셋 세션        │
│   장 마감 → 분석 리포트 → Notion 작성 → Slack 전송 → Pine Script       │
└──────────┬─────────────────────┬────────────────────┬──────────────────┘
           │                     │                    │
┌──────────▼──────────┐ ┌───────▼─────────┐ ┌────────▼───────────────────┐
│   Paper Trader      │ │ Market Analyzer │ │  Pine Script Generator     │
│ 멀티심볼 실시간 매매 │ │ KIS + 기술지표  │ │  JSON → Pine v6 변환       │
│ Stop Loss/Take Profit│ │ + Notion 리포트 │ │  LLM 코멘터리 / 폴백       │
│ SQLite 세션 추적     │ │                 │ │                            │
└──────────┬──────────┘ └───────┬─────────┘ └────────────────────────────┘
           │                    │
┌──────────▼────────────────────▼────────────────────────────────────────┐
│                     Market Intelligence                                │
│   5-Layer 시장 분석 엔진 (매크로/구조/섹터/기술적/센티먼트)              │
│   + 이벤트 캘린더 (15종) + Fear & Greed + 뉴스 + 펀더멘탈              │
└──────────┬─────────────────────────────────────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────────────────────────────┐
│                      Strategy Layer                                    │
│   RSI │ MACD │ Bollinger │ Stochastic │ RSI+MACD Combo │ MA Cross     │
│   BaseStrategy (ABC) │ StrategyRegistry │ SignalValidator              │
└──────────┬─────────────────────────────────────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────────────────────────────┐
│                      Execution Layer                                   │
│   Backtester │ VBT Backtester │ Optimizer │ ExecutionVerifier          │
└──────────┬─────────────────────────────────────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────────────────────────────┐
│                       Broker Layer                                     │
│   BaseBroker (통합 인터페이스)                                          │
│   ├── CCXTBroker (100+ 암호화폐 거래소)                                 │
│   ├── KoreaInvestmentBroker (국내/해외주식)                             │
│   └── yfinance (시장 데이터)                                           │
└────────────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름

```
[시장 데이터]                    [시장 인텔리전스]
 KIS API / yfinance               5-Layer 분석
 SimulationDataGenerator           뉴스 / Fear & Greed
       │                                │
       ▼                                ▼
  OHLCV DataFrame ──────────→ RegimeDetector (시장 레짐)
       │                                │
       ▼                                ▼
  Strategy.calculate_indicators() ← LLM 시그널 필터
       │
       ▼
  SignalValidator (시그널 검증)
       │
       ▼
  Backtester / PaperTrader (실행)
       │
       ▼
  PerformanceMetrics → 리포트 → Notion / Slack
```

---

## 주요 기능

### 페이퍼 트레이딩

- 멀티 심볼 실시간 모의 매매 (최대 7종목 동시)
- Stop Loss / Take Profit 자동 관리
- 지정가 주문 지원
- SQLite 세션 추적 (거래 내역, 포트폴리오 스냅샷, 성과 지표)
- 전략 프리셋 저장/불러오기 (JSON)
- Streamlit 대시보드 통합 (실시간 시세, 백테스트, 전략 비교)

### 자동화 스케줄러

- APScheduler 기반 크론 스케줄링
- 미국 시장 시간 자동 실행 (23:30~06:00 KST)
- 멀티 프리셋 동시 세션 (`--presets "A" "B" "C"`)
- 장 마감 후 일일 리포트 자동 생성 (CSV/JSON)
- Slack Webhook + Bot Token 파일 업로드
- Email SMTP 알림

### 시장 인텔리전스 (5-Layer 분석)

**5-Layer 분석 엔진**

| Layer | 분석 영역 | 주요 지표 |
|-------|-----------|----------|
| Layer 1 | 매크로 레짐 | 금리, 신용 스프레드, 달러 인덱스, 제조업 PMI |
| Layer 2 | 시장 구조 | VIX, 시장 폭(Breadth), McClellan Oscillator |
| Layer 3 | 섹터/팩터 로테이션 | 섹터별 상대 강도, 팩터 성과 |
| Layer 4 | 개별 종목 기술적 분석 | RSI, MACD, 볼린저밴드, 지지/저항선 |
| Layer 5 | 센티먼트 & 포지셔닝 | Fear & Greed, 뉴스 감성 분석, 포지션 데이터 |

**이벤트 캘린더 (15종)**
- FOMC / FOMC 의사록 / CPI / PPI / NFP / PCE / GDP
- ISM 제조업 / ISM 서비스업 / 잭슨홀 심포지엄
- 월간 옵션 만기 / Quad Witching / VIX 만기
- S&P 500 / Russell 리밸런싱 / NYSE 공휴일

**데이터 수집기**
- `MarketAnalyzer` — KIS API + 기술적 지표 수집
- `NewsCollector` — Google News RSS 뉴스 수집
- `FearGreedCollector` — CNN Fear & Greed Index + 차트 생성
- `FundamentalCollector` — 펀더멘탈 데이터 수집
- `SentimentAnalyzer` — 뉴스 감성 분석

**분석 & 리포팅**
- `RegimeDetector` — ADX 기반 시장 레짐 감지 (BULLISH / BEARISH / SIDEWAYS / VOLATILE)
- `LLMClient` — vLLM 연동 시그널 필터
- `SignalValidator` — 시그널 유효성 검증
- Notion 자동 리포트 (Claude CLI 통합)

### 백테스팅 & 최적화

- **Backtester** — 히스토리컬 데이터 기반 시뮬레이션 (커미션, 슬리피지 반영)
- **VBTBacktester** — vectorbt 기반 벡터화 백테스터 (고속)
- **StrategyOptimizer** — 그리드 서치 파라미터 최적화
- **SimulationDataGenerator** — GBM(기하 브라운 운동) 기반 합성 데이터 생성
- 성과 지표: 수익률, 샤프 비율, 최대 낙폭, 승률

### Pine Script 자동 생성

- 시장 분석 JSON → TradingView Pine Script v6 통합 지표
- LLM 코멘터리 (Claude CLI) + 규칙 기반 폴백
- 종목별 최적 RSI, 레짐, 지지선, 패턴 자동 삽입
- 이벤트 근접도 기반 코멘트/전략/알림 반영
- Slack 자동 전송

---

## 트레이딩 전략

| 전략 | 로직 | 파라미터 |
|------|------|----------|
| MA Crossover | Fast MA ↑ Slow MA → BUY | `fast_period`, `slow_period` |
| RSI | RSI < oversold → BUY, RSI > overbought → SELL | `period`, `overbought`, `oversold` |
| MACD | MACD ↑ Signal → BUY | `fast_period`, `slow_period`, `signal_period` |
| Bollinger Bands | Price → Lower Band → BUY | `period`, `std_dev` |
| Stochastic | %K ↑ %D (oversold) → BUY | `k_period`, `d_period`, `overbought`, `oversold` |
| RSI+MACD Combo | RSI 과매도 AND MACD 골든크로스 → BUY | RSI + MACD 파라미터 결합 |

모든 전략은 `BaseStrategy(ABC)`를 상속하며 `StrategyRegistry`로 이름 기반 조회 가능.

---

## 설치

### Docker (권장)

```bash
git clone <repository-url>
cd quant
cp .env.example .env   # API 키 설정

docker compose up -d
# 대시보드: http://localhost:8501
```

### 로컬 설치

```bash
pip install -r requirements.txt

# 대시보드 실행
streamlit run dashboard/app.py

# 스케줄러 실행
python scheduler.py --presets "프리셋1" "프리셋2"
```

---

## 환경 변수 (.env)

```bash
# 한국투자증권 API
KIS_APPKEY=your_appkey
KIS_APPSECRET=your_appsecret
KIS_ACCOUNT=12345678-01
KIS_MOCK=true

# 분석 대상 종목
MARKET_ANALYSIS_SYMBOLS=AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT

# Notion 연동
NOTION_MARKET_ANALYSIS_PAGE_ID=your_page_id

# Slack 알림
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL=C0123456789

# LLM (선택)
LLM_SIGNAL_URL=http://localhost:8000/v1/chat/completions
LLM_REGIME_URL=http://localhost:8001/v1/chat/completions
LLM_ENABLED=true
```

---

## 사용법

### 백테스팅

```python
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies import RSIStrategy
from trading_bot.backtester import Backtester

data_gen = SimulationDataGenerator(seed=42)
df = data_gen.generate_trend_data(periods=1000, trend='bullish')

strategy = RSIStrategy(period=14, overbought=70, oversold=30)
backtester = Backtester(strategy, initial_capital=10000)
results = backtester.run(df)
backtester.print_results(results)
```

### 전략 최적화

```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies import RSIStrategy

param_grid = {
    'period': [7, 14, 21],
    'overbought': [65, 70, 75],
    'oversold': [25, 30, 35],
}
optimizer = StrategyOptimizer(initial_capital=10000)
best = optimizer.optimize(RSIStrategy, df, param_grid)
print(f"최적 파라미터: {best['params']}, 수익률: {best['total_return']:.2f}%")
```

### 페이퍼 트레이딩

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from trading_bot.database import TradingDatabase
from dashboard.kis_broker import get_kis_broker

trader = PaperTrader(
    strategy=RSIStrategy(period=14),
    symbols=['AAPL', 'MSFT', 'GOOGL'],
    broker=get_kis_broker(),
    initial_capital=10000.0,
    position_size=0.3,
    stop_loss_pct=0.03,
    take_profit_pct=0.06,
    db=TradingDatabase(),
)
trader.run_realtime(interval_seconds=60, timeframe='1d')
```

### 시장 분석 + Notion 리포트

```bash
python scripts/run_market_analysis.py
```

### Pine Script 생성

```bash
# LLM 코멘터리 포함
python scripts/generate_pine_script.py

# 규칙 기반만
python scripts/generate_pine_script.py --no-llm

# Slack 전송
python scripts/generate_pine_script.py --slack
```

### 스케줄러

```bash
python scheduler.py --presets "보수적RSI" "공격적MACD"
python scheduler.py --list-presets
```

---

## 프로젝트 구조

```
quant/
├── trading_bot/                        # 핵심 패키지
│   ├── strategies/                     #   전략 구현
│   │   ├── base_strategy.py            #     BaseStrategy (ABC)
│   │   ├── rsi_strategy.py             #     RSI 전략
│   │   ├── macd_strategy.py            #     MACD 전략
│   │   ├── bollinger_bands_strategy.py #     볼린저밴드 전략
│   │   ├── stochastic_strategy.py      #     스토캐스틱 전략
│   │   └── rsi_macd_combo_strategy.py  #     RSI+MACD 콤보 전략
│   ├── brokers/                        #   브로커 통합
│   │   ├── base_broker.py              #     BaseBroker (통합 인터페이스)
│   │   ├── ccxt_broker.py              #     CCXT (100+ 거래소)
│   │   └── korea_investment_broker.py  #     한국투자증권 (KIS)
│   ├── market_intelligence/            #   5-Layer 시장 분석 엔진
│   │   ├── layer1_macro_regime.py      #     매크로 레짐
│   │   ├── layer2_market_structure.py  #     시장 구조
│   │   ├── layer3_sector_rotation.py   #     섹터 로테이션
│   │   ├── layer4_technicals.py        #     기술적 분석
│   │   ├── layer5_sentiment.py         #     센티먼트
│   │   ├── scoring.py                  #     종합 스코어링
│   │   └── data_fetcher.py             #     데이터 수집
│   ├── scheduler/                      #   스케줄러 코어
│   ├── backtester.py                   #   백테스팅 엔진
│   ├── vbt_backtester.py               #   vectorbt 백테스터
│   ├── optimizer.py                    #   전략 최적화 (그리드 서치)
│   ├── paper_trader.py                 #   페이퍼 트레이딩
│   ├── database.py                     #   SQLite 트레이딩 DB
│   ├── market_analyzer.py              #   일일 시장 분석
│   ├── market_analysis_prompt.py       #   LLM 프롬프트 빌더
│   ├── event_calendar.py               #   이벤트 캘린더 (15종)
│   ├── news_collector.py               #   뉴스 수집 (Google RSS)
│   ├── fear_greed_collector.py         #   Fear & Greed 수집
│   ├── fundamental_collector.py        #   펀더멘탈 수집
│   ├── sentiment_analyzer.py           #   뉴스 감성 분석
│   ├── regime_detector.py              #   시장 레짐 감지 (ADX)
│   ├── llm_client.py                   #   LLM 시그널 필터 (vLLM)
│   ├── signal_validator.py             #   시그널 유효성 검증
│   ├── signal_pipeline.py              #   시그널 파이프라인
│   ├── signal_tracker.py               #   시그널 추적
│   ├── execution_verifier.py           #   주문 실행 검증
│   ├── notifications.py                #   Slack/Email 알림
│   ├── strategy_presets.py             #   프리셋 관리
│   ├── strategy_registry.py            #   전략 레지스트리
│   ├── risk_manager.py                 #   리스크 관리
│   ├── portfolio_manager.py            #   포트폴리오 관리
│   ├── order_executor.py               #   주문 실행기
│   ├── limit_order.py                  #   지정가 주문
│   ├── anomaly_detector.py             #   이상치 탐지
│   ├── performance_calculator.py       #   성과 계산
│   ├── simulation_data.py              #   시뮬레이션 데이터 (GBM)
│   ├── reports.py                      #   일일 리포트 생성
│   ├── health.py                       #   헬스체크
│   └── config.py                       #   설정 관리
├── dashboard/                          # Streamlit 대시보드
│   ├── app.py                          #   메인 앱
│   ├── tabs/                           #   탭 모듈
│   │   ├── backtest.py                 #     백테스트 탭
│   │   ├── realtime_quotes.py          #     실시간 시세 탭
│   │   ├── paper_trading.py            #     페이퍼 트레이딩 탭
│   │   ├── strategy_comparison.py      #     전략 비교 탭
│   │   ├── live_monitor.py             #     라이브 모니터링 탭
│   │   └── scheduler.py               #     스케줄러 관리 탭
│   └── components/                     #   공유 UI 컴포넌트
├── scripts/                            # 유틸리티 스크립트
│   ├── generate_pine_script.py         #   Pine Script 생성기
│   ├── run_market_analysis.py          #   시장 분석 수동 실행
│   ├── notion_writer.py                #   Notion 작성
│   ├── ralph/                          #   Ralph 자율 코딩 에이전트
│   └── deploy/                         #   배포 스크립트
├── tests/                              # 테스트 (1,499개)
├── examples/                           # 예제 스크립트
├── data/                               # 데이터 (분석 JSON, 프리셋, DB)
│   └── market_analysis/                #   일일 시장 분석 결과
├── scheduler.py                        # 자동화 스케줄러 엔트리포인트
├── docker-compose.yml                  # Docker 배포
├── Dockerfile
└── requirements.txt
```

---

## Docker 배포

```bash
# 전체 시작 (대시보드 + 스케줄러)
docker compose up -d

# 스케줄러 로그 확인
docker compose logs -f trading-bot-scheduler

# 스케줄러만 중지
docker compose stop trading-bot-scheduler

# 전체 중지
docker compose down
```

| 서비스 | 포트 | 설명 |
|--------|------|------|
| `trading-bot-dashboard` | 8501 | Streamlit 대시보드 |
| `trading-bot-scheduler` | - | 자동매매 스케줄러 |

공유 볼륨: `data/`, `logs/`, `reports/`

---

## 테스트

```bash
# 전체 테스트 (1,499개)
pytest

# slow 테스트 제외 (API 호출 없이)
pytest -m "not slow"

# 커버리지
pytest --cov=trading_bot

# 특정 모듈
pytest tests/test_event_calendar.py -v
pytest tests/test_market_intelligence/ -v
```

---

## 기술 스택

| 분류 | 라이브러리 |
|------|-----------|
| 언어 | Python 3.11+ |
| 데이터 | pandas 2.0+, numpy 1.24+, yfinance 0.2.50+ |
| 브로커 | ccxt 4.0+ (암호화폐), python-kis (주식) |
| 백테스팅 | vectorbt 0.26+ |
| 대시보드 | Streamlit 1.28+, Plotly 5.17+ |
| 시각화 | matplotlib 3.7+, seaborn 0.12+ |
| 스케줄링 | APScheduler 3.10+ |
| 알림 | slack-sdk 3.23+, requests 2.31+ |
| 뉴스 | feedparser 6.0+ |
| 테스트 | pytest 7.4+, pytest-cov 4.1+ |

---

## 개발 현황

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1 | 완료 | 페이퍼 트레이딩 (멀티 심볼, SL/TP, SQLite, 대시보드) |
| Phase 2 | 완료 | 자동화 스케줄러 (APScheduler, Slack/Email, 멀티 프리셋) |
| Phase 3 | 완료 | 시장 인텔리전스 (5-Layer 분석, 이벤트 캘린더, LLM 시그널, Notion) |
| Phase 4 | 진행중 | VBT 마이그레이션 (vectorbt 기반 벡터화 백테스터) |
| Phase 5 | 계획중 | 라이브 트레이딩 (RiskManager, LiveTrader, 2단계 확인 UI) |

---

## 라이선스

MIT License

## 면책 조항

이 소프트웨어는 교육 및 연구 목적으로만 제공됩니다. 실제 자금을 사용하기 전에 충분한 테스트와 리스크 이해가 필요합니다. 투자 손실에 대한 책임은 사용자에게 있습니다.
