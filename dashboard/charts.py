"""
Chart generation utilities using Plotly
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Optional


class ChartGenerator:
    """Generate interactive charts for trading dashboard"""

    def __init__(self):
        """Initialize chart generator with default styling"""
        self.colors = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#00c853',
            'danger': '#ff1744',
            'buy': '#00c853',
            'sell': '#ff1744',
            'fast_ma': '#2196f3',
            'slow_ma': '#ff9800'
        }

    def plot_equity_curve(self, equity_df: pd.DataFrame) -> go.Figure:
        """
        Plot equity curve over time

        Args:
            equity_df: DataFrame with columns ['timestamp', 'equity']

        Returns:
            Plotly figure
        """
        fig = go.Figure()

        # Equity line
        fig.add_trace(go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['equity'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color=self.colors['primary'], width=2),
            fill='tozeroy',
            fillcolor='rgba(31, 119, 180, 0.1)'
        ))

        # Layout
        fig.update_layout(
            title='Equity Curve',
            xaxis_title='Date',
            yaxis_title='Portfolio Value ($)',
            hovermode='x unified',
            template='plotly_white',
            height=400
        )

        return fig

    def plot_price_with_signals(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """
        Plot price chart with moving averages and trade signals

        Args:
            data: DataFrame with OHLCV and indicator data
            trades_df: DataFrame with trade history

        Returns:
            Plotly figure
        """
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('Price & Moving Averages', 'Volume')
        )

        # Candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Moving averages
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data['fast_ma'],
                mode='lines',
                name=f'Fast MA',
                line=dict(color=self.colors['fast_ma'], width=1.5)
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data['slow_ma'],
                mode='lines',
                name=f'Slow MA',
                line=dict(color=self.colors['slow_ma'], width=1.5)
            ),
            row=1, col=1
        )

        # Trade signals
        if not trades_df.empty:
            buy_trades = trades_df[trades_df['type'] == 'BUY']
            sell_trades = trades_df[trades_df['type'].str.contains('SELL')]

            if not buy_trades.empty:
                fig.add_trace(
                    go.Scatter(
                        x=buy_trades['timestamp'],
                        y=buy_trades['price'],
                        mode='markers',
                        name='Buy',
                        marker=dict(
                            symbol='triangle-up',
                            size=12,
                            color=self.colors['buy'],
                            line=dict(color='white', width=1)
                        )
                    ),
                    row=1, col=1
                )

            if not sell_trades.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sell_trades['timestamp'],
                        y=sell_trades['price'],
                        mode='markers',
                        name='Sell',
                        marker=dict(
                            symbol='triangle-down',
                            size=12,
                            color=self.colors['sell'],
                            line=dict(color='white', width=1)
                        )
                    ),
                    row=1, col=1
                )

        # Volume bars
        colors = [self.colors['success'] if close >= open else self.colors['danger']
                 for close, open in zip(data['close'], data['open'])]

        fig.add_trace(
            go.Bar(
                x=data.index,
                y=data['volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.5
            ),
            row=2, col=1
        )

        # Layout
        fig.update_layout(
            title='Price Chart with Trading Signals',
            xaxis2_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=600,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def plot_price_with_ma(self, data: pd.DataFrame) -> go.Figure:
        """
        Plot price with moving averages (simpler version for live monitoring)

        Args:
            data: DataFrame with OHLCV and indicator data

        Returns:
            Plotly figure
        """
        fig = go.Figure()

        # Price line
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data['close'],
            mode='lines',
            name='Price',
            line=dict(color=self.colors['primary'], width=2)
        ))

        # Moving averages
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data['fast_ma'],
            mode='lines',
            name='Fast MA',
            line=dict(color=self.colors['fast_ma'], width=1.5, dash='dash')
        ))

        fig.add_trace(go.Scatter(
            x=data.index,
            y=data['slow_ma'],
            mode='lines',
            name='Slow MA',
            line=dict(color=self.colors['slow_ma'], width=1.5, dash='dash')
        ))

        # Layout
        fig.update_layout(
            title='Price & Moving Averages',
            xaxis_title='Date',
            yaxis_title='Price ($)',
            hovermode='x unified',
            template='plotly_white',
            height=500
        )

        return fig

    def plot_drawdown(self, equity_df: pd.DataFrame) -> go.Figure:
        """
        Plot drawdown chart

        Args:
            equity_df: DataFrame with equity data

        Returns:
            Plotly figure
        """
        # Calculate drawdown
        equity_df = equity_df.copy()
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['drawdown'],
            mode='lines',
            name='Drawdown',
            line=dict(color=self.colors['danger'], width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 23, 68, 0.1)'
        ))

        fig.update_layout(
            title='Drawdown',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            hovermode='x unified',
            template='plotly_white',
            height=400
        )

        return fig

    def plot_trade_analysis(self, trades_df: pd.DataFrame) -> go.Figure:
        """
        Plot trade analysis (P&L distribution)

        Args:
            trades_df: DataFrame with trade history

        Returns:
            Plotly figure
        """
        # Filter sell trades with P&L
        sell_trades = trades_df[trades_df['type'].str.contains('SELL')].copy()

        if sell_trades.empty or 'pnl' not in sell_trades.columns:
            # Return empty figure
            fig = go.Figure()
            fig.add_annotation(
                text="No completed trades yet",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=20)
            )
            return fig

        fig = go.Figure()

        # P&L bar chart
        colors = [self.colors['success'] if pnl > 0 else self.colors['danger']
                 for pnl in sell_trades['pnl']]

        fig.add_trace(go.Bar(
            x=list(range(len(sell_trades))),
            y=sell_trades['pnl'],
            name='P&L',
            marker_color=colors,
            text=[f"${pnl:.2f}" for pnl in sell_trades['pnl']],
            textposition='outside'
        ))

        fig.update_layout(
            title='Trade P&L Analysis',
            xaxis_title='Trade Number',
            yaxis_title='Profit/Loss ($)',
            template='plotly_white',
            height=400
        )

        return fig

    def plot_strategy_chart(self, data: pd.DataFrame, trades_df: pd.DataFrame, strategy_name: str) -> go.Figure:
        """
        Plot price chart with strategy-specific indicators

        Args:
            data: DataFrame with OHLCV and indicator data
            trades_df: DataFrame with trade history
            strategy_name: Name of the strategy

        Returns:
            Plotly figure
        """
        if 'Moving Average' in strategy_name:
            return self._plot_ma_strategy(data, trades_df)
        elif 'RSI' in strategy_name:
            return self._plot_rsi_strategy(data, trades_df)
        elif 'MACD' in strategy_name:
            return self._plot_macd_strategy(data, trades_df)
        elif 'Bollinger' in strategy_name:
            return self._plot_bollinger_strategy(data, trades_df)
        elif 'Stochastic' in strategy_name:
            return self._plot_stochastic_strategy(data, trades_df)
        else:
            # Default to price with signals
            return self.plot_price_with_signals(data, trades_df)

    def _plot_ma_strategy(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """Plot Moving Average strategy chart"""
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('Price & Moving Averages', 'Volume')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Moving averages
        if 'fast_ma' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['fast_ma'],
                    mode='lines',
                    name='Fast MA',
                    line=dict(color=self.colors['fast_ma'], width=1.5)
                ),
                row=1, col=1
            )

        if 'slow_ma' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['slow_ma'],
                    mode='lines',
                    name='Slow MA',
                    line=dict(color=self.colors['slow_ma'], width=1.5)
                ),
                row=1, col=1
            )

        # Add trade signals
        self._add_trade_signals(fig, trades_df, row=1)

        # Volume
        self._add_volume(fig, data, row=2)

        fig.update_layout(
            title='Moving Average Crossover Strategy',
            xaxis2_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=600,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def _plot_rsi_strategy(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """Plot RSI strategy chart"""
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.3, 0.2],
            subplot_titles=('Price', 'RSI', 'Volume')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Add trade signals
        self._add_trade_signals(fig, trades_df, row=1)

        # RSI
        if 'rsi' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['rsi'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='purple', width=2)
                ),
                row=2, col=1
            )

            # Overbought/Oversold lines
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Overbought (70)")
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Oversold (30)")

        # Volume
        self._add_volume(fig, data, row=3)

        fig.update_layout(
            title='RSI Strategy',
            xaxis3_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='RSI',
            yaxis3_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=700,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def _plot_macd_strategy(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """Plot MACD strategy chart"""
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.3, 0.2],
            subplot_titles=('Price', 'MACD', 'Volume')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Add trade signals
        self._add_trade_signals(fig, trades_df, row=1)

        # MACD components
        if 'macd_line' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['macd_line'],
                    mode='lines',
                    name='MACD Line',
                    line=dict(color='blue', width=2)
                ),
                row=2, col=1
            )

        if 'signal_line' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['signal_line'],
                    mode='lines',
                    name='Signal Line',
                    line=dict(color='orange', width=2)
                ),
                row=2, col=1
            )

        if 'macd_histogram' in data.columns:
            colors = ['green' if val >= 0 else 'red' for val in data['macd_histogram']]
            fig.add_trace(
                go.Bar(
                    x=data.index,
                    y=data['macd_histogram'],
                    name='MACD Histogram',
                    marker_color=colors,
                    opacity=0.5
                ),
                row=2, col=1
            )

        # Volume
        self._add_volume(fig, data, row=3)

        fig.update_layout(
            title='MACD Strategy',
            xaxis3_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='MACD',
            yaxis3_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=700,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def _plot_bollinger_strategy(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """Plot Bollinger Bands strategy chart"""
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('Price & Bollinger Bands', 'Volume')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Bollinger Bands
        if 'bb_upper' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['bb_upper'],
                    mode='lines',
                    name='Upper Band',
                    line=dict(color='gray', width=1, dash='dash')
                ),
                row=1, col=1
            )

        if 'bb_middle' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['bb_middle'],
                    mode='lines',
                    name='Middle Band (SMA)',
                    line=dict(color='blue', width=1.5)
                ),
                row=1, col=1
            )

        if 'bb_lower' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['bb_lower'],
                    mode='lines',
                    name='Lower Band',
                    line=dict(color='gray', width=1, dash='dash'),
                    fill='tonexty',
                    fillcolor='rgba(128, 128, 128, 0.1)'
                ),
                row=1, col=1
            )

        # Add trade signals
        self._add_trade_signals(fig, trades_df, row=1)

        # Volume
        self._add_volume(fig, data, row=2)

        fig.update_layout(
            title='Bollinger Bands Strategy',
            xaxis2_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=600,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def _plot_stochastic_strategy(self, data: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
        """Plot Stochastic Oscillator strategy chart"""
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.3, 0.2],
            subplot_titles=('Price', 'Stochastic Oscillator', 'Volume')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price',
                increasing_line_color=self.colors['success'],
                decreasing_line_color=self.colors['danger']
            ),
            row=1, col=1
        )

        # Add trade signals
        self._add_trade_signals(fig, trades_df, row=1)

        # Stochastic lines
        if 'stoch_k' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['stoch_k'],
                    mode='lines',
                    name='%K',
                    line=dict(color='blue', width=2)
                ),
                row=2, col=1
            )

        if 'stoch_d' in data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['stoch_d'],
                    mode='lines',
                    name='%D',
                    line=dict(color='orange', width=2)
                ),
                row=2, col=1
            )

        # Overbought/Oversold lines
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Overbought (80)")
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Oversold (20)")

        # Volume
        self._add_volume(fig, data, row=3)

        fig.update_layout(
            title='Stochastic Oscillator Strategy',
            xaxis3_title='Date',
            yaxis_title='Price ($)',
            yaxis2_title='Stochastic',
            yaxis3_title='Volume',
            hovermode='x unified',
            template='plotly_white',
            height=700,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )

        return fig

    def _add_trade_signals(self, fig: go.Figure, trades_df: pd.DataFrame, row: int = 1):
        """Add buy/sell signals to chart"""
        if trades_df.empty:
            return

        buy_trades = trades_df[trades_df['type'] == 'BUY']
        sell_trades = trades_df[trades_df['type'].str.contains('SELL')]

        if not buy_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_trades['timestamp'],
                    y=buy_trades['price'],
                    mode='markers',
                    name='Buy',
                    marker=dict(
                        symbol='triangle-up',
                        size=12,
                        color=self.colors['buy'],
                        line=dict(color='white', width=1)
                    )
                ),
                row=row, col=1
            )

        if not sell_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_trades['timestamp'],
                    y=sell_trades['price'],
                    mode='markers',
                    name='Sell',
                    marker=dict(
                        symbol='triangle-down',
                        size=12,
                        color=self.colors['sell'],
                        line=dict(color='white', width=1)
                    )
                ),
                row=row, col=1
            )

    def _add_volume(self, fig: go.Figure, data: pd.DataFrame, row: int):
        """Add volume bars to chart"""
        colors = [self.colors['success'] if close >= open else self.colors['danger']
                 for close, open in zip(data['close'], data['open'])]

        fig.add_trace(
            go.Bar(
                x=data.index,
                y=data['volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.5,
                showlegend=False
            ),
            row=row, col=1
        )
