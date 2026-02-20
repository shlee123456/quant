# trading_bot/ - 트레이딩 봇 핵심 모듈

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, `trading_bot/` 디렉토리에 특화된 규칙만 정의합니다.

---

## 목적

트레이딩 봇의 핵심 로직을 구현하는 모듈:
- **Data Layer**: 실시간/시뮬레이션 데이터 처리
- **Strategy Layer**: 트레이딩 전략 및 시그널 생성
- **Execution Layer**: 백테스팅 및 페이퍼 트레이딩
- **Optimization Layer**: 전략 파라미터 최적화

---

## 디렉토리 구조

```
trading_bot/
├── __init__.py
├── config.py                    # 설정 관리 (암호화폐 + 해외주식)
├── data_handler.py              # 실시간 데이터 (CCXT, 증권사 API)
├── simulation_data.py           # 시뮬레이션 데이터 생성
├── strategy.py                  # 기본 MA 전략
├── backtester.py                # 백테스팅 엔진
├── optimizer.py                 # 전략 최적화
├── paper_trader.py              # 페이퍼 트레이딩
├── database.py                  # SQLite 데이터베이스 (세션 추적)
├── strategy_presets.py          # 전략 프리셋 관리
├── strategy_registry.py         # 전략 등록/조회 레지스트리
├── signal_validator.py          # 시그널 유효성 검증
├── execution_verifier.py        # 주문 실행 정확성 검증
├── notifications.py             # 알림 서비스 (Slack, Email)
├── regime_detector.py           # 시장 레짐 감지 (ADX, 변동성 기반)
├── llm_client.py                # LLM API 클라이언트 (vLLM, 시그널 필터/레짐 판단)
├── market_analyzer.py           # 일일 시장 데이터 분석 (KIS API + Notion 연동)
├── market_analysis_prompt.py    # 시장 분석 LLM 프롬프트 빌더
├── news_collector.py            # Google News RSS 뉴스 수집기
└── strategies/
    ├── __init__.py
    ├── base_strategy.py         # 전략 추상 기본 클래스 (ABC)
    ├── rsi_strategy.py          # RSI 전략
    ├── macd_strategy.py         # MACD 전략
    ├── bollinger_bands_strategy.py  # 볼린저 밴드
    └── stochastic_strategy.py   # 스토캐스틱
```

---

## 마켓별 특성

### 암호화폐 트레이딩
- **거래소 연동**: CCXT 라이브러리 사용
- **24/7 거래**: 주말/공휴일 없음
- **높은 변동성**: 시뮬레이션 파라미터 조정 필요
- **거래 수수료**: 0.1% ~ 0.25% (거래소별 상이)

### 해외주식 트레이딩
- **증권사 연동**: 증권사 API (키움, 이베스트, Interactive Brokers 등)
- **거래 시간**: 장중 거래 시간 제한 (미국: 23:30~06:00 KST)
- **안정적 변동성**: 암호화폐 대비 낮은 변동성
- **거래 수수료**: 증권사별 상이

---

## 전략 아키텍처

### BaseStrategy 추상 기본 클래스

모든 전략은 `BaseStrategy`(ABC)를 상속해야 합니다. 위치: `strategies/base_strategy.py`

```python
from trading_bot.strategies import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, param1: int = 10):
        super().__init__(name=f"MyStrategy_{param1}")
        self.param1 = param1

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # 반드시 signal, position 컬럼 포함
        ...

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        ...

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        ...

    def get_params(self) -> Dict:
        return {'param1': self.param1}
```

**BaseStrategy 제공 메서드**:
- `validate_signal(signal)`: 시그널 값이 -1, 0, 1인지 검증
- `validate_dataframe(df)`: OHLCV 필수 컬럼 존재 확인
- `get_params()`: 파라미터 반환 (오버라이드 권장)
- `get_param_info()`: 파라미터 설명 반환 (오버라이드 권장)

### StrategyRegistry - 전략 등록/조회

싱글턴 레지스트리로 전략을 이름으로 관리합니다.

```python
from trading_bot import StrategyRegistry

registry = StrategyRegistry()

# 전략 조회
registry.list_strategies()        # ['RSI', 'MACD', 'BollingerBands', ...]
strategy = registry.create("RSI", period=14, overbought=70, oversold=30)

# 전략 등록 (커스텀)
registry.register("MyStrategy", MyStrategy)
```

**데코레이터로 자동 등록**:
```python
from trading_bot.strategy_registry import register_strategy

@register_strategy("MyStrategy")
class MyStrategy(BaseStrategy):
    ...
```

내장 전략들은 모듈 로드 시 자동 등록됩니다.

### 검증 레이어

#### SignalValidator - 시그널 유효성 검증

```python
from trading_bot import SignalValidator

# 시그널 값 검증
SignalValidator.validate_signal_value(signal)

# 시그널 시퀀스 논리 검증 (중복 진입, 공매도 탐지)
warnings = SignalValidator.validate_signal_sequence(df['signal'])

# 지표 데이터 이상 탐지 (NaN, Inf)
warnings = SignalValidator.validate_indicators(df)

# Look-ahead bias 간이 탐지
is_ok = SignalValidator.validate_no_lookahead(df, strategy)
```

#### OrderExecutionVerifier - 주문 실행 검증

```python
from trading_bot import OrderExecutionVerifier

verifier = OrderExecutionVerifier()

# 시그널-주문 방향 일치 확인
is_valid, msg = verifier.verify_execution(signal, trade, position)

# 포지션 정합성 검증 (거래 기록 기반 재구성)
issues = verifier.verify_position_consistency(positions, trades)

# 자본금 정합성 검증
is_ok, msg = verifier.verify_capital_consistency(initial, trades, current)

# 검증 리포트
report = verifier.generate_verification_report()
```

#### Backtester/PaperTrader에서 검증 활성화

```python
# Backtester
backtester = Backtester(strategy, enable_verification=True)
results = backtester.run(df)
# results에 verification_report 포함

# PaperTrader
trader = PaperTrader(strategy=strategy, ..., enable_verification=True)
```

---

## 로컬 코딩 컨벤션

### 전략 인터페이스 (필수 구현)

모든 전략 클래스는 `BaseStrategy`를 상속하고 다음 메서드를 구현해야 합니다:

```python
from trading_bot.strategies import BaseStrategy

class Strategy(BaseStrategy):
    def __init__(self, **params):
        """전략 파라미터 초기화"""
        super().__init__(name="Strategy_Name")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        지표 계산 및 시그널 생성

        Returns:
            DataFrame with:
            - 원본 OHLCV 컬럼
            - 지표 컬럼 (전략별)
            - 'signal': 1 (BUY), -1 (SELL), 0 (HOLD)
            - 'position': 1 (long), 0 (flat)
        """
        pass

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """현재 시그널 반환: (signal, info_dict)"""
        pass

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """모든 시그널 이벤트 반환"""
        pass
```

### Look-Ahead Bias 방지

❌ **잘못된 예시** (미래 데이터 사용):
```python
data['signal'] = (data['close'] > data['close'].shift(-1))  # 미래 데이터!
```

✅ **올바른 예시** (과거 데이터만 사용):
```python
data['signal'] = (data['close'] > data['close'].shift(1))
```

### 시그널 타이밍

- 시그널은 **현재 바의 종가** 기준으로 생성
- 실행은 **다음 바의 시가** (또는 현재 종가) 기준

### 데이터 복사 규칙

지표 계산 시 원본 데이터 보호:
```python
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()  # 원본 보호
    # 지표 계산...
    return data
```

---

## 주요 파일 설명

| 파일 | 역할 | 마켓 지원 |
|------|------|----------|
| `config.py` | 전역 설정 관리 (거래소, 증권사, 초기 자본 등) | 암호화폐 + 해외주식 |
| `data_handler.py` | CCXT, 증권사 API를 통한 실시간 데이터 | 암호화폐 + 해외주식 |
| `simulation_data.py` | GBM 기반 시뮬레이션 데이터 생성 | 공통 |
| `backtester.py` | 백테스팅 엔진 (수수료, 슬리피지 포함) | 공통 |
| `optimizer.py` | 그리드 서치 파라미터 최적화 | 공통 |
| `paper_trader.py` | 실시간 페이퍼 트레이딩 (Stop Loss/Take Profit 지원) | 암호화폐 + 해외주식 |
| `database.py` | SQLite 데이터베이스 (세션 추적) | 공통 |
| `strategy_presets.py` | 전략 설정 저장/불러오기 (JSON) | 공통 |
| `strategy_registry.py` | 전략 등록/조회 싱글턴 레지스트리 | 공통 |
| `signal_validator.py` | 시그널 유효성 검증 (값, 시퀀스, 지표, look-ahead) | 공통 |
| `execution_verifier.py` | 주문 실행 정확성 검증 (포지션, 자본금) | 공통 |
| `notifications.py` | 알림 서비스 (Slack Webhook, Email SMTP) | 공통 |
| `regime_detector.py` | 시장 레짐 감지 (ADX, 트렌드, 변동성 기반 분류) | 공통 |
| `llm_client.py` | LLM API 클라이언트 (vLLM, 시그널 필터/레짐 판단) | 공통 |
| `market_analyzer.py` | 일일 시장 데이터 분석 (KIS API 데이터 수집 + Notion 리포트) | 해외주식 |
| `market_analysis_prompt.py` | 시장 분석 LLM 프롬프트 빌더 (섹터별 분석, 기술적 지표) | 해외주식 |
| `news_collector.py` | Google News RSS 뉴스 수집기 (feedparser 기반, 종목별 최신 뉴스) | 해외주식 |

---

## PaperTrader - 실시간 모의투자

### 개요

`PaperTrader` 클래스는 실시간 시장 데이터를 사용한 모의투자를 지원합니다.
- **멀티 심볼**: 최대 7종목 동시 추적 가능
- **데이터베이스 연동**: SQLite로 세션, 거래, 포트폴리오 스냅샷 저장
- **실시간 실행**: `run_realtime()` 메서드로 주기적 전략 실행

### 기본 사용법

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from trading_bot.database import TradingDatabase
from dashboard.kis_broker import get_kis_broker

# 1. 브로커, 전략, 데이터베이스 초기화
broker = get_kis_broker()  # KIS API 필요
strategy = RSIStrategy(period=14, overbought=70, oversold=30)
db = TradingDatabase()  # data/paper_trading.db에 저장

# 2. PaperTrader 생성
trader = PaperTrader(
    strategy=strategy,
    symbols=['AAPL', 'MSFT', 'GOOGL'],  # 최대 7종목
    broker=broker,
    initial_capital=10000.0,
    position_size=0.3,  # 종목당 30% 투자
    db=db
)

# 3. 실시간 실행 (60초 간격)
trader.run_realtime(interval_seconds=60, timeframe='1d')
```

### 실시간 실행 루프

`run_realtime()` 메서드는 다음 작업을 반복합니다:

1. **실시간 시세 조회**: `broker.fetch_ticker(symbol, overseas=True)`
2. **OHLCV 데이터 조회**: `broker.fetch_ohlcv(symbol, timeframe, limit=100, overseas=True)`
3. **전략 신호 생성**: `strategy.get_current_signal(df)`
4. **거래 실행**: 신호에 따라 BUY/SELL
5. **포트폴리오 스냅샷**: 현재 포트폴리오 상태 저장
6. **대기**: `interval_seconds` 만큼 sleep

### 데이터베이스 연동

`TradingDatabase` 클래스는 다음 테이블을 관리합니다:

#### 1. `paper_trading_sessions`
- `session_id`: 세션 ID (strategy_name_timestamp 형식)
- `strategy_name`: 전략 이름
- `start_time`, `end_time`: 세션 시작/종료 시간
- `initial_capital`, `final_capital`: 초기/최종 자본
- `total_return`, `sharpe_ratio`, `max_drawdown`, `win_rate`: 성과 지표
- `status`: 세션 상태 (active/completed)

#### 2. `trades`
- 거래 내역 (symbol, timestamp, type, price, size, commission, pnl)

#### 3. `portfolio_snapshots`
- 포트폴리오 스냅샷 (timestamp, total_value, cash, positions JSON)

#### 4. `strategy_signals`
- 전략 신호 (symbol, timestamp, signal, indicator_values JSON, executed)

#### 5. `regime_history`
- 레짐 감지 이력 (session_id, symbol, timestamp, regime, confidence, adx, trend_direction, volatility_percentile, recommended_strategies JSON, details JSON)
- 인덱스: session_id, (session_id, timestamp), (symbol, timestamp)

#### 6. `llm_decisions`
- LLM 판단 이력 (session_id, symbol, timestamp, decision_type, request_context JSON, response JSON, latency_ms, model_name)
- decision_type: "signal_filter" 또는 "regime_judge"
- 인덱스: session_id, (session_id, timestamp), decision_type

### 멀티 심볼 포트폴리오

```python
# positions는 Dict[str, float] (심볼 → 보유 주식 수)
trader.positions = {
    'AAPL': 10.0,
    'MSFT': 5.0,
    'GOOGL': 3.0
}

# 포트폴리오 가치 계산
total_value = trader.get_portfolio_value()  # 현금 + 모든 포지션 가치
```

### 세션 관리

```python
# 세션 시작 (자동으로 session_id 생성)
trader.start()

# 세션 중지 (최종 지표 업데이트)
trader.stop()

# 세션 요약 조회
summary = db.get_session_summary(trader.session_id)
print(f"Total Return: {summary['total_return']:.2f}%")
print(f"Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
```

### 주의사항

1. **브로커 필수**: `run_realtime()` 사용 시 broker 파라미터 필수
2. **API 제한**: KIS API rate limit (1분당 1회) 고려
3. **해외주식**: `overseas=True` 파라미터 필수 (미국 주식 거래 시)
4. **종목 수 제한**: 최대 7종목 (API 제한 및 성능 고려)
5. **데이터베이스**: db 파라미터 없으면 세션 추적 안 됨

---

## Strategy Preset Manager - 전략 설정 관리

### 개요

`StrategyPresetManager` 클래스는 전략 설정을 JSON 파일로 저장하고 불러오는 기능을 제공합니다.
- **프리셋 저장**: 전략 이름, 파라미터, 심볼, 자본금, 위험 관리 설정 저장
- **프리셋 불러오기**: 저장된 설정을 빠르게 복원
- **프리셋 공유**: JSON 파일로 내보내기/가져오기

### 기본 사용법

```python
from trading_bot.strategy_presets import StrategyPresetManager

# 1. StrategyPresetManager 초기화
manager = StrategyPresetManager()  # 기본 경로: data/strategy_presets.json

# 2. 프리셋 저장
manager.save_preset(
    name="보수적 RSI 전략",
    description="안정적 수익을 위한 보수적 RSI 설정",
    strategy="RSI Strategy",
    strategy_params={"period": 14, "overbought": 70, "oversold": 30},
    symbols=["AAPL", "MSFT", "GOOGL"],
    initial_capital=10000.0,
    position_size=0.3,
    stop_loss_pct=0.03,  # 3% 손절
    take_profit_pct=0.06,  # 6% 익절
    enable_stop_loss=True,
    enable_take_profit=True
)

# 3. 프리셋 불러오기
preset = manager.load_preset("보수적 RSI 전략")
print(preset['strategy'])  # "RSI Strategy"
print(preset['strategy_params'])  # {"period": 14, ...}

# 4. 모든 프리셋 조회
all_presets = manager.list_presets()
for preset_name in all_presets:
    print(preset_name)

# 5. 프리셋 삭제
manager.delete_preset("보수적 RSI 전략")

# 6. 프리셋 내보내기
manager.export_preset("보수적 RSI 전략", "presets/my_strategy.json")

# 7. 프리셋 가져오기
manager.import_preset("presets/my_strategy.json", new_name="가져온 전략")
```

### 프리셋 데이터 구조

```python
{
    "name": "보수적 RSI 전략",
    "description": "안정적 수익을 위한 보수적 RSI 설정",
    "strategy": "RSI Strategy",
    "strategy_params": {
        "period": 14,
        "overbought": 70,
        "oversold": 30
    },
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "initial_capital": 10000.0,
    "position_size": 0.3,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06,
    "enable_stop_loss": true,
    "enable_take_profit": true,
    "created_at": "2026-02-09T10:30:00",
    "updated_at": "2026-02-09T10:30:00",
    "last_used": "2026-02-09T12:00:00"
}
```

### 주의사항

- 프리셋 이름은 고유해야 함 (중복 시 덮어쓰기)
- JSON 파일은 `data/` 디렉토리에 자동 저장
- 프리셋 불러오기 시 `last_used` 타임스탬프 자동 업데이트
- 프리셋 가져오기 시 `new_name` 지정하지 않으면 원래 이름 사용

---

## Notification Service - 알림 서비스 (Phase 2)

### 개요

`NotificationService` 클래스는 거래 알림과 일일 리포트를 Slack 또는 Email로 전송합니다.
- **Slack Webhook**: 실시간 거래 알림
- **Email SMTP**: 일일 성과 리포트
- **다양한 알림 타입**: 거래, 세션 시작/종료, 일일 리포트, 에러

### 기본 사용법

#### Slack 알림

```python
from trading_bot.notifications import NotificationService
import os

# 1. Slack Webhook으로 초기화
notifier = NotificationService(
    slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL')
)

# 2. 거래 알림
notifier.notify_trade({
    'type': 'BUY',
    'symbol': 'AAPL',
    'price': 150.25,
    'size': 10.0,
    'timestamp': '2026-02-09 10:30:00'
})

# 3. 세션 시작 알림
notifier.notify_session_start({
    'strategy_name': 'RSI_14_70_30',
    'symbols': ['AAPL', 'MSFT'],
    'initial_capital': 10000.0
})

# 4. 세션 종료 알림
notifier.notify_session_end({
    'strategy_name': 'RSI_14_70_30',
    'total_return': 2.5,
    'win_rate': 65.0,
    'max_drawdown': -3.2
})

# 5. 일일 리포트
notifier.notify_daily_report({
    'strategy_name': 'RSI_14_70_30',
    'total_return': 2.5,
    'sharpe_ratio': 1.45,
    'max_drawdown': -3.2,
    'win_rate': 65.0,
    'num_trades': 12
})

# 6. 에러 알림
notifier.notify_error('API 호출 실패', 'Rate limit exceeded')
```

#### Email 알림

```python
# Email SMTP로 초기화
notifier = NotificationService(
    email_config={
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender_email': 'your_email@gmail.com',
        'sender_password': os.getenv('EMAIL_PASSWORD'),
        'receiver_email': 'receiver@example.com'
    }
)

# Email로 일일 리포트 전송
notifier.notify_daily_report({
    'strategy_name': 'RSI_14_70_30',
    'total_return': 2.5,
    'sharpe_ratio': 1.45,
    'max_drawdown': -3.2,
    'win_rate': 65.0,
    'num_trades': 12
})
```

#### Slack + Email 동시 사용

```python
# 두 채널 모두 활성화
notifier = NotificationService(
    slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
    email_config={
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender_email': 'your_email@gmail.com',
        'sender_password': os.getenv('EMAIL_PASSWORD'),
        'receiver_email': 'receiver@example.com'
    }
)

# 거래는 Slack으로 (실시간)
notifier.notify_trade({...})

# 일일 리포트는 Email로 (상세)
notifier.notify_daily_report({...})
```

### Slack 파일 업로드 (Phase 2 - 2026-02-09)

#### 개요

Slack Bot Token을 사용하여 리포트 파일을 Slack 채널에 자동 업로드합니다.
- **단일 파일 업로드**: `upload_file_to_slack()`
- **여러 파일 일괄 업로드**: `upload_reports_to_slack()`
- **리포트 + 파일 통합**: `notify_daily_report_with_files()`

#### 설정 방법

1. **Slack Bot Token 발급**:
   - [Slack API 앱](https://api.slack.com/apps) 생성
   - **OAuth & Permissions** → Bot Token Scopes 추가:
     - `files:write`: 파일 업로드 권한
     - `chat:write`: 메시지 전송 권한
   - **Install App to Workspace** → Bot User OAuth Token 복사

2. **채널 ID 확인**:
   - Slack 채널 우클릭 → **View channel details**
   - 하단에 Channel ID 표시 (예: `C0123456789`)

3. **환경 변수 설정** (`.env`):
```bash
# Slack Bot Token (파일 업로드용)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_CHANNEL=C0123456789  # 채널 ID (# 기호 없음)

# Slack Webhook (텍스트 메시지용 - 선택)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

4. **라이브러리 설치**:
```bash
pip install slack-sdk>=3.23.0
```

#### 사용 예시

**단일 파일 업로드**:
```python
from trading_bot.notifications import NotificationService

notifier = NotificationService(
    slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
    slack_channel=os.getenv('SLACK_CHANNEL')
)

# CSV 파일 업로드
notifier.upload_file_to_slack(
    file_path='reports/RSI_14_30_70_summary.csv',
    initial_comment='📊 일일 트레이딩 요약',
    title='Daily Trading Summary'
)
```

**여러 파일 일괄 업로드**:
```python
# 세션 종료 후 리포트 파일들 업로드
report_files = [
    'reports/RSI_14_30_70_summary.csv',
    'reports/RSI_14_30_70_snapshots.csv',
    'reports/RSI_14_30_70_report.json'
]

session_summary = {
    'strategy_name': 'RSI_14_70_30',
    'total_return': 2.5,
    'sharpe_ratio': 1.45,
    'max_drawdown': -3.2,
    'win_rate': 65.0,
    'num_trades': 12
}

notifier.upload_reports_to_slack(report_files, session_summary)
```

**리포트 텍스트 + 파일 통합 전송**:
```python
# 일일 리포트 (텍스트 메시지) + 파일 첨부
notifier.notify_daily_report_with_files(
    session_summary={
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'win_rate': 65.0
    },
    report_files=[
        'reports/RSI_14_30_70_summary.csv',
        'reports/RSI_14_30_70_report.json'
    ]
)
```

#### Scheduler 통합

`scheduler.py`에서 장 마감 시 자동으로 리포트 파일을 Slack에 업로드합니다:

```python
# scheduler.py 내부
def stop_paper_trading():
    """장 마감 후 세션 종료 및 리포트 전송"""
    # ... 세션 종료 ...

    # 리포트 생성
    report_files = generate_daily_report(session_id)

    # Slack에 파일 업로드
    notifier.upload_reports_to_slack(report_files, session_summary)
```

### 환경 변수 설정

`.env` 파일에 다음 환경 변수를 설정하세요:

```bash
# Slack Webhook (텍스트 메시지)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Slack Bot Token (파일 업로드)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_CHANNEL=C0123456789  # 채널 ID (# 없음)

# Email SMTP
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password  # Gmail: 2단계 인증 후 앱 비밀번호 생성
EMAIL_RECEIVER=receiver@example.com
```

### 주의사항

- **Slack Webhook**: [Slack 앱](https://api.slack.com/messaging/webhooks) 생성 후 Webhook URL 발급
- **Slack Bot Token**: OAuth & Permissions에서 `files:write`, `chat:write` 권한 필요
- **채널 ID**: 채널 이름이 아닌 ID 사용 (예: `C0123456789`, `#trading-alerts` 아님)
- **Bot 초대**: 채널에 Bot을 먼저 초대해야 파일 업로드 가능 (`/invite @bot_name`)
- **Gmail 사용 시**: 2단계 인증 활성화 후 앱 비밀번호 생성 필요
- **에러 처리**: 알림 전송 실패 시 로그 기록 (예외 발생 안 함)
- **Rate Limit**: Slack은 1초당 1개 메시지 권장

---

## RegimeDetector - 시장 레짐 감지 모듈

### 개요

`RegimeDetector` 클래스는 OHLCV 데이터로부터 시장 상태(레짐)를 자동 분류합니다.
- **BULLISH**: 강한 상승 추세 (ADX > 25, 양의 트렌드)
- **BEARISH**: 강한 하락 추세 (ADX > 25, 음의 트렌드)
- **SIDEWAYS**: 낮은 추세 강도 (ADX <= 25, 낮은 변동성)
- **VOLATILE**: 높은 변동성 (변동성 백분위 > 75)

### 기본 사용법

```python
from trading_bot.regime_detector import RegimeDetector, MarketRegime, RegimeResult

# 1. 초기화
detector = RegimeDetector(adx_period=14, ma_period=50, vol_window=100)

# 2. 마지막 바 기준 레짐 감지
result = detector.detect(df)  # RegimeResult
print(result.regime)          # MarketRegime.BULLISH
print(result.confidence)      # 0.82
print(result.adx)             # 35.2
print(result.recommended_strategies)  # ['MACD Strategy', 'RSI+MACD Combo Strategy']

# 3. 전체 바별 레짐 라벨링
labeled_df = detector.detect_series(df)
# columns: regime, regime_confidence, adx, trend_direction, volatility_percentile
```

### 분류 로직

```
vol_percentile > 75 → VOLATILE (confidence: 0.5 + (vol-75)/50)
adx > 25 & trend > 0 → BULLISH (confidence: 0.5 + (adx-25)/50)
adx > 25 & trend < 0 → BEARISH (confidence: 0.5 + (adx-25)/50)
else → SIDEWAYS (confidence: 0.5 + (25-adx)/50)
```

### 전략 매핑

| 레짐 | 추천 전략 |
|------|----------|
| BULLISH | MACD Strategy, RSI+MACD Combo Strategy |
| BEARISH | RSI Strategy, Bollinger Bands |
| SIDEWAYS | RSI Strategy, Bollinger Bands |
| VOLATILE | Bollinger Bands |

### PaperTrader 통합

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.regime_detector import RegimeDetector

detector = RegimeDetector()
trader = PaperTrader(
    strategy=strategy,
    symbols=['AAPL'],
    broker=broker,
    regime_detector=detector,  # 레짐 감지 활성화
)
# _realtime_iteration()에서 자동으로 레짐 감지 + DB 로깅
```

### 주의사항

- 최소 데이터 길이: `max(adx_period*2, ma_period, vol_window) + 10` 바
- 데이터 부족 시 SIDEWAYS (confidence=0.3) 반환 (에러 아님)
- scipy 미사용 (pandas/numpy만 사용)

---

## LLMClient - LLM API 클라이언트

### 개요

`LLMClient` 클래스는 vLLM OpenAI-compatible API를 호출하여 시그널 필터링과 레짐 판단을 수행합니다.
- **시그널 필터 (7B)**: VBT/전략 시그널을 실행/보류/거부 판단
- **레짐 판단 (14B)**: 통계 레짐에 LLM의 정성적 판단 보강
- **Fail-open**: LLM 에러/타임아웃 시 원본 시그널 그대로 통과

### 기본 사용법

```python
from trading_bot.llm_client import LLMClient, LLMConfig

# 1. 초기화 (환경변수 자동 읽기)
config = LLMConfig(
    signal_filter_url="http://localhost:8000/v1/chat/completions",  # 7B
    regime_judge_url="http://localhost:8001/v1/chat/completions",   # 14B
    timeout=10.0,
    enabled=True,
)
client = LLMClient(config)

# 2. 시그널 필터링
decision = client.filter_signal({
    'signal': 'BUY',
    'symbol': 'AAPL',
    'strategy': 'RSI',
    'indicators': {'rsi': 28, 'price': 150.25},
    'regime': {'regime': 'BULLISH', 'confidence': 0.82, 'adx': 32},
})
# decision.action: "execute" | "hold" | "reject"
# decision.confidence: 0.85
# decision.reasoning: "RSI oversold in bullish regime..."

# 3. 레짐 판단
judgment = client.judge_regime({
    'statistical_regime': {'regime': 'SIDEWAYS', 'adx': 18},
    'market_data': {'recent_returns': [...], 'volume_trend': 'declining'},
})
# judgment.regime_override: None (동의) 또는 "BEARISH" (오버라이드)

# 4. 헬스체크
health = client.health_check()
# {'signal_filter': True, 'regime_judge': False}
```

### 환경변수

```bash
LLM_SIGNAL_URL=http://localhost:8000/v1/chat/completions  # 7B 모델
LLM_REGIME_URL=http://localhost:8001/v1/chat/completions   # 14B 모델
LLM_ENABLED=true  # false로 비활성화
```

### 주의사항

- `requests` 라이브러리로 직접 호출 (openai SDK 미사용)
- `temperature=0.1`, `max_tokens=500`으로 구조화 출력
- JSON 파싱 실패 시 None 반환 (fail-open)
- `enabled=False` 시 모든 호출이 None 반환
- LLM은 시그널을 **필터링만** 함 (새 시그널 생성 안 함)

---

## MarketAnalyzer - 일일 시장 데이터 분석

### 개요

`MarketAnalyzer` 클래스는 KIS API로 해외주식 시장 데이터를 수집하고, LLM 프롬프트를 생성하여 Notion에 일일 분석 리포트를 작성합니다.
- **데이터 수집**: KIS API를 통해 OHLCV, 거래량, 기술적 지표 수집
- **프롬프트 생성**: `MarketAnalysisPromptBuilder`로 구조화된 LLM 프롬프트 생성
- **Notion 연동**: 분석 결과를 Notion 페이지에 자동 작성

### 기본 사용법

```python
from trading_bot.market_analyzer import MarketAnalyzer

# 1. 초기화 (환경변수에서 설정 로드)
analyzer = MarketAnalyzer()

# 2. 시장 데이터 수집
data = analyzer.collect_market_data()

# 3. 분석 프롬프트 생성
prompt = analyzer.build_analysis_prompt(data)

# 4. Notion에 리포트 작성
analyzer.publish_to_notion(analysis_result)
```

### 환경변수

```bash
MARKET_ANALYSIS_ENABLED=true
MARKET_ANALYSIS_SYMBOLS=AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT
NOTION_MARKET_ANALYSIS_PAGE_ID=30dd62f0-dffd-80a6-b624-e5a061ed26a9
```

### MarketAnalysisPromptBuilder

`market_analysis_prompt.py`는 수집된 시장 데이터를 LLM이 분석할 수 있는 구조화된 프롬프트로 변환합니다.

```python
from trading_bot.market_analysis_prompt import MarketAnalysisPromptBuilder

builder = MarketAnalysisPromptBuilder()
prompt = builder.build(market_data)
# 섹터별 분석, 기술적 지표 요약, 시장 전망 프롬프트 포함
```

### 주의사항

- KIS API 인증 필요 (`.env`에 KIS_APPKEY, KIS_APPSECRET 설정)
- Notion API는 `notion-client` MCP 도구를 통해 연동
- `MARKET_ANALYSIS_ENABLED=false`로 비활성화 가능
- 스케줄러 통합: `scheduler.py`에서 장 마감 후 자동 실행

---

## Stop Loss & Take Profit (PaperTrader 통합)

### 개요

PaperTrader에 손절/익절 기능이 통합되어 자동으로 리스크 관리를 수행합니다.
- **Stop Loss**: 손실이 일정 비율 도달 시 자동 매도
- **Take Profit**: 수익이 일정 비율 도달 시 자동 매도
- **포지션별 관리**: 각 종목마다 독립적으로 손익 추적

### 기본 사용법

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from dashboard.kis_broker import get_kis_broker

# 1. PaperTrader 생성 시 손절/익절 설정
trader = PaperTrader(
    strategy=RSIStrategy(),
    symbols=['AAPL', 'MSFT'],
    broker=get_kis_broker(),
    initial_capital=10000.0,
    position_size=0.3,
    stop_loss_pct=0.03,  # 3% 손절
    take_profit_pct=0.06,  # 6% 익절
    enable_stop_loss=True,
    enable_take_profit=True
)

# 2. 실시간 실행 (손절/익절 자동 실행)
trader.run_realtime(interval_seconds=60, timeframe='1d')
```

### 동작 원리

1. **진입 가격 추적**: 매수 시 평균 진입 가격 기록
2. **실시간 모니터링**: 매 iteration마다 현재가와 진입가 비교
3. **자동 청산**:
   - 손실률 >= `stop_loss_pct` → 자동 매도
   - 수익률 >= `take_profit_pct` → 자동 매도
4. **거래 로그**: 손절/익절 거래도 DB에 기록

### 예시

```python
# 예시: AAPL 매수 후 손절/익절
# 1. AAPL을 $150에 10주 매수 (진입가: $150)
# 2. 손절: $145.50 (-3%) 도달 시 자동 매도
# 3. 익절: $159.00 (+6%) 도달 시 자동 매도
```

### 주의사항

- `enable_stop_loss=False`면 손절 비활성화
- `enable_take_profit=False`면 익절 비활성화
- 손절/익절은 전략 시그널보다 우선 실행됨
- 평균 진입 가격은 `trader.avg_entry_prices` 딕셔너리에 저장

---

## 새 전략 추가 방법

1. **전략 파일 생성**: `trading_bot/strategies/my_strategy.py`
2. **BaseStrategy 상속 및 구현**:
   ```python
   from trading_bot.strategies import BaseStrategy

   class MyStrategy(BaseStrategy):
       def __init__(self, param1=10):
           super().__init__(name=f"MyStrategy_{param1}")
           self.param1 = param1

       def calculate_indicators(self, df): ...
       def get_current_signal(self, df): ...
       def get_all_signals(self, df): ...
       def get_params(self): return {'param1': self.param1}
   ```
3. **`strategies/__init__.py`에 추가**:
   ```python
   from .my_strategy import MyStrategy
   __all__ = [..., 'MyStrategy']
   ```
4. **StrategyRegistry에 등록** (`strategy_registry.py`의 `_register_builtin_strategies`에 추가):
   ```python
   ("MyStrategy", "trading_bot.strategies.my_strategy", "MyStrategy"),
   ```
5. **테스트 작성**: `tests/test_my_strategy.py`
6. **백테스트 검증**: 여러 시장 상황에서 테스트

---

## 성능 최적화 팁

### 벡터화 연산 사용

❌ **비효율적** (루프):
```python
for i in range(len(data)):
    data.loc[i, 'ma'] = data['close'].iloc[i-10:i].mean()
```

✅ **효율적** (벡터화):
```python
data['ma'] = data['close'].rolling(window=10).mean()
```

### 지표 계산 캐싱

```python
@lru_cache(maxsize=128)
def _calculate_expensive_indicator(self, key):
    # 비싼 계산...
    return result
```

---

## 커밋 전 체크리스트

- [ ] 모든 전략이 인터페이스를 올바르게 구현했는가?
- [ ] Look-ahead bias가 없는가?
- [ ] 원본 데이터를 `.copy()`로 보호했는가?
- [ ] 테스트가 통과하는가?
- [ ] 여러 시장 상황(상승/하락/횡보)에서 검증했는가?

---

## 관련 문서

- [strategies/CLAUDE.md](strategies/CLAUDE.md): 전략 구현 세부 가이드
- [../tests/CLAUDE.md](../tests/CLAUDE.md): 테스트 작성 가이드
- [../examples/CLAUDE.md](../examples/CLAUDE.md): 사용 예제
