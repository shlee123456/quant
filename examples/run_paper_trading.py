"""
Paper Trading Example - Real-time simulation with live market data

This example demonstrates how to use the PaperTrader class to run
real-time simulations with actual market data.

Requirements:
- KIS API credentials (see README.md for setup)
- Environment variables set in .env file
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy
from trading_bot.database import TradingDatabase


def main():
    """Run paper trading example"""

    # Initialize database for session tracking
    db = TradingDatabase()
    print(f"Database initialized at: {db.db_path}")

    # Choose a strategy
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    print(f"Strategy: {strategy.name}")

    # Initialize broker (requires KIS API credentials)
    try:
        from dashboard.kis_broker import get_kis_broker
        broker = get_kis_broker()
        print("✓ Broker initialized (KIS)")
    except Exception as e:
        print(f"✗ Failed to initialize broker: {e}")
        print("\nPlease check:")
        print("1. .env file exists with KIS API credentials")
        print("2. KIS_APPKEY, KIS_APPSECRET, KIS_ACCOUNT are set")
        print("\nSee README.md for API setup instructions.")
        return

    # Select symbols to trade
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    print(f"Symbols: {', '.join(symbols)}")

    # Create paper trader
    trader = PaperTrader(
        strategy=strategy,
        symbols=symbols,
        broker=broker,
        initial_capital=10000.0,
        position_size=0.3,  # Use 30% of capital per trade
        db=db
    )

    # Configuration summary
    print("\n" + "="*60)
    print("PAPER TRADING CONFIGURATION")
    print("="*60)
    print(f"Initial Capital: ${trader.initial_capital:,.2f}")
    print(f"Position Size: {trader.position_size:.0%}")
    print(f"Symbols: {len(trader.symbols)} stocks")
    print(f"Strategy: {strategy.name}")
    print(f"Database: Enabled")
    print("="*60)

    # Ask user to confirm
    print("\nPress Enter to start paper trading (Ctrl+C to stop)...")
    input()

    try:
        # Run real-time paper trading
        # Updates every 60 seconds
        # Fetches live market data and executes trades based on signals
        trader.run_realtime(interval_seconds=60, timeframe='1d')

    except KeyboardInterrupt:
        print("\n\nStopping paper trading...")
        trader.stop()

        # Display session summary
        if trader.session_id:
            print(f"\nSession ID: {trader.session_id}")
            summary = db.get_session_summary(trader.session_id)

            if summary:
                print("\nSession Summary:")
                print(f"  Final Capital: ${summary['final_capital']:,.2f}")
                print(f"  Total Return: {summary['total_return']:.2f}%")
                print(f"  Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
                print(f"  Max Drawdown: {summary['max_drawdown']:.2f}%")
                print(f"  Win Rate: {summary['win_rate']:.2f}%")

                # Display trades
                trades = db.get_session_trades(trader.session_id)
                print(f"\n  Total Trades: {len(trades)}")

                if trades:
                    print("\n  Recent Trades:")
                    for trade in trades[-5:]:  # Last 5 trades
                        print(f"    {trade['type']:4} {trade['symbol']:6} "
                              f"${trade['price']:8.2f} x {trade['size']:8.2f}")

        print("\n✓ Paper trading session completed")
        print(f"\nView session history in dashboard:")
        print("  streamlit run dashboard/app.py")
        print("  Navigate to 'Session Comparison' tab")

    except Exception as e:
        print(f"\n✗ Error during paper trading: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
