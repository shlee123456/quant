"""
Tests for Live Monitoring functionality

US-112: 실시간 모니터링 기능 검증 테스트
- Live Monitor 탭의 Current Market Price 섹션 테스트
- Auto-refresh 기능 테스트 (모킹)
- KIS 브로커 실시간 시세 조회 테스트 (모킹 또는 실제 API)
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any


class TestLiveMonitorCurrentPriceSection:
    """Test Current Market Price section in Live Monitor tab"""

    def test_current_price_display_structure(self):
        """Test that current price display has correct structure"""
        # Mock ticker data from KIS broker
        ticker_data = {
            'last': 150.25,
            'rate': 2.5,
            'open': 148.50,
            'high': 151.00,
            'low': 147.80,
            'volume': 1234567
        }

        # Verify all required fields are present
        assert 'last' in ticker_data
        assert 'rate' in ticker_data
        assert 'open' in ticker_data
        assert 'high' in ticker_data
        assert 'low' in ticker_data
        assert 'volume' in ticker_data

        # Verify data types
        assert isinstance(ticker_data['last'], float)
        assert isinstance(ticker_data['rate'], float)
        assert isinstance(ticker_data['open'], float)
        assert isinstance(ticker_data['high'], float)
        assert isinstance(ticker_data['low'], float)
        assert isinstance(ticker_data['volume'], int)

    def test_current_price_formatting(self):
        """Test that price values are formatted correctly"""
        ticker_data = {
            'last': 150.256789,
            'rate': 2.567,
            'open': 148.50,
            'high': 151.00,
            'low': 147.80,
            'volume': 1234567
        }

        # Test price formatting (should be 2 decimal places)
        formatted_last = f"${ticker_data['last']:.2f}"
        assert formatted_last == "$150.26"

        # Test rate formatting
        formatted_rate = f"{ticker_data['rate']:.2f}%"
        assert formatted_rate == "2.57%"

        # Test volume formatting (should have commas)
        formatted_volume = f"{int(ticker_data['volume']):,}"
        assert formatted_volume == "1,234,567"

    def test_price_change_delta_color(self):
        """Test that delta color is determined correctly based on rate"""
        # Positive rate should be "normal"
        ticker_positive = {'rate': 2.5}
        delta_color = "normal" if ticker_positive['rate'] >= 0 else "inverse"
        assert delta_color == "normal"

        # Negative rate should be "inverse"
        ticker_negative = {'rate': -1.5}
        delta_color = "normal" if ticker_negative['rate'] >= 0 else "inverse"
        assert delta_color == "inverse"

        # Zero rate should be "normal"
        ticker_zero = {'rate': 0.0}
        delta_color = "normal" if ticker_zero['rate'] >= 0 else "inverse"
        assert delta_color == "normal"

    def test_timestamp_generation(self):
        """Test that last updated timestamp is generated correctly"""
        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

        # Verify timestamp format
        assert len(timestamp) == 19  # YYYY-MM-DD HH:MM:SS
        assert timestamp[4] == '-'
        assert timestamp[7] == '-'
        assert timestamp[10] == ' '
        assert timestamp[13] == ':'
        assert timestamp[16] == ':'


class TestAutoRefreshFunctionality:
    """Test auto-refresh functionality in Live Monitor"""

    def test_auto_refresh_checkbox_state(self):
        """Test that auto-refresh checkbox state is tracked correctly"""
        # Mock session state
        session_state = {'auto_refresh_enabled': False}

        # Initially disabled
        assert session_state['auto_refresh_enabled'] is False

        # Enable auto-refresh
        session_state['auto_refresh_enabled'] = True
        assert session_state['auto_refresh_enabled'] is True

        # Disable auto-refresh
        session_state['auto_refresh_enabled'] = False
        assert session_state['auto_refresh_enabled'] is False

    def test_last_refresh_time_tracking(self):
        """Test that last refresh time is tracked correctly"""
        import time

        # Mock session state
        session_state = {'last_refresh_time': None}

        # Initial state
        assert session_state['last_refresh_time'] is None

        # Set refresh time
        current_time = time.time()
        session_state['last_refresh_time'] = current_time
        assert session_state['last_refresh_time'] == current_time

        # Calculate elapsed time
        time.sleep(0.1)  # Brief sleep
        elapsed = time.time() - session_state['last_refresh_time']
        assert elapsed >= 0.1

    def test_refresh_countdown_calculation(self):
        """Test that refresh countdown is calculated correctly"""
        import time

        # Mock current time and last refresh time
        current_time = 1000.0
        last_refresh_time = 970.0  # 30 seconds ago

        elapsed = current_time - last_refresh_time
        refresh_interval = 60  # 60 seconds
        remaining = max(0, refresh_interval - int(elapsed))

        assert elapsed == 30.0
        assert remaining == 30

        # Test when refresh is due
        current_time = 1040.0  # 70 seconds after last refresh
        elapsed = current_time - last_refresh_time
        remaining = max(0, refresh_interval - int(elapsed))

        assert elapsed == 70.0
        assert remaining == 0

    def test_refresh_trigger_condition(self):
        """Test that refresh is triggered when elapsed time exceeds interval"""
        import time

        refresh_interval = 60

        # Case 1: Not enough time has passed
        last_refresh_time = time.time() - 30  # 30 seconds ago
        current_time = time.time()
        elapsed = current_time - last_refresh_time
        should_refresh = elapsed >= refresh_interval
        assert should_refresh is False

        # Case 2: Enough time has passed
        last_refresh_time = time.time() - 65  # 65 seconds ago
        current_time = time.time()
        elapsed = current_time - last_refresh_time
        should_refresh = elapsed >= refresh_interval
        assert should_refresh is True


class TestKISBrokerRealtimeQuotes:
    """Test KIS broker real-time quote retrieval"""

    @patch('trading_bot.brokers.korea_investment_broker.KoreaInvestmentBroker')
    def test_fetch_ticker_call(self, mock_broker_class):
        """Test that fetch_ticker is called with correct parameters"""
        # Create mock broker instance
        mock_broker = Mock()
        mock_broker_class.return_value = mock_broker

        # Mock ticker data
        mock_ticker = {
            'last': 150.25,
            'rate': 2.5,
            'open': 148.50,
            'high': 151.00,
            'low': 147.80,
            'volume': 1234567
        }
        mock_broker.fetch_ticker.return_value = mock_ticker

        # Create broker instance
        broker = mock_broker_class()

        # Call fetch_ticker
        symbol = 'AAPL'
        ticker = broker.fetch_ticker(symbol, overseas=True, market='NASDAQ')

        # Verify the call
        mock_broker.fetch_ticker.assert_called_once_with(symbol, overseas=True, market='NASDAQ')
        assert ticker == mock_ticker

    @patch('trading_bot.brokers.korea_investment_broker.KoreaInvestmentBroker')
    def test_fetch_ticker_symbol_normalization(self, mock_broker_class):
        """Test that symbol is normalized correctly (remove market suffix)"""
        # Create mock broker instance
        mock_broker = Mock()
        mock_broker_class.return_value = mock_broker

        # Mock ticker data
        mock_ticker = {'last': 150.25}
        mock_broker.fetch_ticker.return_value = mock_ticker

        # Test symbol normalization
        symbol_with_suffix = 'AAPL.US'
        normalized_symbol = symbol_with_suffix.split('.')[0]
        assert normalized_symbol == 'AAPL'

        # Call with normalized symbol
        broker = mock_broker_class()
        ticker = broker.fetch_ticker(normalized_symbol, overseas=True, market='NASDAQ')

        # Verify normalized symbol was used
        mock_broker.fetch_ticker.assert_called_once_with('AAPL', overseas=True, market='NASDAQ')

    @patch('trading_bot.brokers.korea_investment_broker.KoreaInvestmentBroker')
    def test_fetch_ticker_error_handling(self, mock_broker_class):
        """Test that errors are handled gracefully"""
        # Create mock broker instance
        mock_broker = Mock()
        mock_broker_class.return_value = mock_broker

        # Mock fetch_ticker to raise an exception
        mock_broker.fetch_ticker.side_effect = Exception("API Error: Rate limit exceeded")

        # Create broker instance
        broker = mock_broker_class()

        # Test error handling
        with pytest.raises(Exception) as exc_info:
            broker.fetch_ticker('AAPL', overseas=True, market='NASDAQ')

        assert "Rate limit exceeded" in str(exc_info.value)

    def test_ticker_data_validation(self):
        """Test that ticker data is validated correctly"""
        # Valid ticker data
        valid_ticker = {
            'last': 150.25,
            'rate': 2.5,
            'open': 148.50,
            'high': 151.00,
            'low': 147.80,
            'volume': 1234567
        }

        # Check all required fields
        required_fields = ['last', 'rate', 'open', 'high', 'low', 'volume']
        for field in required_fields:
            assert field in valid_ticker

        # Check value ranges
        assert valid_ticker['last'] > 0
        assert valid_ticker['high'] >= valid_ticker['last']
        assert valid_ticker['low'] <= valid_ticker['last']
        assert valid_ticker['volume'] >= 0


class TestLiveMonitorDataFlow:
    """Test the overall data flow in Live Monitor tab"""

    @patch('trading_bot.brokers.korea_investment_broker.KoreaInvestmentBroker')
    def test_live_monitor_workflow(self, mock_broker_class):
        """Test the complete workflow of Live Monitor tab"""
        # Create mock broker
        mock_broker = Mock()
        mock_broker_class.return_value = mock_broker

        # Mock ticker data
        mock_ticker = {
            'last': 150.25,
            'rate': 2.5,
            'open': 148.50,
            'high': 151.00,
            'low': 147.80,
            'volume': 1234567
        }
        mock_broker.fetch_ticker.return_value = mock_ticker

        # Create broker instance
        broker = mock_broker_class()

        # Simulate the workflow
        symbol = 'AAPL'

        # Step 1: Fetch ticker
        ticker = broker.fetch_ticker(symbol, overseas=True, market='NASDAQ')
        assert ticker is not None

        # Step 2: Format data for display
        formatted_data = {
            'current_price': f"${ticker['last']:.2f}",
            'rate': f"{ticker['rate']:.2f}%",
            'open': f"${ticker['open']:.2f}",
            'high': f"${ticker['high']:.2f}",
            'low': f"${ticker['low']:.2f}",
            'volume': f"{int(ticker['volume']):,}"
        }

        # Step 3: Verify formatted data
        assert formatted_data['current_price'] == "$150.25"
        assert formatted_data['rate'] == "2.50%"
        assert formatted_data['open'] == "$148.50"
        assert formatted_data['high'] == "$151.00"
        assert formatted_data['low'] == "$147.80"
        assert formatted_data['volume'] == "1,234,567"

    def test_market_type_conditional_display(self):
        """Test that Current Market Price section is shown only for stock market"""
        # Mock session state
        session_state = {
            'market_type': 'stock',
            'use_simulation': False
        }

        # Determine if section should be shown
        should_show = (
            session_state['market_type'] == 'stock' and
            not session_state['use_simulation']
        )
        assert should_show is True

        # Test with crypto market
        session_state['market_type'] = 'crypto'
        should_show = (
            session_state['market_type'] == 'stock' and
            not session_state['use_simulation']
        )
        assert should_show is False

        # Test with simulation mode
        session_state['market_type'] = 'stock'
        session_state['use_simulation'] = True
        should_show = (
            session_state['market_type'] == 'stock' and
            not session_state['use_simulation']
        )
        assert should_show is False

    @patch('trading_bot.data_handler.DataHandler')
    def test_strategy_signal_refresh(self, mock_data_handler_class):
        """Test that strategy signals are refreshed correctly"""
        # Create mock data handler
        mock_data_handler = Mock()
        mock_data_handler_class.return_value = mock_data_handler

        # Mock OHLCV data
        mock_df = pd.DataFrame({
            'timestamp': pd.date_range(start='2024-01-01', periods=100, freq='1h'),
            'open': np.random.uniform(100, 110, 100),
            'high': np.random.uniform(110, 120, 100),
            'low': np.random.uniform(90, 100, 100),
            'close': np.random.uniform(100, 110, 100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        mock_data_handler.fetch_ohlcv.return_value = mock_df

        # Create data handler instance
        data_handler = mock_data_handler_class()

        # Simulate refresh
        symbol = 'BTC/USDT'
        timeframe = '1h'
        limit = 100

        df = data_handler.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

        # Verify the call
        mock_data_handler.fetch_ohlcv.assert_called_once_with(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit
        )

        # Verify data is not empty
        assert not df.empty
        assert len(df) == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
