"""
Simulation data generator for backtesting without exchange connection
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class SimulationDataGenerator:
    """
    Generate simulated OHLCV data for backtesting

    Uses Geometric Brownian Motion to simulate realistic price movements
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize simulation data generator

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        # Create a RandomState instance for reproducible random number generation
        if seed is not None:
            self.rng = np.random.RandomState(seed)
        else:
            self.rng = np.random.RandomState()

    def generate_ohlcv(
        self,
        initial_price: float = 50000.0,
        periods: int = 1000,
        timeframe: str = '1h',
        drift: float = 0.0001,
        volatility: float = 0.02,
        start_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Generate OHLCV data using Geometric Brownian Motion

        Args:
            initial_price: Starting price
            periods: Number of periods to generate
            timeframe: Time interval between periods (e.g., '1h', '1d')
            drift: Drift parameter (trend direction, μ)
            volatility: Volatility parameter (σ)
            start_date: Starting datetime (default: now - periods * timeframe)

        Returns:
            DataFrame with OHLCV data
        """
        # Parse timeframe
        timeframe_delta = self._parse_timeframe(timeframe)

        # Generate timestamps
        if start_date is None:
            # Use fixed date if seed is provided for reproducibility
            if self.seed is not None:
                start_date = datetime(2024, 1, 1) - (periods * timeframe_delta)
            else:
                start_date = datetime.now() - (periods * timeframe_delta)

        timestamps = [start_date + i * timeframe_delta for i in range(periods)]

        # Generate closing prices using Geometric Brownian Motion
        # dS = μ * S * dt + σ * S * dW
        dt = 1.0  # time step
        prices = [initial_price]

        for i in range(1, periods):
            random_shock = self.rng.normal(0, 1)
            price_change = drift * prices[-1] * dt + volatility * prices[-1] * random_shock * np.sqrt(dt)
            new_price = max(prices[-1] + price_change, 0.01)  # Prevent negative prices
            prices.append(new_price)

        # Generate OHLC from closing prices
        data = []
        for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
            # Add realistic intrabar movements
            intrabar_volatility = volatility * 0.5
            high = close * (1 + abs(self.rng.normal(0, intrabar_volatility)))
            low = close * (1 - abs(self.rng.normal(0, intrabar_volatility)))

            # Ensure OHLC consistency: low <= open,close <= high
            open_price = prices[i-1] if i > 0 else initial_price
            open_price = np.clip(open_price, low, high)
            close = np.clip(close, low, high)

            # Generate volume (correlated with volatility)
            base_volume = 100000
            volume = base_volume * (1 + abs(self.rng.normal(0, 0.5)))

            data.append({
                'timestamp': timestamp,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)

        return df

    def generate_trend_data(
        self,
        initial_price: float = 50000.0,
        periods: int = 1000,
        timeframe: str = '1h',
        trend: str = 'bullish',
        volatility: float = 0.02
    ) -> pd.DataFrame:
        """
        Generate trending market data

        Args:
            initial_price: Starting price
            periods: Number of periods
            timeframe: Time interval
            trend: Market trend - 'bullish', 'bearish', or 'sideways'
            volatility: Price volatility

        Returns:
            DataFrame with OHLCV data
        """
        # Set drift based on trend
        drift_map = {
            'bullish': 0.0005,
            'bearish': -0.0005,
            'sideways': 0.0
        }

        drift = drift_map.get(trend, 0.0)

        return self.generate_ohlcv(
            initial_price=initial_price,
            periods=periods,
            timeframe=timeframe,
            drift=drift,
            volatility=volatility
        )

    def generate_volatile_data(
        self,
        initial_price: float = 50000.0,
        periods: int = 1000,
        timeframe: str = '1h'
    ) -> pd.DataFrame:
        """
        Generate highly volatile market data

        Args:
            initial_price: Starting price
            periods: Number of periods
            timeframe: Time interval

        Returns:
            DataFrame with OHLCV data
        """
        return self.generate_ohlcv(
            initial_price=initial_price,
            periods=periods,
            timeframe=timeframe,
            drift=0.0,
            volatility=0.05  # High volatility
        )

    def generate_cyclical_data(
        self,
        initial_price: float = 50000.0,
        periods: int = 1000,
        timeframe: str = '1h',
        cycle_length: int = 100,
        amplitude: float = 0.1
    ) -> pd.DataFrame:
        """
        Generate cyclical market data with sine wave pattern

        Args:
            initial_price: Starting price
            periods: Number of periods
            timeframe: Time interval
            cycle_length: Length of one complete cycle
            amplitude: Amplitude of the cycle (as fraction of price)

        Returns:
            DataFrame with OHLCV data
        """
        # Parse timeframe
        timeframe_delta = self._parse_timeframe(timeframe)

        # Generate timestamps
        # Use fixed date if seed is provided for reproducibility
        if self.seed is not None:
            start_date = datetime(2024, 1, 1) - (periods * timeframe_delta)
        else:
            start_date = datetime.now() - (periods * timeframe_delta)
        timestamps = [start_date + i * timeframe_delta for i in range(periods)]

        # Generate prices with sine wave pattern
        prices = []
        for i in range(periods):
            cycle_position = (i % cycle_length) / cycle_length
            sine_component = np.sin(2 * np.pi * cycle_position)
            trend_price = initial_price * (1 + amplitude * sine_component)

            # Add random noise
            noise = self.rng.normal(0, 0.01)
            price = trend_price * (1 + noise)
            prices.append(max(price, 0.01))

        # Generate OHLC from closing prices
        data = []
        for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
            intrabar_volatility = 0.01
            high = close * (1 + abs(self.rng.normal(0, intrabar_volatility)))
            low = close * (1 - abs(self.rng.normal(0, intrabar_volatility)))

            open_price = prices[i-1] if i > 0 else initial_price
            open_price = np.clip(open_price, low, high)
            close = np.clip(close, low, high)

            volume = 100000 * (1 + abs(self.rng.normal(0, 0.5)))

            data.append({
                'timestamp': timestamp,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)

        return df

    def _parse_timeframe(self, timeframe: str) -> timedelta:
        """
        Parse timeframe string to timedelta

        Args:
            timeframe: Timeframe string (e.g., '1h', '1d', '4h')

        Returns:
            timedelta object
        """
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        unit_map = {
            'm': timedelta(minutes=value),
            'h': timedelta(hours=value),
            'd': timedelta(days=value),
            'w': timedelta(weeks=value)
        }

        return unit_map.get(unit, timedelta(hours=value))

    def add_market_shock(
        self,
        df: pd.DataFrame,
        shock_date: datetime,
        shock_magnitude: float = -0.2
    ) -> pd.DataFrame:
        """
        Add a market shock (sudden price drop/spike) to existing data

        Args:
            df: Existing OHLCV DataFrame
            shock_date: When the shock occurs
            shock_magnitude: Magnitude of shock (negative for crash, positive for spike)

        Returns:
            DataFrame with shock applied
        """
        data = df.copy()

        # Find the closest timestamp to shock_date
        time_diffs = abs(data.index - shock_date)
        closest_idx = time_diffs.argmin()

        # Apply shock from that point forward
        shock_multiplier = 1 + shock_magnitude

        for col in ['open', 'high', 'low', 'close']:
            data.loc[data.index >= data.index[closest_idx], col] *= shock_multiplier

        return data
