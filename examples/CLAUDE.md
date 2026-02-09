# examples/ - 예제 스크립트

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, 예제 스크립트 사용법에 특화된 규칙만 정의합니다.

---

## 목적

트레이딩 봇의 주요 기능을 시연하는 예제 스크립트:
- **빠른 시작**: 초보자를 위한 간단한 예제
- **백테스팅**: 전략 백테스트 실행
- **최적화**: 파라미터 최적화
- **전략 비교**: 여러 전략 성능 비교

---

## 디렉토리 구조

```
examples/
├── quickstart.py                    # 빠른 시작 가이드
├── run_backtest_example.py          # 백테스팅 예제
├── strategy_optimization.py         # 전략 최적화 예제
├── strategy_comparison.py           # 전략 비교 예제
├── test_dashboard.py                # 대시보드 테스트
├── test_strategy_presets.py         # 전략 프리셋 관리 테스트
├── test_stop_loss_take_profit.py    # 손절/익절 기능 테스트
├── test_notifications.py            # 알림 서비스 테스트 (Phase 2)
├── test_scheduler.py                # 자동화 스케줄러 테스트 (Phase 2)
├── test_slack_file_upload.py        # Slack 파일 업로드 테스트 (Phase 2)
└── debug_slack_channels.py          # Slack 채널 ID 조회 도구 (Phase 2)
```

---

## 예제 스크립트

### 1. `quickstart.py` - 빠른 시작

**목적**: 5분 안에 첫 백테스트 실행

**실행 명령어**:
```bash
python examples/quickstart.py 2>&1 | tee .context/terminal/quickstart_$(date +%s).log
```

**주요 내용**:
- 시뮬레이션 데이터 생성
- RSI 전략 생성
- 백테스트 실행
- 결과 출력

**코드 구조**:
```python
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.backtester import Backtester

# 1. 데이터 생성
data_gen = SimulationDataGenerator(seed=42)
df = data_gen.generate_trend_data(periods=1000, trend='bullish')

# 2. 전략 생성
strategy = RSIStrategy(period=14, overbought=70, oversold=30)

# 3. 백테스트 실행
backtester = Backtester(strategy, initial_capital=10000)
results = backtester.run(df)

# 4. 결과 출력
backtester.print_results(results)
```

**예상 출력**:
```
=== Backtest Results ===
Strategy: RSI_14_70_30
Total Return: 15.23%
Sharpe Ratio: 1.45
Max Drawdown: -8.67%
Win Rate: 58.33%
Total Trades: 24
```

---

### 2. `run_backtest_example.py` - 백테스팅 예제

**목적**: 다양한 시장 상황에서 전략 테스트

**실행 명령어**:
```bash
python examples/run_backtest_example.py 2>&1 | tee .context/terminal/backtest_$(date +%s).log
```

**주요 내용**:
- 여러 시장 상황 (상승/하락/횡보/변동성) 생성
- 각 상황에서 전략 백테스트
- 결과 비교 및 분석

**코드 구조**:
```python
# 여러 시장 상황 생성
market_scenarios = {
    'bullish': data_gen.generate_trend_data(periods=1000, trend='bullish'),
    'bearish': data_gen.generate_trend_data(periods=1000, trend='bearish'),
    'sideways': data_gen.generate_trend_data(periods=1000, trend='sideways'),
    'volatile': data_gen.generate_volatile_data(periods=1000)
}

# 각 상황에서 백테스트
for scenario_name, data in market_scenarios.items():
    print(f"\n=== {scenario_name.upper()} Market ===")
    results = backtester.run(data)
    backtester.print_results(results)
```

**마켓별 권장 사용**:
- **암호화폐**: volatile 시나리오 중점 테스트
- **해외주식**: bullish/bearish 시나리오 중점 테스트

---

### 3. `strategy_optimization.py` - 전략 최적화

**목적**: 그리드 서치로 최적 파라미터 찾기

**실행 명령어**:
```bash
python examples/strategy_optimization.py 2>&1 | tee .context/terminal/optimization_$(date +%s).log
```

**주요 내용**:
- 파라미터 그리드 정의
- 모든 조합 백테스트
- 최적 파라미터 찾기
- 민감도 분석

**코드 구조**:
```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy

# 파라미터 그리드 (암호화폐용)
crypto_param_grid = {
    'period': [7, 10, 14, 21, 28],
    'overbought': [70, 75, 80, 85],
    'oversold': [15, 20, 25, 30]
}

# 파라미터 그리드 (해외주식용)
stock_param_grid = {
    'period': [10, 14, 20, 28, 35],
    'overbought': [65, 70, 75, 80],
    'oversold': [20, 25, 30, 35]
}

# 최적화 실행
optimizer = StrategyOptimizer(initial_capital=10000)
best_result = optimizer.optimize(
    RSIStrategy, 
    df, 
    crypto_param_grid,  # 또는 stock_param_grid
    metric='sharpe_ratio'
)

print(f"Best parameters: {best_result['params']}")
print(f"Best Sharpe Ratio: {best_result['sharpe_ratio']:.2f}")
```

**최적화 메트릭 선택**:
- `total_return`: 수익률 최대화 (단기)
- `sharpe_ratio`: 위험 대비 수익 최대화 (권장)
- `win_rate`: 승률 최대화
- `max_drawdown`: 손실 최소화 (보수적)

---

### 4. `strategy_comparison.py` - 전략 비교

**목적**: 여러 전략의 성능 비교

**실행 명령어**:
```bash
python examples/strategy_comparison.py 2>&1 | tee .context/terminal/comparison_$(date +%s).log
```

**주요 내용**:
- 여러 전략 생성 (RSI, MACD, MA, Bollinger Bands, Stochastic)
- 동일한 데이터로 백테스트
- 결과 테이블로 비교

**코드 구조**:
```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from trading_bot.strategies.stochastic_strategy import StochasticStrategy
from trading_bot.strategy import MovingAverageCrossover

# 전략 리스트
strategies = [
    MovingAverageCrossover(fast_period=10, slow_period=30),
    RSIStrategy(period=14, overbought=70, oversold=30),
    MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
    BollingerBandsStrategy(period=20, std_dev=2.0),
    StochasticStrategy(k_period=14, d_period=3)
]

# 비교 실행
optimizer = StrategyOptimizer(initial_capital=10000)
comparison = optimizer.compare_strategies(strategies, df)

print("\n=== Strategy Comparison ===")
print(comparison.to_string(index=False))
```

**예상 출력**:
```
=== Strategy Comparison ===
         Strategy  Total Return  Sharpe Ratio  Max Drawdown  Win Rate  Num Trades
  MA_Crossover_10_30         8.45          1.12        -12.34     52.17          23
        RSI_14_70_30        15.23          1.45         -8.67     58.33          24
     MACD_12_26_9        11.78          1.28         -9.45     55.56          27
  BollingerBands_20_2.0        9.34          1.18        -10.23     53.33          30
    Stochastic_14_3        13.56          1.35         -9.12     56.67          33
```

**마켓별 추천 전략**:
- **암호화폐 (고변동성)**: RSI, Bollinger Bands
- **해외주식 (저변동성)**: MACD, MA Crossover

---

### 5. `test_dashboard.py` - 대시보드 테스트

**목적**: 대시보드 기능 검증

**실행 명령어**:
```bash
python examples/test_dashboard.py 2>&1 | tee .context/terminal/dashboard_test_$(date +%s).log
```

**주요 내용**:
- 대시보드 차트 생성 함수 테스트
- 다국어 번역 테스트
- 데이터 로딩 테스트

---

### 6. `test_strategy_presets.py` - 전략 프리셋 관리

**목적**: StrategyPresetManager 기능 검증

**실행 명령어**:
```bash
python examples/test_strategy_presets.py 2>&1 | tee .context/terminal/test_presets_$(date +%s).log
```

**주요 내용**:
- 프리셋 저장/불러오기
- 프리셋 목록 조회
- 프리셋 삭제
- 프리셋 내보내기/가져오기

**코드 구조**:
```python
from trading_bot.strategy_presets import StrategyPresetManager

def test_save_and_load():
    """프리셋 저장 및 불러오기 테스트"""
    manager = StrategyPresetManager()

    # 저장
    manager.save_preset(
        name="테스트 전략",
        strategy="RSI Strategy",
        strategy_params={"period": 14, "overbought": 70, "oversold": 30},
        symbols=["AAPL"],
        initial_capital=10000.0,
        position_size=0.3
    )

    # 불러오기
    preset = manager.load_preset("테스트 전략")
    assert preset['strategy'] == "RSI Strategy"
    print("✅ 저장/불러오기 성공")

def test_list_presets():
    """프리셋 목록 조회 테스트"""
    manager = StrategyPresetManager()
    presets = manager.list_presets()
    print(f"총 {len(presets)}개 프리셋:")
    for name in presets:
        print(f"  - {name}")

def test_delete_preset():
    """프리셋 삭제 테스트"""
    manager = StrategyPresetManager()
    manager.delete_preset("테스트 전략")
    print("✅ 삭제 성공")

if __name__ == "__main__":
    test_save_and_load()
    test_list_presets()
    test_delete_preset()
```

---

### 7. `test_stop_loss_take_profit.py` - 손절/익절 기능

**목적**: PaperTrader의 손절/익절 자동화 검증

**실행 명령어**:
```bash
python examples/test_stop_loss_take_profit.py 2>&1 | tee .context/terminal/test_sl_tp_$(date +%s).log
```

**주요 내용**:
- MockBroker로 가격 시뮬레이션
- Stop Loss 트리거 확인
- Take Profit 트리거 확인
- 거래 로그 검증

**코드 구조**:
```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy

class MockBroker:
    """가격 시뮬레이션을 위한 Mock Broker"""
    def __init__(self):
        self.current_price = 100.0

    def fetch_ticker(self, symbol, overseas=True):
        return {'last': self.current_price}

    def fetch_ohlcv(self, symbol, timeframe, limit, overseas=True):
        # OHLCV 데이터 생성
        pass

def test_stop_loss():
    """손절 기능 테스트"""
    broker = MockBroker()

    trader = PaperTrader(
        strategy=RSIStrategy(),
        symbols=['AAPL'],
        broker=broker,
        initial_capital=10000.0,
        stop_loss_pct=0.03,  # 3% 손절
        enable_stop_loss=True
    )

    # 1. 매수 ($100)
    trader._execute_trade('AAPL', 'BUY', 10.0)

    # 2. 가격 하락 ($97, -3%)
    broker.current_price = 97.0
    trader._check_stop_loss_take_profit()

    # 3. 손절 확인
    assert trader.positions.get('AAPL', 0) == 0  # 포지션 청산
    print("✅ 손절 성공")

def test_take_profit():
    """익절 기능 테스트"""
    broker = MockBroker()

    trader = PaperTrader(
        strategy=RSIStrategy(),
        symbols=['AAPL'],
        broker=broker,
        initial_capital=10000.0,
        take_profit_pct=0.06,  # 6% 익절
        enable_take_profit=True
    )

    # 1. 매수 ($100)
    trader._execute_trade('AAPL', 'BUY', 10.0)

    # 2. 가격 상승 ($106, +6%)
    broker.current_price = 106.0
    trader._check_stop_loss_take_profit()

    # 3. 익절 확인
    assert trader.positions.get('AAPL', 0) == 0  # 포지션 청산
    print("✅ 익절 성공")

if __name__ == "__main__":
    test_stop_loss()
    test_take_profit()
```

---

### 8. `test_notifications.py` - 알림 서비스 (Phase 2)

**목적**: NotificationService의 Slack/Email 알림 검증

**실행 명령어**:
```bash
python examples/test_notifications.py 2>&1 | tee .context/terminal/test_notifications_$(date +%s).log
```

**주요 내용**:
- Slack Webhook 테스트
- Email SMTP 테스트
- 다양한 알림 타입 테스트

**환경 변수 요구사항**:
```bash
# .env 파일
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com
```

**코드 구조**:
```python
import os
from trading_bot.notifications import NotificationService

def test_slack_notification():
    """Slack 알림 테스트"""
    notifier = NotificationService(
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL')
    )

    # 거래 알림
    notifier.notify_trade({
        'type': 'BUY',
        'symbol': 'AAPL',
        'price': 150.25,
        'size': 10.0
    })
    print("✅ Slack 거래 알림 전송")

    # 일일 리포트
    notifier.notify_daily_report({
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'win_rate': 65.0
    })
    print("✅ Slack 일일 리포트 전송")

def test_email_notification():
    """Email 알림 테스트"""
    notifier = NotificationService(
        email_config={
            'smtp_server': os.getenv('EMAIL_SMTP_SERVER'),
            'smtp_port': int(os.getenv('EMAIL_SMTP_PORT', 587)),
            'sender_email': os.getenv('EMAIL_SENDER'),
            'sender_password': os.getenv('EMAIL_PASSWORD'),
            'receiver_email': os.getenv('EMAIL_RECEIVER')
        }
    )

    # 일일 리포트 (Email)
    notifier.notify_daily_report({
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'sharpe_ratio': 1.45
    })
    print("✅ Email 일일 리포트 전송")

if __name__ == "__main__":
    test_slack_notification()
    test_email_notification()
```

---

### 9. `test_scheduler.py` - 자동화 스케줄러 (Phase 2)

**목적**: APScheduler 기반 자동 트레이딩 검증

**실행 명령어**:
```bash
python examples/test_scheduler.py 2>&1 | tee .context/terminal/test_scheduler_$(date +%s).log
```

**주요 내용**:
- 스케줄러 초기화
- Cron 트리거 설정
- 시뮬레이션 모드 실행

**코드 구조**:
```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy

def start_trading():
    """거래 시작 작업 (23:30 KST)"""
    print("📈 Starting paper trading...")

    trader = PaperTrader(
        strategy=RSIStrategy(),
        symbols=['AAPL', 'MSFT'],
        initial_capital=10000.0
    )
    trader.start()
    print("✅ Trading session started")

def stop_trading():
    """거래 종료 작업 (06:00 KST)"""
    print("📊 Stopping paper trading...")
    # 세션 종료 및 리포트 생성
    print("✅ Trading session stopped")

def optimize_strategy():
    """전략 최적화 작업 (23:00 KST)"""
    print("🔍 Optimizing strategy...")
    # 파라미터 최적화 실행
    print("✅ Strategy optimized")

def test_scheduler():
    """스케줄러 테스트 (즉시 실행)"""
    scheduler = BlockingScheduler()

    # 테스트용 즉시 실행
    scheduler.add_job(optimize_strategy, 'date')  # 즉시 1회
    scheduler.add_job(start_trading, 'date')  # 즉시 1회
    scheduler.add_job(stop_trading, 'date')  # 즉시 1회

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()

if __name__ == "__main__":
    test_scheduler()
```

**실제 스케줄 설정** (`scheduler.py`):
```python
# 실전 스케줄 (매일 자동 실행)
scheduler.add_job(
    optimize_strategy,
    CronTrigger(hour=23, minute=0)  # 23:00 KST
)

scheduler.add_job(
    start_trading,
    CronTrigger(hour=23, minute=30)  # 23:30 KST (장 시작)
)

scheduler.add_job(
    stop_trading,
    CronTrigger(hour=6, minute=0)  # 06:00 KST (장 마감)
)
```

---

### 10. `test_slack_file_upload.py` - Slack 파일 업로드 (Phase 2)

**목적**: Slack Bot Token을 사용한 파일 업로드 기능 검증

**실행 명령어**:
```bash
python examples/test_slack_file_upload.py 2>&1 | tee .context/terminal/test_slack_upload_$(date +%s).log
```

**주요 내용**:
- Slack Bot Token 연결 확인
- 단일 파일 업로드
- 여러 파일 일괄 업로드
- 리포트 + 파일 통합 전송

**환경 변수 요구사항**:
```bash
# .env 파일
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_CHANNEL=C0123456789  # 채널 ID (# 없음)
```

**코드 구조**:
```python
import os
from trading_bot.notifications import NotificationService
from pathlib import Path

def test_upload_single_file():
    """단일 파일 업로드 테스트"""
    notifier = NotificationService(
        slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
        slack_channel=os.getenv('SLACK_CHANNEL')
    )

    # 테스트 파일 생성
    test_file = 'reports/test_report.txt'
    Path('reports').mkdir(exist_ok=True)
    with open(test_file, 'w') as f:
        f.write('This is a test report\n')

    # 파일 업로드
    success = notifier.upload_file_to_slack(
        file_path=test_file,
        initial_comment='📊 테스트 리포트',
        title='Test Report'
    )

    if success:
        print("✅ 파일 업로드 성공")
    else:
        print("✗ 파일 업로드 실패")

def test_upload_multiple_files():
    """여러 파일 일괄 업로드 테스트"""
    notifier = NotificationService(
        slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
        slack_channel=os.getenv('SLACK_CHANNEL')
    )

    # 테스트 파일 생성
    test_files = [
        'reports/summary.csv',
        'reports/snapshots.csv',
        'reports/report.json'
    ]

    for file_path in test_files:
        with open(file_path, 'w') as f:
            f.write(f'Test content for {Path(file_path).name}\n')

    # 세션 요약
    session_summary = {
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'sharpe_ratio': 1.45,
        'max_drawdown': -3.2,
        'win_rate': 65.0,
        'num_trades': 12
    }

    # 파일 업로드
    success = notifier.upload_reports_to_slack(test_files, session_summary)

    if success:
        print("✅ 여러 파일 업로드 성공")
    else:
        print("✗ 여러 파일 업로드 실패")

def test_daily_report_with_files():
    """일일 리포트 + 파일 통합 전송"""
    notifier = NotificationService(
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),  # 텍스트 메시지
        slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),      # 파일 업로드
        slack_channel=os.getenv('SLACK_CHANNEL')
    )

    session_summary = {
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'win_rate': 65.0
    }

    report_files = ['reports/summary.csv', 'reports/report.json']

    success = notifier.notify_daily_report_with_files(
        session_summary,
        report_files
    )

    if success:
        print("✅ 리포트 + 파일 전송 성공")
    else:
        print("✗ 리포트 + 파일 전송 실패")

if __name__ == "__main__":
    test_upload_single_file()
    test_upload_multiple_files()
    test_daily_report_with_files()
```

**Bot Token 발급 방법**:
1. [Slack API 앱](https://api.slack.com/apps) 생성
2. **OAuth & Permissions** → Bot Token Scopes 추가:
   - `files:write`: 파일 업로드 권한
   - `chat:write`: 메시지 전송 권한
3. **Install App to Workspace** → Bot User OAuth Token 복사
4. 채널에 Bot 초대: `/invite @bot_name`

---

### 11. `debug_slack_channels.py` - Slack 채널 ID 조회 도구

**목적**: Slack 채널 목록 조회 및 채널 ID 확인

**실행 명령어**:
```bash
python examples/debug_slack_channels.py 2>&1 | tee .context/terminal/debug_slack_$(date +%s).log
```

**주요 내용**:
- Bot이 접근 가능한 모든 채널 목록 조회
- 채널 이름과 ID 매핑 확인
- Bot 권한 상태 확인

**환경 변수 요구사항**:
```bash
# .env 파일
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
```

**코드 구조**:
```python
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def list_slack_channels():
    """Bot이 접근 가능한 채널 목록 조회"""
    token = os.getenv('SLACK_BOT_TOKEN')

    if not token:
        print("✗ SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
        return

    try:
        client = WebClient(token=token)

        # 공개 채널 조회
        response = client.conversations_list(types='public_channel,private_channel')

        print("\n=== Slack 채널 목록 ===\n")
        for channel in response['channels']:
            channel_name = channel['name']
            channel_id = channel['id']
            is_member = channel.get('is_member', False)
            member_status = "✓ Bot 참여중" if is_member else "✗ Bot 미참여"

            print(f"이름: #{channel_name}")
            print(f"ID: {channel_id}")
            print(f"상태: {member_status}")
            print("-" * 50)

    except SlackApiError as e:
        print(f"✗ Slack API 에러: {e.response['error']}")
        if e.response['error'] == 'missing_scope':
            print("권한이 부족합니다. channels:read 권한을 추가하세요.")

if __name__ == "__main__":
    list_slack_channels()
```

**사용 시나리오**:
- Slack Bot Token은 있지만 채널 ID를 모를 때
- Bot이 채널에 제대로 참여했는지 확인할 때
- 여러 채널 중 어느 채널을 사용할지 선택할 때

**Bot 권한 추가 (필요 시)**:
- **OAuth & Permissions** → Bot Token Scopes:
  - `channels:read`: 공개 채널 목록 조회
  - `groups:read`: 비공개 채널 목록 조회

---

## 예제 작성 가이드

### 새 예제 추가 시

1. **명확한 목적**: 예제가 보여주려는 핵심 기능 1개
2. **주석 추가**: 각 단계에 설명 주석
3. **결과 출력**: 실행 결과를 명확하게 표시
4. **로그 기록**: 터미널 로그 저장

**템플릿**:
```python
"""
[예제 제목]

목적: [이 예제가 보여주는 것]
실행: python examples/[파일명].py
"""
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.backtester import Backtester


def main():
    # 1. 데이터 준비
    print("Step 1: Generating simulation data...")
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish')
    print(f"Generated {len(df)} data points\n")
    
    # 2. 전략 생성
    print("Step 2: Creating strategy...")
    strategy = RSIStrategy(period=14)
    print(f"Strategy: {strategy.name}\n")
    
    # 3. 백테스트 실행
    print("Step 3: Running backtest...")
    backtester = Backtester(strategy, initial_capital=10000)
    results = backtester.run(df)
    
    # 4. 결과 출력
    print("\n=== Results ===")
    backtester.print_results(results)


if __name__ == "__main__":
    main()
```

---

## 실행 순서 권장

초보자를 위한 순서:
1. `quickstart.py` - 기본 개념 이해
2. `run_backtest_example.py` - 다양한 시장 상황 경험
3. `strategy_comparison.py` - 여러 전략 비교
4. `strategy_optimization.py` - 파라미터 튜닝

---

## 마켓별 예제 수정

### 암호화폐 트레이딩용

```python
# 높은 변동성, 짧은 기간
data = data_gen.generate_volatile_data(periods=500)
strategy = RSIStrategy(period=10, overbought=80, oversold=20)
```

### 해외주식 트레이딩용

```python
# 안정적 변동성, 긴 기간
data = data_gen.generate_trend_data(periods=2000, trend='bullish')
strategy = RSIStrategy(period=14, overbought=70, oversold=30)
```

---

## 트러블슈팅

### "No trades executed"

**원인**: 시그널이 전혀 발생하지 않음

**해결**:
- 파라미터 조정 (더 민감하게)
- 데이터 길이 늘리기 (periods 증가)
- 다른 시장 상황 시도

### "NaN in results"

**원인**: 데이터가 전략의 warm-up 기간보다 짧음

**해결**:
- 데이터 길이 늘리기
- 전략 파라미터 낮추기 (period 감소)

### "Low Sharpe Ratio"

**원인**: 위험 대비 수익이 낮음

**해결**:
- 전략 최적화 실행
- 다른 전략 시도
- 수수료 설정 확인

---

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 백테스팅 엔진 상세
- [../trading_bot/strategies/CLAUDE.md](../trading_bot/strategies/CLAUDE.md): 전략 구현 가이드
- [../README.md](../README.md): 프로젝트 개요 및 설치
