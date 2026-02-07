"""
Data handler for fetching and managing cryptocurrency market data
"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
import time


class DataHandler:
    """Handles fetching and managing market data from crypto exchanges"""

    def __init__(self, exchange_name: str = 'binance', api_key: str = '', api_secret: str = ''):
        """
        Initialize data handler

        Args:
            exchange_name: Name of the exchange (default: binance)
            api_key: API key for authenticated requests
            api_secret: API secret for authenticated requests
        """
        self.exchange_name = exchange_name

        # Initialize exchange
        exchange_class = getattr(ccxt, exchange_name)
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h',
                    since: Optional[datetime] = None,
                    limit: int = 500) -> pd.DataFrame:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data

        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1m', '5m', '1h', '1d')
            since: Start datetime for historical data
            limit: Number of candles to fetch

        Returns:
            DataFrame with OHLCV data
        """
        if since:
            since_timestamp = int(since.timestamp() * 1000)
        else:
            since_timestamp = None

        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since_timestamp,
                limit=limit
            )

            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            return df

        except Exception as e:
            print(f"Error fetching OHLCV data: {e}")
            return pd.DataFrame()

    def fetch_historical_data(self, symbol: str, timeframe: str,
                             start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch historical data for a date range

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with historical OHLCV data
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        all_data = []
        current_dt = start_dt

        # Fetch data in chunks (exchange limits apply)
        while current_dt < end_dt:
            print(f"Fetching data from {current_dt.strftime('%Y-%m-%d')}...")

            df = self.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=current_dt,
                limit=1000
            )

            if df.empty:
                break

            all_data.append(df)

            # Move to next chunk
            current_dt = df.index[-1].to_pydatetime() + timedelta(milliseconds=1)

            # Respect rate limits
            time.sleep(self.exchange.rateLimit / 1000)

            # Stop if we've reached the end date
            if current_dt >= end_dt:
                break

        if all_data:
            combined_df = pd.concat(all_data)
            # Remove duplicates and filter by date range
            combined_df = combined_df[~combined_df.index.duplicated(keep='first')]
            combined_df = combined_df[
                (combined_df.index >= start_dt) &
                (combined_df.index <= end_dt)
            ]
            return combined_df.sort_index()

        return pd.DataFrame()

    def get_current_price(self, symbol: str) -> float:
        """
        Get current market price for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Current price
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            print(f"Error fetching current price: {e}")
            return 0.0

    def save_to_csv(self, df: pd.DataFrame, filepath: str):
        """Save DataFrame to CSV file"""
        df.to_csv(filepath)
        print(f"Data saved to {filepath}")

    def load_from_csv(self, filepath: str) -> pd.DataFrame:
        """Load DataFrame from CSV file"""
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        return df
