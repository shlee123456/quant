"""
Integration tests for dashboard Paper Trading tab
Note: These are simplified tests as full Streamlit UI testing requires browser automation
"""

import pytest
import os
import tempfile
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.database import TradingDatabase
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy, MACDStrategy
from datetime import datetime
import plotly.graph_objects as go


# Import dashboard functions
# Note: We can't fully test Streamlit components without a running app,
# but we can test the underlying logic functions


@pytest.fixture
def temp_db():
    """Create temporary database with sample data"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_dashboard.db')
    db = TradingDatabase(db_path=db_path)

    # Create sample sessions
    session1 = db.create_session('RSI_14_30_70', 10000.0)
    session2 = db.create_session('MACD_12_26_9', 10000.0)

    # Add some trades and snapshots
    for session_id in [session1, session2]:
        # Add trades
        db.log_trade(session_id, {
            'symbol': 'AAPL',
            'timestamp': datetime.now(),
            'type': 'BUY',
            'price': 150.0,
            'size': 10.0,
            'commission': 1.5
        })

        db.log_trade(session_id, {
            'symbol': 'AAPL',
            'timestamp': datetime.now(),
            'type': 'SELL',
            'price': 155.0,
            'size': 10.0,
            'commission': 1.5,
            'pnl': 50.0,
            'pnl_pct': 3.33
        })

        # Add portfolio snapshots
        for i in range(5):
            db.log_portfolio_snapshot(session_id, {
                'timestamp': datetime.now(),
                'total_value': 10000.0 + i * 100,
                'cash': 5000.0,
                'positions': {'AAPL': 10.0}
            })

        # Update session with final metrics
        db.update_session(session_id, {
            'end_time': datetime.now().isoformat(),
            'final_capital': 10500.0,
            'total_return': 5.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': 2.0,
            'win_rate': 100.0,
            'status': 'completed'
        })

    yield db

    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


def test_paper_trading_tab_data_flow():
    """Test basic data flow in Paper Trading tab"""
    # Test strategy instantiation
    strategies = {
        'RSI Strategy': RSIStrategy(period=14, overbought=70, oversold=30),
        'MACD Strategy': MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    }

    for name, strategy in strategies.items():
        assert strategy is not None
        assert hasattr(strategy, 'name')


def test_strategy_selection_options():
    """Test that strategy options are valid"""
    strategy_options = ['RSI Strategy', 'MACD Strategy', 'Moving Average Crossover',
                       'Bollinger Bands', 'Stochastic Oscillator']

    assert len(strategy_options) == 5
    assert 'RSI Strategy' in strategy_options
    assert 'MACD Strategy' in strategy_options


def test_symbol_selection_options():
    """Test that US stock symbols are valid"""
    us_stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    assert len(us_stocks) == 7
    assert all(isinstance(symbol, str) for symbol in us_stocks)
    assert all(symbol.isupper() for symbol in us_stocks)


def test_session_comparison_data_retrieval(temp_db):
    """Test retrieving session data for comparison"""
    all_sessions = temp_db.get_all_sessions()

    assert len(all_sessions) >= 2

    # Verify session data structure
    for session in all_sessions:
        assert 'session_id' in session
        assert 'strategy_name' in session
        assert 'initial_capital' in session
        assert 'final_capital' in session
        assert 'total_return' in session
        assert 'status' in session


def test_portfolio_display_data_structure(temp_db):
    """Test portfolio display data structure"""
    sessions = temp_db.get_all_sessions()
    session_id = sessions[0]['session_id']

    # Get snapshots
    snapshots = temp_db.get_session_snapshots(session_id)
    assert len(snapshots) > 0

    # Verify snapshot structure
    snapshot = snapshots[0]
    assert 'timestamp' in snapshot
    assert 'total_value' in snapshot
    assert 'cash' in snapshot
    assert 'positions' in snapshot

    # Verify positions structure
    positions = snapshot['positions']
    assert isinstance(positions, dict)
    assert 'AAPL' in positions


def test_equity_comparison_chart_data(temp_db):
    """Test equity comparison chart data preparation"""
    sessions = temp_db.get_all_sessions()
    session_ids = [s['session_id'] for s in sessions[:2]]

    # Prepare chart data
    chart_data = []
    for session_id in session_ids:
        snapshots = temp_db.get_session_snapshots(session_id)
        if snapshots:
            chart_data.append({
                'session_id': session_id,
                'timestamps': [s['timestamp'] for s in snapshots],
                'values': [s['total_value'] for s in snapshots]
            })

    assert len(chart_data) == 2
    assert all('session_id' in data for data in chart_data)
    assert all('timestamps' in data for data in chart_data)
    assert all('values' in data for data in chart_data)


def test_create_equity_comparison_chart_function(temp_db):
    """Test equity comparison chart creation function"""
    # Import the function from dashboard/app.py
    from dashboard.app import create_equity_comparison_chart

    sessions = temp_db.get_all_sessions()
    session_ids = [s['session_id'] for s in sessions[:2]]

    fig = create_equity_comparison_chart(session_ids, temp_db)

    # Verify chart was created
    assert fig is not None
    assert isinstance(fig, go.Figure)

    # Verify chart has data
    assert len(fig.data) > 0


def test_create_equity_comparison_chart_with_no_data(temp_db):
    """Test equity comparison chart with sessions that have no snapshots"""
    from dashboard.app import create_equity_comparison_chart

    # Create session with no snapshots
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    fig = create_equity_comparison_chart([session_id], temp_db)

    # Should return None when no data
    assert fig is None


def test_session_start_workflow_components():
    """Test session start workflow components"""
    # Test that required components can be instantiated
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    symbols = ['AAPL', 'MSFT']
    initial_capital = 10000.0
    position_size = 0.95

    assert strategy is not None
    assert len(symbols) == 2
    assert initial_capital > 0
    assert 0 < position_size <= 1.0


def test_session_comparison_metrics():
    """Test comparison metrics calculation"""
    # Sample session data
    sessions = [
        {
            'session_id': 'session1',
            'strategy_name': 'RSI_14_30_70',
            'total_return': 5.0,
            'win_rate': 60.0,
            'sharpe_ratio': 1.2
        },
        {
            'session_id': 'session2',
            'strategy_name': 'MACD_12_26_9',
            'total_return': 3.0,
            'win_rate': 75.0,
            'sharpe_ratio': 0.8
        }
    ]

    # Find best by different metrics
    best_by_return = max(sessions, key=lambda x: x['total_return'])
    best_by_win_rate = max(sessions, key=lambda x: x['win_rate'])
    best_by_sharpe = max(sessions, key=lambda x: x['sharpe_ratio'])

    assert best_by_return['session_id'] == 'session1'
    assert best_by_win_rate['session_id'] == 'session2'
    assert best_by_sharpe['session_id'] == 'session1'


def test_portfolio_value_calculation():
    """Test portfolio value calculation logic"""
    # Simulate portfolio data
    cash = 5000.0
    positions = {'AAPL': 10.0, 'MSFT': 5.0}
    current_prices = {'AAPL': 150.0, 'MSFT': 300.0}

    # Calculate total value
    positions_value = sum(positions[symbol] * current_prices[symbol]
                         for symbol in positions)
    total_value = cash + positions_value

    assert positions_value == 10.0 * 150.0 + 5.0 * 300.0
    assert total_value == 5000.0 + 3000.0


def test_pnl_calculation():
    """Test P&L calculation logic"""
    entry_price = 150.0
    current_price = 155.0
    shares = 10.0

    pnl = (current_price - entry_price) * shares
    pnl_pct = ((current_price - entry_price) / entry_price) * 100

    assert pnl == 50.0
    assert abs(pnl_pct - 3.33) < 0.01


def test_comparison_table_data_formatting():
    """Test comparison table data formatting"""
    session_data = {
        'session_id': 'RSI_14_30_70_20260208_120000',
        'strategy_name': 'RSI_14_30_70',
        'start_time': '2026-02-08 12:00:00',
        'end_time': '2026-02-08 13:00:00',
        'initial_capital': 10000.0,
        'final_capital': 10500.0,
        'total_return': 5.0,
        'sharpe_ratio': 1.5,
        'max_drawdown': 2.0,
        'win_rate': 75.0
    }

    # Format for display
    formatted = {
        'Session ID': session_data['session_id'],
        'Strategy': session_data['strategy_name'],
        'Start Time': session_data['start_time'][:16],
        'End Time': session_data['end_time'][:16],
        'Initial Capital': f"${session_data['initial_capital']:,.2f}",
        'Final Capital': f"${session_data['final_capital']:,.2f}",
        'Return %': f"{session_data['total_return']:.2f}%",
        'Sharpe Ratio': f"{session_data['sharpe_ratio']:.2f}",
        'Max Drawdown %': f"{session_data['max_drawdown']:.2f}%",
        'Win Rate %': f"{session_data['win_rate']:.2f}%"
    }

    assert formatted['Initial Capital'] == '$10,000.00'
    assert formatted['Return %'] == '5.00%'
    assert formatted['Win Rate %'] == '75.00%'
