# 미국 주식 퀀트 트레이딩 자동화 봇 - 로드맵

> **작성일**: 2026-02-08
> **목표**: 미국 주식 퀀트 트레이딩 자동화 봇 완성
> **마켓**: 미국 주식 (다양한 종목)
> **브로커**: 한국투자증권 (실전 계좌)

---

## 📊 현재 상태 (92% 완성)

### ✅ 완료된 작업

1. **핵심 인프라**
   - 백테스팅 엔진 (`backtester.py`)
   - 전략 최적화 (`optimizer.py`)
   - 여러 전략 구현 (RSI, MACD, Bollinger Bands, Stochastic)
   - 시뮬레이션 데이터 생성

2. **한국투자증권 API 연동**
   - `KoreaInvestmentBroker` 구현 완료
   - 실시간 시세, OHLCV, 잔고, 주문 기능
   - python-kis 통합
   - Rate Limiter 구현

3. **대시보드**
   - Streamlit 기반 UI
   - Real-time Quotes 탭 (실시간 시세)
   - 백테스팅 결과 시각화
   - Auto-refresh 기능

4. **모의투자 (Paper Trading) - Phase 1 완료 ✅**
   - `PaperTrader` 실시간 실행 루프 (`run_realtime()`)
   - 멀티 심볼 포트폴리오 추적 (최대 7종목 동시)
   - SQLite 데이터베이스 연동 (세션, 거래, 스냅샷, 시그널)
   - 대시보드 Paper Trading 탭 (전략/종목 선택, 시작/중지)
   - 실시간 포트폴리오 모니터링 (10초 자동 새로고침)
   - Strategy Comparison 탭 (세션 비교, 수익 곡선 차트)
   - 42개 통합 테스트 통과

4. **자동화 스케줄러 (Phase 2 완료 ✅)**
   - `scheduler.py` - APScheduler 통합
   - 미국 장 시간대 자동 실행 (23:00, 23:30, 06:00 KST)
   - 알림 서비스 (`notifications.py`) - Slack/Email
   - Slack 파일 업로드 (Bot Token) - 리포트 자동 전송
   - 거래 알림, 일일 리포트, 에러 알림
   - 로깅 시스템 (`logs/scheduler.log`)

### ⚠️ 부족한 부분 (8% 미완성)

1. **실전 매매 연결 없음** (Phase 3)
   - 모의투자만 지원 (실전 계좌 연결 전)
   - 리스크 관리 시스템 미구현

---

## 🎯 Phase 1: 모의투자 엔드투엔드 연결 (최우선, 2-3주)

**목표**: 백테스트 → 모의투자를 대시보드에서 원클릭 실행

### 1.1 대시보드에 "Paper Trading" 탭 추가

**파일**: `dashboard/app.py`

**구현 내용**:
```python
# 새 탭 추가
tab1, tab2, tab3, tab4 = st.tabs([
    "Backtest", "Paper Trading", "Live Monitor", "Real-time Quotes"
])

with tab2:  # Paper Trading 탭
    # 1. 전략 선택
    strategy_selector()

    # 2. 종목 선택 (다양한 미국 주식)
    stock_selector()  # AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA 등

    # 3. 모의투자 설정
    initial_capital = st.number_input("초기 자본", value=10000.0)
    position_size = st.slider("포지션 크기", 0.1, 1.0, 0.95)

    # 4. 시작/중지 버튼
    if st.button("모의투자 시작"):
        start_paper_trading()

    if st.button("모의투자 중지"):
        stop_paper_trading()

    # 5. 실시간 포트폴리오 현황
    display_portfolio_status()
```

**산출물**:
- [x] Paper Trading 탭 UI
- [ ] 전략 선택 UI
- [ ] 종목 선택 UI (다양한 미국 주식)
- [ ] 포트폴리오 현황 표시

---

### 1.2 PaperTrader와 KIS 브로커 연결

**파일**: `trading_bot/paper_trader.py`

**변경 사항**:
```python
class PaperTrader:
    def __init__(
        self,
        strategy,
        broker,  # DataHandler 대신 KoreaInvestmentBroker 사용
        symbols: List[str],  # 여러 종목 지원
        initial_capital: float = 10000.0,
        position_size: float = 0.95,
        commission: float = 0.001
    ):
        self.broker = broker
        self.symbols = symbols
        # ...

    def run_realtime(self, interval_seconds: int = 60):
        """실시간 모의투자 실행 (매 1분마다)"""
        while self.is_running:
            for symbol in self.symbols:
                # 1. 실시간 시세 조회
                ticker = self.broker.fetch_ticker(symbol, overseas=True)

                # 2. 전략 신호 생성
                signal = self.strategy.get_current_signal(...)

                # 3. 모의 주문 실행
                if signal == 1:  # BUY
                    self.execute_buy(ticker['last'], datetime.now())
                elif signal == -1:  # SELL
                    self.execute_sell(ticker['last'], datetime.now())

            time.sleep(interval_seconds)
```

**산출물**:
- [ ] PaperTrader 리팩토링 (여러 종목 지원)
- [ ] KIS 브로커 실시간 데이터 연결
- [ ] 매 1분마다 전략 실행

---

### 1.3 모의투자 결과 데이터베이스 저장

**목적**:
- 모의투자 거래 내역 영구 저장
- 추후 LLM 학습 데이터로 활용
- 전략 성과 분석

**파일**: `trading_bot/database.py` (신규)

**스키마 설계**:
```sql
-- 모의투자 세션
CREATE TABLE paper_trading_sessions (
    session_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    initial_capital REAL NOT NULL,
    final_capital REAL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    win_rate REAL,
    status TEXT DEFAULT 'running'  -- running, stopped, completed
);

-- 거래 내역
CREATE TABLE trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    type TEXT NOT NULL,  -- BUY, SELL
    price REAL NOT NULL,
    size REAL NOT NULL,
    commission REAL NOT NULL,
    pnl REAL,
    pnl_pct REAL,
    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions(session_id)
);

-- 포트폴리오 스냅샷 (매 분마다 기록)
CREATE TABLE portfolio_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    total_value REAL NOT NULL,
    cash REAL NOT NULL,
    positions TEXT,  -- JSON: {"AAPL": 10, "MSFT": 5}
    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions(session_id)
);

-- 전략 신호 (LLM 학습용)
CREATE TABLE strategy_signals (
    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    signal INTEGER NOT NULL,  -- -1: SELL, 0: HOLD, 1: BUY
    indicator_values TEXT,  -- JSON: {"RSI": 30.5, "MACD": 0.1}
    market_price REAL NOT NULL,
    executed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (session_id) REFERENCES paper_trading_sessions(session_id)
);
```

**구현 내용**:
```python
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional

class TradingDatabase:
    def __init__(self, db_path: str = "data/paper_trading.db"):
        self.db_path = db_path
        self._init_db()

    def create_session(self, strategy_name: str, initial_capital: float) -> str:
        """새 모의투자 세션 생성"""
        session_id = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # INSERT INTO paper_trading_sessions ...
        return session_id

    def log_trade(self, session_id: str, trade: Dict):
        """거래 내역 저장"""
        # INSERT INTO trades ...

    def log_signal(self, session_id: str, signal: Dict):
        """전략 신호 저장 (LLM 학습용)"""
        # INSERT INTO strategy_signals ...

    def log_portfolio_snapshot(self, session_id: str, snapshot: Dict):
        """포트폴리오 스냅샷 저장"""
        # INSERT INTO portfolio_snapshots ...

    def get_session_summary(self, session_id: str) -> Dict:
        """세션 요약 조회"""
        # SELECT FROM paper_trading_sessions ...

    def export_for_llm(self, session_id: str) -> pd.DataFrame:
        """LLM 학습용 데이터 Export"""
        # 전략 신호 + 시장 데이터 + 결과 조합
        pass
```

**산출물**:
- [ ] SQLite 데이터베이스 스키마
- [ ] TradingDatabase 클래스 구현
- [ ] PaperTrader와 연동

---

### 1.4 전략 성과 비교 대시보드

**파일**: `dashboard/app.py` (Strategy Comparison 탭 추가)

**구현 내용**:
```python
with tab5:  # Strategy Comparison 탭
    st.header("전략 성과 비교")

    # 1. 저장된 모의투자 세션 목록
    sessions = db.get_all_sessions()

    # 2. 비교할 세션 선택
    selected_sessions = st.multiselect(
        "비교할 세션 선택",
        sessions,
        format_func=lambda x: f"{x['strategy_name']} ({x['start_time']})"
    )

    # 3. 성과 지표 비교 테이블
    comparison_df = pd.DataFrame([
        db.get_session_summary(s) for s in selected_sessions
    ])
    st.dataframe(comparison_df)

    # 4. 수익 곡선 비교 차트
    fig = create_equity_comparison_chart(selected_sessions)
    st.plotly_chart(fig)

    # 5. 승률 높은 전략 추천
    best_strategy = comparison_df.loc[comparison_df['win_rate'].idxmax()]
    st.success(f"🏆 승률 1위: {best_strategy['strategy_name']} ({best_strategy['win_rate']:.1f}%)")
```

**산출물**:
- [ ] Strategy Comparison 탭 UI
- [ ] 여러 세션 성과 비교 테이블
- [ ] 수익 곡선 비교 차트
- [ ] 승률 기반 전략 추천

---

### 1.5 Phase 1 체크리스트 ✅

- [x] Paper Trading 탭 추가
- [x] PaperTrader와 KIS 브로커 연결
- [x] 여러 종목 동시 모의투자 (최대 7종목)
- [x] SQLite 데이터베이스 구현 (`TradingDatabase`)
- [x] 전략 성과 비교 대시보드 (Strategy Comparison 탭)
- [x] 단위 테스트 작성 (42개 테스트 통과)
- [x] 문서 업데이트 (README, CLAUDE.md, examples)

---

## 🤖 Phase 2: 자동화 스케줄러 (2주)

**목표**: 미국 장 시작 시 자동으로 모의투자 실행

### 2.1 스케줄러 스크립트 작성

**파일**: `scheduler.py` (루트 디렉토리)

**구현 내용**:
```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from trading_bot.paper_trader import PaperTrader
from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.strategies import RSIStrategy, MACDStrategy
import os
from dotenv import load_dotenv

load_dotenv()

scheduler = BlockingScheduler()

def optimize_strategy():
    """장 시작 30분 전: 전략 파라미터 최적화"""
    print("전략 최적화 시작...")
    # optimizer.optimize() 실행
    # 최적 파라미터 저장

def start_paper_trading():
    """장 시작: 모의투자 시작"""
    print("모의투자 시작...")
    broker = KoreaInvestmentBroker(...)
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)

    trader = PaperTrader(
        strategy=strategy,
        broker=broker,
        symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
        initial_capital=10000.0
    )

    trader.run_realtime(interval_seconds=60)

def stop_paper_trading():
    """장 마감: 모의투자 중지, 결과 리포트 생성"""
    print("모의투자 중지...")
    # trader.stop()
    # 결과 리포트 생성 (CSV, 이메일 전송)

# 미국 장 시작 30분 전 (한국 시간 23:00)
scheduler.add_job(
    optimize_strategy,
    CronTrigger(hour=23, minute=0, timezone='Asia/Seoul')
)

# 미국 장 시작 (한국 시간 23:30)
scheduler.add_job(
    start_paper_trading,
    CronTrigger(hour=23, minute=30, timezone='Asia/Seoul')
)

# 미국 장 마감 (한국 시간 06:00)
scheduler.add_job(
    stop_paper_trading,
    CronTrigger(hour=6, minute=0, timezone='Asia/Seoul')
)

if __name__ == '__main__':
    print("스케줄러 시작...")
    scheduler.start()
```

**산출물**:
- [x] `scheduler.py` 작성 ✅
- [x] APScheduler 통합 ✅
- [x] 미국 장 시간대 자동 실행 ✅
- [x] 알림 서비스 통합 ✅

---

### 2.2 알림 기능 (Slack/이메일)

**파일**: `trading_bot/notifications.py` (신규)

**구현 내용**:
```python
import requests
from email.mime.text import MIMEText
import smtplib

class NotificationService:
    def __init__(self, slack_webhook_url: str = None, email_config: dict = None):
        self.slack_webhook_url = slack_webhook_url
        self.email_config = email_config

    def send_slack(self, message: str):
        """Slack 알림 전송"""
        if self.slack_webhook_url:
            requests.post(self.slack_webhook_url, json={'text': message})

    def send_email(self, subject: str, body: str):
        """이메일 알림 전송"""
        if self.email_config:
            msg = MIMEText(body)
            msg['Subject'] = subject
            # SMTP 전송...

    def notify_trade(self, trade: dict):
        """거래 발생 시 알림"""
        message = f"🔔 거래 발생: {trade['type']} {trade['symbol']} @ ${trade['price']}"
        self.send_slack(message)

    def notify_daily_report(self, session_summary: dict):
        """일일 리포트 알림"""
        message = f"""
📊 일일 모의투자 리포트
전략: {session_summary['strategy_name']}
수익률: {session_summary['total_return']:.2f}%
승률: {session_summary['win_rate']:.1f}%
최대 손실: {session_summary['max_drawdown']:.2f}%
        """
        self.send_slack(message)
```

**산출물**:
- [x] `notifications.py` 작성 ✅
- [x] Slack Webhook 통합 ✅
- [x] Slack Bot Token 통합 (파일 업로드) ✅
- [x] 이메일 알림 기능 (SMTP) ✅
- [x] 거래 발생 시 알림 ✅
- [x] 일일 리포트 자동 전송 ✅
- [x] 리포트 파일 자동 업로드 (CSV/JSON) ✅
- [x] 에러 알림 ✅
- [x] 세션 시작/종료 알림 ✅

---

### 2.3 Phase 2 체크리스트

- [x] `scheduler.py` 작성
- [x] 미국 장 시간대 자동 실행 (APScheduler 통합)
- [x] `notifications.py` 작성 (Slack/이메일 알림)
- [x] Slack 파일 업로드 기능 (Bot Token)
- [x] 스케줄러에 알림 통합
- [x] 스케줄러에 파일 업로드 통합
- [x] requirements.txt 업데이트 (APScheduler, requests, slack-sdk 추가)
- [x] .env.example 업데이트 (알림 설정)
- [x] 테스트 스크립트 작성 (examples/test_notifications.py)
- [x] 테스트 스크립트 작성 (examples/test_slack_file_upload.py)
- [x] 채널 ID 조회 도구 (examples/debug_slack_channels.py)
- [ ] 로그 모니터링 (Sentry, CloudWatch 등) - 선택사항

---

## 🚀 Phase 3: 실전 매매 연결 (신중하게, 2-3주)

**⚠️ 주의**: 실전 계좌이므로 모의투자에서 최소 **3개월** 이상 안정적인 수익을 확인한 후 진행

### 3.1 실전 모드 토글

**파일**: `dashboard/app.py`

**구현 내용**:
```python
# 사이드바에 모드 선택
mode = st.sidebar.radio(
    "거래 모드",
    ["백테스팅", "모의투자", "실전투자 ⚠️"],
    help="실전투자는 신중하게 선택하세요"
)

if mode == "실전투자 ⚠️":
    # 2단계 확인
    st.warning("⚠️ 실전 계좌로 자동매매를 실행합니다. 신중하게 진행하세요.")

    password = st.text_input("확인 비밀번호 입력", type="password")

    if password != os.getenv('TRADING_PASSWORD'):
        st.error("비밀번호가 올바르지 않습니다.")
        st.stop()

    # 리스크 관리 설정
    max_daily_loss = st.slider("1일 최대 손실 제한 (%)", 1, 10, 3)
    max_position_size = st.slider("종목별 최대 투자 비율 (%)", 5, 30, 20)
```

**산출물**:
- [ ] 실전 모드 UI
- [ ] 2단계 확인 (비밀번호)
- [ ] 리스크 관리 설정 UI

---

### 3.2 리스크 관리 추가

**파일**: `trading_bot/risk_manager.py` (신규)

**구현 내용**:
```python
class RiskManager:
    def __init__(
        self,
        max_daily_loss_pct: float = 3.0,
        max_position_size_pct: float = 20.0,
        max_total_exposure_pct: float = 80.0
    ):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_position_size_pct = max_position_size_pct
        self.max_total_exposure_pct = max_total_exposure_pct

        self.daily_start_capital = None
        self.is_trading_halted = False

    def check_daily_loss(self, current_capital: float) -> bool:
        """1일 최대 손실 체크"""
        if self.daily_start_capital is None:
            self.daily_start_capital = current_capital
            return True

        loss_pct = (self.daily_start_capital - current_capital) / self.daily_start_capital * 100

        if loss_pct >= self.max_daily_loss_pct:
            self.is_trading_halted = True
            # 알림 전송
            notify(f"⛔ 일일 최대 손실 {self.max_daily_loss_pct}% 도달. 거래 중지.")
            return False

        return True

    def check_position_size(self, symbol: str, amount: float, current_capital: float) -> bool:
        """종목별 최대 투자 비율 체크"""
        position_value = amount  # amount는 투자 금액
        position_pct = position_value / current_capital * 100

        if position_pct > self.max_position_size_pct:
            notify(f"⚠️ {symbol} 투자 비율 {position_pct:.1f}% > 제한 {self.max_position_size_pct}%")
            return False

        return True

    def reset_daily(self):
        """일일 리셋 (매일 장 시작 시)"""
        self.daily_start_capital = None
        self.is_trading_halted = False
```

**산출물**:
- [ ] RiskManager 클래스 구현
- [ ] 1일 최대 손실 제한
- [ ] 종목별 최대 투자 비율 제한
- [ ] 총 투자 비율 제한

---

### 3.3 실전 주문 실행 (신중)

**파일**: `trading_bot/live_trader.py` (신규)

**구현 내용**:
```python
from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.risk_manager import RiskManager
from trading_bot.notifications import NotificationService

class LiveTrader:
    def __init__(
        self,
        strategy,
        broker: KoreaInvestmentBroker,
        symbols: List[str],
        risk_manager: RiskManager,
        notifier: NotificationService
    ):
        self.strategy = strategy
        self.broker = broker
        self.symbols = symbols
        self.risk_manager = risk_manager
        self.notifier = notifier

    def execute_signal(self, symbol: str, signal: int, current_price: float):
        """실전 주문 실행 (리스크 관리 포함)"""

        # 1. 리스크 관리 체크
        balance = self.broker.fetch_balance()
        current_capital = balance['total']['KRW']

        if not self.risk_manager.check_daily_loss(current_capital):
            self.notifier.send_slack("⛔ 일일 손실 제한 도달. 거래 중지.")
            return

        # 2. 주문 전 알림
        self.notifier.send_slack(
            f"🔔 주문 전 알림: {signal_text(signal)} {symbol} @ ${current_price}"
        )

        # 3. 실전 주문 실행
        try:
            if signal == 1:  # BUY
                amount = self._calculate_position_size(current_capital, current_price)

                if not self.risk_manager.check_position_size(symbol, amount, current_capital):
                    return

                order = self.broker.create_order(
                    symbol=symbol,
                    order_type='market',
                    side='buy',
                    amount=amount / current_price,  # 주식 수량
                    overseas=True
                )

                self.notifier.send_slack(f"✅ 매수 체결: {symbol} {order['amount']}주 @ ${order['price']}")

            elif signal == -1:  # SELL
                order = self.broker.create_order(
                    symbol=symbol,
                    order_type='market',
                    side='sell',
                    amount=self._get_holdings(symbol),
                    overseas=True
                )

                self.notifier.send_slack(f"✅ 매도 체결: {symbol} {order['amount']}주 @ ${order['price']}")

        except Exception as e:
            self.notifier.send_slack(f"❌ 주문 실패: {symbol} - {str(e)}")
            raise
```

**산출물**:
- [ ] LiveTrader 클래스 구현
- [ ] 실전 주문 실행 (KIS 브로커)
- [ ] 리스크 관리 통합
- [ ] 주문 전/후 알림

---

### 3.4 감사(Audit) 로그

**파일**: `trading_bot/audit_logger.py` (신규)

**구현 내용**:
```python
import logging
from datetime import datetime

class AuditLogger:
    def __init__(self, log_file: str = "logs/audit.log"):
        self.logger = logging.getLogger('audit')
        self.logger.setLevel(logging.INFO)

        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(handler)

    def log_order(self, order_type: str, symbol: str, amount: float, price: float, **kwargs):
        """주문 로그 기록"""
        self.logger.info(f"ORDER: {order_type} {symbol} {amount} @ {price} | {kwargs}")

    def log_risk_event(self, event: str, details: dict):
        """리스크 이벤트 로그"""
        self.logger.warning(f"RISK_EVENT: {event} | {details}")

    def log_system_event(self, event: str):
        """시스템 이벤트 로그"""
        self.logger.info(f"SYSTEM: {event}")
```

**산출물**:
- [ ] AuditLogger 클래스 구현
- [ ] 모든 실전 주문 로그 기록
- [ ] 리스크 이벤트 로그
- [ ] 로그 파일 백업 (S3 등)

---

### 3.5 Phase 3 체크리스트

- [ ] 실전 모드 UI (2단계 확인)
- [ ] RiskManager 구현
- [ ] LiveTrader 구현
- [ ] 감사 로그 시스템
- [ ] 모의투자 3개월 검증 완료 ✅
- [ ] 소액(10만원) 실전 테스트
- [ ] 본격 실전 투자

---

## 🔮 Phase 4: 고도화 (장기, 선택사항)

### 4.1 LLM 연결 (데이터 기반 의사결정)

**목적**:
- 모의투자/실전투자 데이터를 LLM에 학습시켜 더 나은 의사결정
- 시장 뉴스 분석 → 매매 신호 보강

**구현 아이디어**:
```python
# 1. 데이터 준비 (이미 Phase 1에서 SQLite에 저장됨)
df = db.export_for_llm(session_id)

# 2. LLM 학습 (OpenAI API 또는 로컬 LLM)
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# 시장 데이터 + 전략 신호 + 결과를 프롬프트로 전달
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "당신은 퀀트 트레이딩 전문가입니다."},
        {"role": "user", "content": f"다음 데이터를 분석하여 매수 신호인지 판단하세요:\n{df.to_string()}"}
    ]
)

# 3. LLM 응답을 신호에 반영
llm_signal = parse_llm_response(response.choices[0].message.content)

# 4. 기존 전략 신호 + LLM 신호 조합
final_signal = combine_signals(strategy_signal, llm_signal)
```

**데이터 구조 (LLM 학습용)**:
```json
{
  "timestamp": "2024-01-01 10:30:00",
  "symbol": "AAPL",
  "market_data": {
    "open": 150.0,
    "high": 152.0,
    "low": 149.5,
    "close": 151.0,
    "volume": 5000000
  },
  "indicators": {
    "RSI": 30.5,
    "MACD": 0.1,
    "MA_fast": 150.2,
    "MA_slow": 149.8
  },
  "strategy_signal": 1,  // BUY
  "executed": true,
  "result": {
    "pnl": 50.0,
    "pnl_pct": 2.5
  },
  "news": [
    "Apple announces new iPhone",
    "Stock market rally continues"
  ]
}
```

**산출물**:
- [ ] LLM 프롬프트 엔지니어링
- [ ] 뉴스 API 통합 (Bloomberg, Reuters)
- [ ] LLM 신호 + 전략 신호 조합 로직
- [ ] 성과 비교 (LLM 있음 vs 없음)

---

### 4.2 포트폴리오 최적화

**목적**: 여러 전략을 조합하여 리스크 분산

**구현 아이디어**:
```python
from scipy.optimize import minimize

def portfolio_optimization(strategies: List, historical_returns: np.ndarray):
    """마코위츠 평균-분산 최적화"""

    def objective(weights):
        portfolio_return = np.dot(weights, historical_returns.mean(axis=0))
        portfolio_vol = np.sqrt(np.dot(weights, np.dot(historical_returns.cov(), weights)))
        sharpe = portfolio_return / portfolio_vol
        return -sharpe  # 최대화 → 최소화

    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]  # 가중치 합 = 1
    bounds = [(0, 0.5) for _ in strategies]  # 각 전략 최대 50%

    result = minimize(objective, x0=np.ones(len(strategies)) / len(strategies), bounds=bounds, constraints=constraints)

    return result.x  # 최적 가중치
```

**산출물**:
- [ ] 포트폴리오 최적화 모듈
- [ ] 여러 전략 동시 실행
- [ ] 가중치 자동 조정

---

### 4.3 머신러닝 전략

**목적**: LSTM/XGBoost로 가격 예측

**구현 아이디어**:
```python
from sklearn.ensemble import GradientBoostingClassifier

# 1. 피처 엔지니어링
features = ['RSI', 'MACD', 'MA_fast', 'MA_slow', 'volume_ratio']
target = 'signal'  # 1: BUY, -1: SELL, 0: HOLD

# 2. 학습
X_train, y_train = prepare_data(df)
model = GradientBoostingClassifier()
model.fit(X_train, y_train)

# 3. 예측
signal = model.predict(X_test)
```

**산출물**:
- [ ] 머신러닝 전략 모듈
- [ ] LSTM/XGBoost 학습 파이프라인
- [ ] 백테스팅 검증

---

### 4.4 멀티 마켓

**목적**: 미국 주식 + 국내 주식 + 암호화폐 동시 운용

**산출물**:
- [ ] 멀티 마켓 지원 (KIS 국내주식, CCXT 암호화폐)
- [ ] 환율 리스크 관리
- [ ] 마켓별 전략 최적화

---

## 📅 타임라인 요약

| Phase | 목표 | 기간 | 상태 |
|-------|------|------|------|
| **Phase 1** | 모의투자 엔드투엔드 연결 | 2-3주 | ✅ 완료 (2026-02-08) |
| **Phase 2** | 자동화 스케줄러 | 2주 | ✅ 완료 (2026-02-08) |
| **Phase 3** | 실전 매매 연결 | 2-3주 | 🟡 다음 단계 (3개월 검증 후) |
| **Phase 4** | 고도화 (LLM, ML) | 장기 | ⚪ 선택사항 |

---

## 🎯 다음 액션 아이템

### 즉시 시작 (Phase 1.1)
1. [ ] `dashboard/app.py`에 "Paper Trading" 탭 추가
2. [ ] 미국 주식 종목 리스트 정의 (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA 등 - 다양한 섹터)
3. [ ] Paper Trading UI 구현 (전략 선택, 종목 선택, 시작/중지 버튼)

### 다음 주 (Phase 1.2-1.3)
1. [ ] `PaperTrader` 리팩토링 (여러 종목 지원)
2. [ ] KIS 브로커 실시간 데이터 연결
3. [ ] SQLite 데이터베이스 설계 및 구현

### 2주 후 (Phase 1.4-1.5)
1. [ ] 전략 성과 비교 대시보드
2. [ ] 테스트 작성
3. [ ] Phase 1 완료 및 Phase 2 시작

---

## 📝 참고 사항

### 실전 계좌 사용 주의사항

1. **모의투자 필수**: 최소 3개월 이상 안정적인 수익 확인
2. **소액 테스트**: 처음에는 10-50만원으로 시작
3. **리스크 관리**: 1일 최대 손실 제한 (3% 권장)
4. **감정 배제**: 자동화 시스템 신뢰, 수동 개입 최소화

### LLM 연결 준비

- **데이터 수집**: Phase 1부터 모든 거래 내역을 SQLite에 저장
- **스키마 설계**: LLM 학습에 적합한 JSON 형식
- **API 비용**: OpenAI API 사용 시 월 예산 고려

### 전략 연구 방법

1. **백테스팅**: 과거 데이터로 여러 전략 테스트
2. **파라미터 최적화**: Grid Search로 최적 파라미터 찾기
3. **모의투자 검증**: 실시간 데이터로 3개월 이상 검증
4. **승률 분석**: Strategy Comparison 탭에서 비교
5. **리스크 조정**: Sharpe Ratio, Max Drawdown 고려

---

**작성자**: Quant Trading Lab Development Team
**최종 업데이트**: 2026-02-08
