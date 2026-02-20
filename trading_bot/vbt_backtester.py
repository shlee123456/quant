"""
VectorBT 기반 백테스터 - 기존 Backtester와 동일한 결과 인터페이스
"""

import pandas as pd
import numpy as np
import vectorbt as vbt
from typing import Dict


class VBTBacktester:
    """
    VectorBT 기반 백테스터

    기존 Backtester.run()과 동일한 Dict 키를 반환하여 호환성을 유지합니다.
    전략의 get_entries_exits() 메서드를 사용하여 벡터화된 백테스팅을 수행합니다.
    """

    def __init__(self, strategy, initial_capital: float = 10000.0,
                 position_size: float = 0.95, commission: float = 0.001):
        """
        Args:
            strategy: get_entries_exits(df)를 구현한 전략 객체
            initial_capital: 초기 자본금 (USD)
            position_size: 거래당 자본 비율 (0-1)
            commission: 수수료 비율 (0.001 = 0.1%)
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.trades = []
        self.equity_curve = []

    def run(self, df: pd.DataFrame) -> Dict:
        """
        VectorBT를 사용하여 백테스트 실행

        Args:
            df: OHLCV DataFrame (index: timestamp, columns: open/high/low/close/volume)

        Returns:
            기존 Backtester.run()과 동일한 키를 가진 Dict
        """
        if df.empty:
            return self._empty_results(df)

        entries, exits = self.strategy.get_entries_exits(df)

        # 시그널이 전혀 없는 경우
        if not entries.any() and not exits.any():
            return self._no_trade_results(df)

        close = df['close']

        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            size=self.position_size,
            size_type='percent',
            fees=self.commission,
            freq='1D',
        )

        return self._adapt_results(pf, df)

    def _adapt_results(self, pf, df: pd.DataFrame) -> Dict:
        """VBT Portfolio 결과를 레거시 Dict 형식으로 변환"""
        trades = pf.trades
        total_trades_count = int(trades.count())

        if total_trades_count == 0:
            return self._no_trade_results(df)

        final_value = float(pf.final_value())
        total_return = float(pf.total_return() * 100)

        # max_drawdown: 레거시 형식은 음수 퍼센트 (e.g., -5.2)
        raw_dd = pf.max_drawdown()
        max_drawdown = float(raw_dd * 100) if not np.isnan(raw_dd) else 0.0

        raw_sharpe = pf.sharpe_ratio()
        sharpe = float(raw_sharpe) if np.isfinite(raw_sharpe) else 0.0

        # 거래 레코드에서 통계 추출
        records = trades.records_readable
        if len(records) > 0 and 'PnL' in records.columns:
            pnl = records['PnL']
            winning = int((pnl > 0).sum())
            losing = int((pnl <= 0).sum())
            win_rate = (winning / len(records) * 100) if len(records) > 0 else 0.0
            avg_win = float(pnl[pnl > 0].mean()) if winning > 0 else 0.0
            avg_loss = float(pnl[pnl <= 0].mean()) if losing > 0 else 0.0
        else:
            winning = 0
            losing = 0
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0

        # 호환성을 위해 equity curve 저장
        self.equity_curve = pf.value().tolist()

        return {
            'initial_capital': self.initial_capital,
            'final_capital': final_value,
            'total_return': total_return,
            'total_trades': total_trades_count,
            'winning_trades': winning,
            'losing_trades': losing,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'start_date': df.index[0],
            'end_date': df.index[-1],
        }

    def _no_trade_results(self, df: pd.DataFrame) -> Dict:
        """거래가 없을 때의 결과"""
        self.equity_curve = [self.initial_capital] * len(df) if len(df) > 0 else []
        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.initial_capital,
            'total_return': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'start_date': df.index[0] if len(df) > 0 else None,
            'end_date': df.index[-1] if len(df) > 0 else None,
        }

    def _empty_results(self, df: pd.DataFrame) -> Dict:
        """빈 DataFrame일 때의 결과"""
        self.equity_curve = []
        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.initial_capital,
            'total_return': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'start_date': None,
            'end_date': None,
        }
