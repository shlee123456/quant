"""
Backtesting engine for trading strategies
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from .strategies.base_strategy import BaseStrategy
from .signal_validator import SignalValidator
from .execution_verifier import OrderExecutionVerifier
from .logging_config import get_backtester_logger, log_exception

logger = get_backtester_logger()


class Backtester:
    """
    Backtesting engine to test trading strategies on historical data
    """

    def __init__(self, strategy: BaseStrategy, initial_capital: float = 10000.0,
                 position_size: float = 0.95, commission: float = 0.001,
                 enable_verification: bool = False):
        """
        Initialize backtester

        Args:
            strategy: Trading strategy to backtest
            initial_capital: Starting capital in USD
            position_size: Fraction of capital to use per trade (0-1)
            commission: Trading commission/fee (0.001 = 0.1%)
            enable_verification: Enable signal/execution verification (default: False)
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.enable_verification = enable_verification

        # Verification
        self._signal_validator = SignalValidator()
        self._execution_verifier = OrderExecutionVerifier()

        # Results
        self.trades = []
        self.equity_curve = []

    def run(self, df: pd.DataFrame) -> Dict:
        """
        Run backtest on historical data

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary with backtest results
        """
        try:
            logger.info(f"Starting backtest with strategy: {self.strategy.name}")
            logger.debug(f"Initial capital: ${self.initial_capital}, Position size: {self.position_size}, Commission: {self.commission}")

            # Calculate indicators
            data = self.strategy.calculate_indicators(df)
            logger.debug(f"Calculated indicators for {len(data)} data points")

            # Initialize tracking variables
            capital = self.initial_capital
            position = 0  # 0 = no position, >0 = long position size
            entry_price = 0
            trades = []
            equity = []

            # Iterate through data
            for idx, row in data.iterrows():
                signal = row['signal']
                price = row['close']

                # Validate signal value
                if self.enable_verification:
                    if not self._signal_validator.validate_signal_value(int(signal)):
                        logger.warning(f"유효하지 않은 시그널 값: {signal} (index={idx})")

                # Track equity
                if position > 0:
                    current_value = capital + (position * price)
                else:
                    current_value = capital

                equity.append({
                    'timestamp': idx,
                    'equity': current_value,
                    'price': price,
                    'position': position
                })

                # Execute trades based on signals
                if signal == 1 and position == 0:  # BUY signal
                    # Enter long position
                    trade_capital = capital * self.position_size
                    position = trade_capital / price * (1 - self.commission)
                    entry_price = price
                    capital = capital - trade_capital

                    trade = {
                        'timestamp': idx,
                        'type': 'BUY',
                        'price': price,
                        'size': position,
                        'capital': capital,
                        'commission': trade_capital * self.commission
                    }
                    trades.append(trade)

                    # Verify execution
                    if self.enable_verification:
                        is_valid, msg = self._execution_verifier.verify_execution(
                            expected_signal=1, executed_trade=trade, current_position=0
                        )
                        if not is_valid:
                            logger.warning(f"실행 검증 실패: {msg}")

                elif signal == -1 and position > 0:  # SELL signal
                    # Exit long position
                    sale_proceeds = position * price * (1 - self.commission)
                    capital = capital + sale_proceeds

                    # Calculate profit/loss
                    pnl = sale_proceeds - (position * entry_price)
                    pnl_pct = (price - entry_price) / entry_price * 100

                    trade = {
                        'timestamp': idx,
                        'type': 'SELL',
                        'price': price,
                        'size': position,
                        'capital': capital,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'commission': position * price * self.commission
                    }
                    trades.append(trade)

                    # Verify execution
                    if self.enable_verification:
                        is_valid, msg = self._execution_verifier.verify_execution(
                            expected_signal=-1, executed_trade=trade, current_position=position
                        )
                        if not is_valid:
                            logger.warning(f"실행 검증 실패: {msg}")

                    position = 0
                    entry_price = 0

            # Close any open position at the end
            if position > 0:
                final_price = data.iloc[-1]['close']
                sale_proceeds = position * final_price * (1 - self.commission)
                capital = capital + sale_proceeds

                pnl = sale_proceeds - (position * entry_price)
                pnl_pct = (final_price - entry_price) / entry_price * 100

                trades.append({
                    'timestamp': data.index[-1],
                    'type': 'SELL (CLOSE)',
                    'price': final_price,
                    'size': position,
                    'capital': capital,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'commission': position * final_price * self.commission
                })

            # Store results
            self.trades = trades
            self.equity_curve = equity

            # Calculate performance metrics
            results = self._calculate_metrics(data)

            # Verify capital consistency at end of run
            if self.enable_verification:
                is_consistent, msg = self._execution_verifier.verify_capital_consistency(
                    initial_capital=self.initial_capital,
                    trades=self.trades,
                    current_capital=capital,
                )
                if not is_consistent:
                    logger.warning(f"자본금 정합성 검증 실패: {msg}")
                results['verification_report'] = self._execution_verifier.generate_verification_report()

            logger.info(f"Backtest completed: {len(trades)} trades, Total Return: {results['total_return']:.2f}%")

            return results

        except Exception as e:
            log_exception(logger, f"Error during backtest: {str(e)}")
            raise

    def _calculate_metrics(self, data: pd.DataFrame) -> Dict:
        """Calculate performance metrics"""

        # Final capital
        final_capital = self.equity_curve[-1]['equity'] if self.equity_curve else self.initial_capital

        # Total return
        total_return = ((final_capital - self.initial_capital) / self.initial_capital) * 100

        # Extract buy and sell trades
        buy_trades = [t for t in self.trades if t['type'] == 'BUY']
        sell_trades = [t for t in self.trades if 'pnl' in t]

        # Win rate
        if sell_trades:
            winning_trades = [t for t in sell_trades if t['pnl'] > 0]
            win_rate = len(winning_trades) / len(sell_trades) * 100

            avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
            avg_loss = np.mean([t['pnl'] for t in sell_trades if t['pnl'] < 0])
            avg_loss = avg_loss if not np.isnan(avg_loss) else 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0

        # Maximum drawdown
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
        max_drawdown = equity_df['drawdown'].min()

        # Sharpe ratio (simplified - assumes daily data)
        if len(equity_df) > 1:
            equity_df['returns'] = equity_df['equity'].pct_change()
            sharpe_ratio = (equity_df['returns'].mean() / equity_df['returns'].std()) * np.sqrt(252)
            sharpe_ratio = sharpe_ratio if not np.isnan(sharpe_ratio) else 0
        else:
            sharpe_ratio = 0

        results = {
            'initial_capital': self.initial_capital,
            'final_capital': final_capital,
            'total_return': total_return,
            'total_trades': len(sell_trades),
            'winning_trades': len([t for t in sell_trades if t['pnl'] > 0]),
            'losing_trades': len([t for t in sell_trades if t['pnl'] < 0]),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'start_date': data.index[0],
            'end_date': data.index[-1],
        }

        return results

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        return pd.DataFrame(self.trades)

    def get_equity_curve_df(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        return pd.DataFrame(self.equity_curve)

    def print_results(self, results: Dict):
        """Print backtest results in a formatted way"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        print(f"Strategy: {self.strategy}")
        print(f"Period: {results['start_date']} to {results['end_date']}")
        print("-"*60)
        print(f"Initial Capital: ${results['initial_capital']:,.2f}")
        print(f"Final Capital: ${results['final_capital']:,.2f}")
        print(f"Total Return: {results['total_return']:.2f}%")
        print("-"*60)
        print(f"Total Trades: {results['total_trades']}")
        print(f"Winning Trades: {results['winning_trades']}")
        print(f"Losing Trades: {results['losing_trades']}")
        print(f"Win Rate: {results['win_rate']:.2f}%")
        print(f"Average Win: ${results['avg_win']:.2f}")
        print(f"Average Loss: ${results['avg_loss']:.2f}")
        print("-"*60)
        print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
        print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
        print("="*60 + "\n")
