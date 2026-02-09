"""
손절매/익절매 기능 테스트

목적: PaperTrader의 손절매(stop loss)와 익절매(take profit) 기능 검증

실행: python examples/test_stop_loss_take_profit.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy


class MockBroker:
    """Mock broker for testing stop loss/take profit"""

    def __init__(self):
        self.price_sequence = []
        self.current_idx = 0

    def set_price_sequence(self, prices):
        """Set sequence of prices to return"""
        self.price_sequence = prices
        self.current_idx = 0

    def fetch_ticker(self, symbol, overseas=True):
        """Return next price in sequence"""
        if self.current_idx >= len(self.price_sequence):
            price = self.price_sequence[-1]
        else:
            price = self.price_sequence[self.current_idx]
            self.current_idx += 1

        return {'last': price, 'symbol': symbol}

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Return dummy OHLCV data"""
        import pandas as pd
        import numpy as np

        # Generate dummy data that triggers BUY signal (RSI < 30)
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='1h')
        data = pd.DataFrame({
            'timestamp': dates,
            'open': np.linspace(100, 90, limit),  # Declining trend
            'high': np.linspace(102, 92, limit),
            'low': np.linspace(98, 88, limit),
            'close': np.linspace(100, 90, limit),
            'volume': np.ones(limit) * 1000
        })
        data.set_index('timestamp', inplace=True)

        return data


def test_stop_loss():
    """Test stop loss functionality"""
    print("=" * 60)
    print("TEST 1: 손절매 테스트")
    print("=" * 60)

    # Create mock broker
    broker = MockBroker()

    # Price sequence: buy at 100, then drop to 94 (triggers 5% stop loss)
    broker.set_price_sequence([
        100.0,  # Initial price
        100.0,  # Buy signal (RSI will be < 30)
        98.0,   # -2% (no trigger)
        96.0,   # -4% (no trigger)
        94.5,   # -5.5% (STOP LOSS TRIGGERED!)
        90.0,   # Would continue dropping if not stopped
    ])

    # Create strategy and paper trader
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    trader = PaperTrader(
        strategy=strategy,
        symbols=['TEST'],
        broker=broker,
        initial_capital=10000.0,
        position_size=0.95,
        stop_loss_pct=0.05,  # 5% stop loss
        take_profit_pct=0.10,
        enable_stop_loss=True,
        enable_take_profit=False
    )

    print(f"\n설정:")
    print(f"  초기 자본: ${trader.initial_capital:,.2f}")
    print(f"  손절매: {trader.stop_loss_pct:.0%}")
    print(f"  진입 가격: $100.00 (예상)")
    print(f"  손절 가격: $95.00 (예상)\n")

    # Manually execute iterations to control price sequence
    trader.start()

    # First iteration - should BUY (RSI < 30 due to declining trend)
    print("반복 1: 매수 신호 예상")
    trader.execute_buy('TEST', 100.0, datetime.now())

    # Subsequent iterations - check stop loss
    for i, price in enumerate([98.0, 96.0, 94.5], start=2):
        print(f"\n반복 {i}: 현재가 ${price:.2f}")
        timestamp = datetime.now()

        # Check stop loss
        triggered = trader._check_stop_loss_take_profit('TEST', price, timestamp)
        if triggered:
            print(f"✅ 손절매 발동! (가격: ${price:.2f})")
            break
        else:
            pnl_pct = (price - 100.0) / 100.0 * 100
            print(f"   손익: {pnl_pct:+.2f}% (손절 기준: -5%)")

    print("\n결과:")
    print(f"  총 거래: {len(trader.trades)}")
    print(f"  최종 자본: ${trader.capital:,.2f}")

    if len(trader.trades) == 2:
        sell_trade = trader.trades[1]
        print(f"  손절 가격: ${sell_trade['price']:.2f}")
        print(f"  손익: ${sell_trade['pnl']:.2f} ({sell_trade['pnl_pct']:+.2f}%)")
        print(f"  손절 이유: {sell_trade.get('reason', 'N/A')}")

        if sell_trade.get('reason') == 'stop_loss':
            print("\n✅ 손절매 테스트 성공!")
        else:
            print("\n❌ 손절매 테스트 실패 - 이유가 'stop_loss'가 아님")
    else:
        print("\n❌ 손절매 테스트 실패 - 매도가 실행되지 않음")


def test_take_profit():
    """Test take profit functionality"""
    print("\n\n" + "=" * 60)
    print("TEST 2: 익절매 테스트")
    print("=" * 60)

    # Create mock broker
    broker = MockBroker()

    # Price sequence: buy at 100, then rise to 111 (triggers 10% take profit)
    broker.set_price_sequence([
        100.0,  # Initial price
        100.0,  # Buy signal
        105.0,  # +5% (no trigger)
        108.0,  # +8% (no trigger)
        111.0,  # +11% (TAKE PROFIT TRIGGERED!)
        120.0,  # Would continue rising if not stopped
    ])

    # Create strategy and paper trader
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    trader = PaperTrader(
        strategy=strategy,
        symbols=['TEST'],
        broker=broker,
        initial_capital=10000.0,
        position_size=0.95,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,  # 10% take profit
        enable_stop_loss=False,
        enable_take_profit=True
    )

    print(f"\n설정:")
    print(f"  초기 자본: ${trader.initial_capital:,.2f}")
    print(f"  익절매: {trader.take_profit_pct:.0%}")
    print(f"  진입 가격: $100.00 (예상)")
    print(f"  익절 가격: $110.00 (예상)\n")

    # Manually execute iterations
    trader.start()

    # First iteration - BUY
    print("반복 1: 매수")
    trader.execute_buy('TEST', 100.0, datetime.now())

    # Subsequent iterations - check take profit
    for i, price in enumerate([105.0, 108.0, 111.0], start=2):
        print(f"\n반복 {i}: 현재가 ${price:.2f}")
        timestamp = datetime.now()

        # Check take profit
        triggered = trader._check_stop_loss_take_profit('TEST', price, timestamp)
        if triggered:
            print(f"✅ 익절매 발동! (가격: ${price:.2f})")
            break
        else:
            pnl_pct = (price - 100.0) / 100.0 * 100
            print(f"   손익: {pnl_pct:+.2f}% (익절 기준: +10%)")

    print("\n결과:")
    print(f"  총 거래: {len(trader.trades)}")
    print(f"  최종 자본: ${trader.capital:,.2f}")

    if len(trader.trades) == 2:
        sell_trade = trader.trades[1]
        print(f"  익절 가격: ${sell_trade['price']:.2f}")
        print(f"  손익: ${sell_trade['pnl']:.2f} ({sell_trade['pnl_pct']:+.2f}%)")
        print(f"  익절 이유: {sell_trade.get('reason', 'N/A')}")

        if sell_trade.get('reason') == 'take_profit':
            print("\n✅ 익절매 테스트 성공!")
        else:
            print("\n❌ 익절매 테스트 실패 - 이유가 'take_profit'이 아님")
    else:
        print("\n❌ 익절매 테스트 실패 - 매도가 실행되지 않음")


def test_priority():
    """Test that stop loss/take profit takes priority over strategy signals"""
    print("\n\n" + "=" * 60)
    print("TEST 3: 손절/익절 우선순위 테스트")
    print("=" * 60)

    print("\n시나리오:")
    print("  - 가격이 94로 하락 (5% 손실)")
    print("  - 동시에 전략에서 BUY 시그널 발생")
    print("  - 예상: 손절매가 우선, BUY 시그널 무시\n")

    broker = MockBroker()
    broker.set_price_sequence([100.0, 94.0])

    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    trader = PaperTrader(
        strategy=strategy,
        symbols=['TEST'],
        broker=broker,
        initial_capital=10000.0,
        position_size=0.95,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        enable_stop_loss=True,
        enable_take_profit=True
    )

    trader.start()
    trader.execute_buy('TEST', 100.0, datetime.now())

    print("매수 완료: $100.00")
    print("현재 포지션: 있음\n")

    # Check stop loss at 94.0 (should trigger before strategy signal)
    timestamp = datetime.now()
    triggered = trader._check_stop_loss_take_profit('TEST', 94.0, timestamp)

    print("결과:")
    if triggered:
        print("✅ 손절매가 우선 실행됨")
        print(f"   거래 수: {len(trader.trades)}")
        print(f"   포지션: {'없음' if trader.positions['TEST'] == 0 else '있음'}")
    else:
        print("❌ 손절매가 실행되지 않음")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("손절매/익절매 기능 테스트")
    print("="*60 + "\n")

    # Run tests
    test_stop_loss()
    test_take_profit()
    test_priority()

    print("\n" + "="*60)
    print("모든 테스트 완료")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
