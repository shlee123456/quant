# tests/ - 테스트 작성 가이드

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, 테스트 작성에 특화된 규칙만 정의합니다.

---

## 목적

트레이딩 봇의 안정성과 정확성을 보장하기 위한 단위 테스트 및 통합 테스트:
- **전략 테스트**: 지표 계산, 시그널 생성 검증
- **백테스팅 테스트**: 성능 메트릭, 거래 실행 검증
- **통합 테스트**: 전체 워크플로우 검증

---

## 디렉토리 구조

```
tests/
├── __init__.py
├── conftest.py                        # 공통 pytest fixtures
├── test_strategy.py                   # MA 전략 테스트
├── test_rsi_strategy.py               # RSI 전략 테스트
├── test_macd_strategy.py              # MACD 전략 테스트
├── test_bollinger_bands_strategy.py   # Bollinger Bands 테스트
├── test_stochastic_strategy.py        # Stochastic 테스트
├── test_backtester.py                 # 백테스터 테스트
├── test_optimizer.py                  # 최적화 테스트
├── test_simulation_data.py            # 데이터 생성 테스트
├── test_kis_api.py                    # 한국투자증권 API 테스트
└── test_dashboard_integration.py      # 대시보드 통합 테스트
```

---

## 테스트 명령어

```bash
# 모든 테스트 실행 (slow 테스트 제외)
pytest -m "not slow" 2>&1 | tee .context/terminal/test_$(date +%s).log

# 모든 테스트 실행 (slow 테스트 포함)
pytest 2>&1 | tee .context/terminal/test_all_$(date +%s).log

# slow 테스트만 실행 (API 통합 테스트)
pytest -m slow 2>&1 | tee .context/terminal/test_slow_$(date +%s).log

# 커버리지 포함
pytest --cov=trading_bot --cov-report=html 2>&1 | tee .context/terminal/test_cov_$(date +%s).log

# 특정 테스트 파일
pytest tests/test_rsi_strategy.py -v 2>&1 | tee .context/terminal/test_rsi_$(date +%s).log

# 특정 테스트 함수
pytest tests/test_rsi_strategy.py::test_rsi_calculation -v

# 실패한 테스트만 재실행
pytest --lf 2>&1 | tee .context/terminal/test_failed_$(date +%s).log

# 병렬 실행 (pytest-xdist 설치 필요)
pytest -n auto
```

### 테스트 마커

프로젝트는 다음 pytest 마커를 사용합니다 (pytest.ini에 정의):

- **`slow`**: 외부 API를 호출하는 느린 테스트
  - 예: KIS API, 거래소 API 통합 테스트
  - 실행 시간이 길고 rate limit이 있을 수 있음
  - CI/CD에서 기본적으로 제외하려면: `pytest -m "not slow"`

---

## conftest.py - 공통 Fixtures

### 위치
`tests/conftest.py`는 pytest가 자동으로 로드하는 공통 fixture 파일입니다.

### 사용 가능한 Fixtures

#### `kis` - 한국투자증권 API 클라이언트

외부 API를 사용하는 테스트를 위한 fixture입니다.

**사용 예시:**
```python
def test_overseas_stock_quote(kis):
    """해외주식 시세 조회 테스트"""
    stock = kis.stock('AAPL', market='NASDAQ')
    quote = stock.quote()
    assert quote.price > 0
```

**환경 변수 요구사항:**
- `KIS_ID`: 한국투자증권 ID
- `KIS_APPKEY`: API Key
- `KIS_APPSECRET`: API Secret
- `KIS_ACCOUNT`: 계좌번호
- `KIS_MOCK`: 모의투자 여부 (기본값: true)

**동작:**
- 환경 변수가 없으면 자동으로 `pytest.skip()` 처리
- `pykis` 패키지가 없으면 자동으로 skip
- PyKis 초기화 실패 시 자동으로 skip

### 외부 API Fixture 패턴

외부 API 클라이언트를 fixture로 만들 때 다음 패턴을 따르세요:

```python
@pytest.fixture
def api_client():
    """외부 API 클라이언트 fixture"""
    # 1. 환경 변수 로드
    credentials = {
        'api_key': os.getenv('API_KEY'),
        'api_secret': os.getenv('API_SECRET'),
    }

    # 2. 필수 값 확인 - 없으면 skip
    if not all(credentials.values()):
        pytest.skip("API credentials not set in .env")

    try:
        # 3. 선택적 의존성 - ImportError 시 skip
        from external_api import APIClient

        # 4. 클라이언트 생성
        client = APIClient(**credentials)
        return client

    except ImportError:
        pytest.skip("external_api package not installed")
    except Exception as e:
        pytest.skip(f"Failed to initialize API client: {e}")
```

---

## 로컬 코딩 컨벤션

### 테스트 함수 네이밍

```python
def test_[기능]_[시나리오]_[기대결과]():
    """테스트 설명"""
    pass

# 예시
def test_rsi_calculation_with_valid_data_returns_correct_values():
    """유효한 데이터로 RSI 계산 시 올바른 값 반환"""
    pass

def test_macd_signal_bullish_crossover_generates_buy_signal():
    """MACD 골든 크로스 시 BUY 시그널 생성"""
    pass
```

### 테스트 구조 (AAA Pattern)

```python
def test_example():
    # Arrange (준비)
    data = create_test_data()
    strategy = RSIStrategy(period=14)
    
    # Act (실행)
    result = strategy.calculate_indicators(data)
    
    # Assert (검증)
    assert result is not None
    assert 'signal' in result.columns
    assert result['signal'].isin([-1, 0, 1]).all()
```

---

## 전략 테스트 템플릿

### 기본 테스트 세트

모든 전략은 다음 테스트를 포함해야 합니다:

```python
import pytest
import pandas as pd
import numpy as np
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.my_strategy import MyStrategy


@pytest.fixture
def sample_data():
    """테스트용 샘플 데이터 생성"""
    data_gen = SimulationDataGenerator(seed=42)
    return data_gen.generate_trend_data(periods=100, trend='bullish')


def test_strategy_initialization():
    """전략 초기화 테스트"""
    strategy = MyStrategy(param1=10)
    assert strategy.name == "MyStrategy_10"
    assert strategy.param1 == 10


def test_calculate_indicators_returns_dataframe(sample_data):
    """calculate_indicators가 DataFrame 반환"""
    strategy = MyStrategy()
    result = strategy.calculate_indicators(sample_data)
    
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(sample_data)


def test_calculate_indicators_adds_required_columns(sample_data):
    """필수 컬럼 추가 확인"""
    strategy = MyStrategy()
    result = strategy.calculate_indicators(sample_data)
    
    assert 'signal' in result.columns
    assert 'position' in result.columns


def test_signal_values_are_valid(sample_data):
    """시그널 값이 -1, 0, 1만 포함"""
    strategy = MyStrategy()
    result = strategy.calculate_indicators(sample_data)
    
    assert result['signal'].isin([-1, 0, 1]).all()


def test_position_values_are_valid(sample_data):
    """포지션 값이 0 또는 1만 포함"""
    strategy = MyStrategy()
    result = strategy.calculate_indicators(sample_data)
    
    assert result['position'].isin([0, 1]).all()


def test_no_lookahead_bias(sample_data):
    """Look-ahead bias 검증"""
    strategy = MyStrategy()
    result = strategy.calculate_indicators(sample_data)
    
    # 시그널이 현재/과거 데이터만 사용하는지 확인
    # (구현 방법은 전략마다 다름)
    assert True  # 실제 검증 로직 추가


def test_get_current_signal_returns_tuple(sample_data):
    """get_current_signal이 튜플 반환"""
    strategy = MyStrategy()
    signal, info = strategy.get_current_signal(sample_data)
    
    assert isinstance(signal, int)
    assert isinstance(info, dict)
    assert signal in [-1, 0, 1]


def test_get_all_signals_returns_list(sample_data):
    """get_all_signals가 리스트 반환"""
    strategy = MyStrategy()
    signals = strategy.get_all_signals(sample_data)
    
    assert isinstance(signals, list)


def test_strategy_with_different_parameters():
    """다양한 파라미터로 전략 테스트"""
    params = [5, 10, 20, 50]
    for param in params:
        strategy = MyStrategy(param1=param)
        assert strategy.param1 == param


def test_strategy_with_insufficient_data():
    """데이터 부족 시 처리"""
    strategy = MyStrategy(param1=50)
    short_data = pd.DataFrame({
        'open': [100] * 10,
        'high': [105] * 10,
        'low': [95] * 10,
        'close': [102] * 10,
        'volume': [1000] * 10
    })
    
    result = strategy.calculate_indicators(short_data)
    # NaN 또는 적절한 처리 확인
    assert result is not None
```

---

## 지표 계산 정확도 테스트

### RSI 예시

```python
def test_rsi_calculation_accuracy():
    """RSI 계산 정확도 검증"""
    # 알려진 입력과 출력으로 검증
    data = pd.DataFrame({
        'close': [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 
                  46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 
                  46.22, 45.64]
    })
    
    strategy = RSIStrategy(period=14)
    result = strategy.calculate_indicators(pd.DataFrame({'close': data['close'], 
                                                          'open': data['close'],
                                                          'high': data['close'],
                                                          'low': data['close'],
                                                          'volume': [1000]*len(data)}))
    
    # 마지막 RSI 값 확인 (예상값과 비교)
    last_rsi = result['rsi'].iloc[-1]
    assert 0 <= last_rsi <= 100
    # 추가 정확도 검증 (알려진 값과 비교)
```

---

## 백테스터 테스트

```python
def test_backtester_returns_results(sample_data):
    """백테스터가 결과 반환"""
    from trading_bot.backtester import Backtester
    from trading_bot.strategies.rsi_strategy import RSIStrategy
    
    strategy = RSIStrategy()
    backtester = Backtester(strategy, initial_capital=10000)
    results = backtester.run(sample_data)
    
    assert results is not None
    assert 'total_return' in results
    assert 'sharpe_ratio' in results
    assert 'max_drawdown' in results


def test_backtester_with_no_trades(sample_data):
    """거래가 없을 때 처리"""
    # 시그널이 전혀 발생하지 않는 전략
    class NoTradeStrategy:
        def __init__(self):
            self.name = "NoTrade"
        
        def calculate_indicators(self, df):
            data = df.copy()
            data['signal'] = 0  # 항상 HOLD
            data['position'] = 0
            return data
    
    backtester = Backtester(NoTradeStrategy(), initial_capital=10000)
    results = backtester.run(sample_data)
    
    assert results['num_trades'] == 0
    assert results['total_return'] == 0.0


def test_backtester_commission_impact():
    """수수료가 수익에 영향"""
    from trading_bot.backtester import Backtester
    from trading_bot.strategies.rsi_strategy import RSIStrategy
    
    data_gen = SimulationDataGenerator(seed=42)
    data = data_gen.generate_trend_data(periods=100, trend='bullish')
    
    strategy = RSIStrategy()
    
    # 수수료 없음
    backtester_no_fee = Backtester(strategy, initial_capital=10000, commission=0.0)
    results_no_fee = backtester_no_fee.run(data)
    
    # 수수료 있음
    backtester_with_fee = Backtester(strategy, initial_capital=10000, commission=0.001)
    results_with_fee = backtester_with_fee.run(data)
    
    # 수수료가 있으면 수익이 낮아야 함
    assert results_with_fee['total_return'] < results_no_fee['total_return']
```

---

## 시뮬레이션 데이터 테스트

```python
def test_simulation_data_generates_correct_length():
    """시뮬레이션 데이터 길이 확인"""
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=500)
    
    assert len(df) == 500


def test_simulation_data_has_required_columns():
    """필수 컬럼 확인"""
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=100)
    
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    for col in required_columns:
        assert col in df.columns


def test_simulation_data_ohlc_logic():
    """OHLC 로직 확인 (high >= low, close <= high, close >= low)"""
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=100)
    
    assert (df['high'] >= df['low']).all()
    assert (df['high'] >= df['close']).all()
    assert (df['low'] <= df['close']).all()


def test_simulation_data_reproducibility():
    """동일한 seed로 동일한 데이터 생성"""
    data_gen1 = SimulationDataGenerator(seed=42)
    df1 = data_gen1.generate_trend_data(periods=100)
    
    data_gen2 = SimulationDataGenerator(seed=42)
    df2 = data_gen2.generate_trend_data(periods=100)
    
    pd.testing.assert_frame_equal(df1, df2)
```

---

## 최적화 테스트

```python
def test_optimizer_finds_best_parameters():
    """최적화가 최적 파라미터 반환"""
    from trading_bot.optimizer import StrategyOptimizer
    from trading_bot.strategies.rsi_strategy import RSIStrategy
    
    data_gen = SimulationDataGenerator(seed=42)
    data = data_gen.generate_trend_data(periods=200)
    
    param_grid = {
        'period': [10, 14, 20],
        'overbought': [70, 80],
        'oversold': [20, 30]
    }
    
    optimizer = StrategyOptimizer(initial_capital=10000)
    best_result = optimizer.optimize(RSIStrategy, data, param_grid)
    
    assert 'params' in best_result
    assert 'total_return' in best_result
    assert best_result['params']['period'] in [10, 14, 20]
```

---

## 통합 테스트

```python
def test_full_workflow_from_data_to_backtest():
    """전체 워크플로우 테스트"""
    # 1. 데이터 생성
    data_gen = SimulationDataGenerator(seed=42)
    data = data_gen.generate_trend_data(periods=200, trend='bullish')
    
    # 2. 전략 생성
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    
    # 3. 백테스팅
    backtester = Backtester(strategy, initial_capital=10000)
    results = backtester.run(data)
    
    # 4. 결과 검증
    assert results['total_return'] != 0
    assert results['num_trades'] > 0
```

---

## 엣지 케이스 테스트

```python
def test_strategy_with_all_same_prices():
    """모든 가격이 동일할 때"""
    data = pd.DataFrame({
        'open': [100] * 50,
        'high': [100] * 50,
        'low': [100] * 50,
        'close': [100] * 50,
        'volume': [1000] * 50
    })
    
    strategy = RSIStrategy()
    result = strategy.calculate_indicators(data)
    
    # 에러 없이 실행되어야 함
    assert result is not None


def test_strategy_with_extreme_volatility():
    """극단적 변동성"""
    data = pd.DataFrame({
        'open': [100, 50, 200, 25, 400] * 20,
        'high': [110, 60, 210, 35, 410] * 20,
        'low': [90, 40, 190, 15, 390] * 20,
        'close': [105, 55, 205, 30, 405] * 20,
        'volume': [1000] * 100
    })
    
    strategy = RSIStrategy()
    result = strategy.calculate_indicators(data)
    
    assert result is not None
```

---

## 커버리지 목표

- **전체 커버리지**: 80% 이상
- **핵심 모듈**: 90% 이상
  - `strategy.py`
  - `backtester.py`
  - `strategies/*.py`

---

## 테스트 작성 체크리스트

### 새 전략 추가 시
- [ ] 기본 테스트 세트 구현
- [ ] 지표 계산 정확도 테스트
- [ ] 시그널 생성 로직 테스트
- [ ] Look-ahead bias 검증
- [ ] 엣지 케이스 테스트

### 새 기능 추가 시
- [ ] 단위 테스트 작성
- [ ] 통합 테스트 업데이트
- [ ] 커버리지 확인 (80% 이상)
- [ ] 에러 처리 테스트

---

## API Rate Limit 처리 패턴

외부 API를 호출하는 테스트는 rate limit을 고려해야 합니다.

### 1. 테스트 클래스에 slow 마커 추가

```python
import time
import pytest
from trading_bot.brokers.base_broker import BrokerError

@pytest.mark.slow
class TestAPIIntegration:
    """외부 API 통합 테스트"""

    def test_api_call(self, api_client):
        """API 호출 테스트"""
        try:
            result = api_client.fetch_data()
            assert result is not None
        except BrokerError as e:
            # Rate limit 에러 발생 시 테스트 건너뛰기
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in [
                'rate limit', 'too many requests', 'egw00133', '1분당 1회', 'forbidden'
            ]):
                pytest.skip(f"Rate limit exceeded: {e}")
            raise
```

### 2. 연속 API 호출 시 sleep 추가

```python
@pytest.mark.slow
class TestMultipleAPICalls:
    """여러 API 호출 테스트"""

    def test_multiple_symbols(self, api_client):
        """여러 종목 조회"""
        symbols = ['AAPL', 'MSFT', 'GOOGL']

        for i, symbol in enumerate(symbols):
            if i > 0:
                # Rate limit 방지를 위한 대기
                time.sleep(1)

            try:
                result = api_client.fetch_data(symbol)
                assert result['symbol'] == symbol
            except BrokerError as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in [
                    'rate limit', 'too many requests', 'egw00133', '1분당 1회', 'forbidden'
                ]):
                    pytest.skip(f"Rate limit exceeded: {e}")
                raise
```

### 3. Rate Limit 에러 키워드

다음 키워드를 사용하여 rate limit 에러를 감지합니다:
- `'rate limit'`: 일반적인 rate limit 메시지
- `'too many requests'`: HTTP 429 에러
- `'egw00133'`: KIS API rate limit 에러 코드
- `'1분당 1회'`: KIS API 한글 에러 메시지
- `'forbidden'`: HTTP 403 (rate limit으로 인한 접근 거부)

### 4. pytest.skip() vs pytest.xfail()

- **pytest.skip()**: Rate limit 에러는 테스트 실패가 아니므로 skip 사용
- **pytest.xfail()**: 알려진 버그나 미구현 기능에 사용

---

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 테스트 대상 모듈
- [../trading_bot/strategies/CLAUDE.md](../trading_bot/strategies/CLAUDE.md): 전략 구현 가이드
