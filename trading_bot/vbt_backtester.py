"""
VectorBT 기반 백테스터 - 기존 Backtester와 동일한 결과 인터페이스
"""

import pandas as pd
import numpy as np
try:
    import vectorbt as vbt
    _has_vbt = True
except ImportError:
    _has_vbt = False
from typing import Dict


class VBTBacktester:
    """
    VectorBT 기반 백테스터

    기존 Backtester.run()과 동일한 Dict 키를 반환하여 호환성을 유지합니다.
    전략의 get_entries_exits() 메서드를 사용하여 벡터화된 백테스팅을 수행합니다.
    """

    def __init__(self, strategy, initial_capital: float = 10000.0,
                 position_size: float = 0.95, commission: float = 0.001,
                 slippage_pct: float = 0.0):
        """
        Args:
            strategy: get_entries_exits(df)를 구현한 전략 객체
            initial_capital: 초기 자본금 (USD)
            position_size: 거래당 자본 비율 (0-1)
            commission: 수수료 비율 (0.001 = 0.1%)
            slippage_pct: 슬리피지 비율 (0.001 = 0.1%)
        """
        if not _has_vbt:
            raise ImportError(
                "vectorbt 패키지가 필요합니다. 설치: pip install vectorbt"
            )
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.slippage_pct = slippage_pct
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

        result = self.strategy.get_entries_exits(df)

        # Detect if strategy returns 4-tuple (with short signals)
        short_entries = None
        short_exits = None
        if isinstance(result, tuple) and len(result) == 4:
            entries, exits, short_entries, short_exits = result
        else:
            entries, exits = result

        # 시그널이 전혀 없는 경우
        has_long = entries.any() or exits.any()
        has_short = short_entries is not None and (short_entries.any() or short_exits.any())
        if not has_long and not has_short:
            return self._no_trade_results(df)

        close = df['close']

        signal_kwargs = dict(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            size=self.position_size,
            size_type='percent',
            fees=self.commission,
            slippage=self.slippage_pct,
            freq='1D',
        )

        if short_entries is not None and short_exits is not None:
            signal_kwargs['short_entries'] = short_entries
            signal_kwargs['short_exits'] = short_exits

        pf = vbt.Portfolio.from_signals(**signal_kwargs)

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

        # trades 리스트를 레거시 형식으로 변환 (orders에서 BUY/SELL 추출)
        self.trades = self._extract_trades(pf, records)

        # equity curve를 레거시 Dict 형식으로 변환
        self.equity_curve = self._build_equity_curve(pf, df)

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
            'total_slippage_cost': 0.0,
            'start_date': df.index[0],
            'end_date': df.index[-1],
        }

    def _extract_trades(self, pf, trade_records: pd.DataFrame) -> list:
        """VBT 거래 레코드를 레거시 Backtester 형식의 trade list로 변환"""
        legacy_trades = []
        order_records = pf.orders.records_readable

        # orders를 BUY/SELL 쌍으로 변환
        for _, order in order_records.iterrows():
            trade = {
                'timestamp': order['Timestamp'],
                'type': 'BUY' if order['Side'] == 'Buy' else 'SELL',
                'price': float(order['Price']),
                'size': float(order['Size']),
                'commission': float(order['Fees']),
                'slippage_cost': 0.0,
            }
            legacy_trades.append(trade)

        # SELL 거래에 pnl, pnl_pct 추가 (trade_records에서 매칭)
        sell_idx = 0
        for t in legacy_trades:
            if t['type'] == 'SELL' and sell_idx < len(trade_records):
                rec = trade_records.iloc[sell_idx]
                t['pnl'] = float(rec['PnL'])
                t['pnl_pct'] = float(rec['Return'] * 100)
                sell_idx += 1

        return legacy_trades

    def _build_equity_curve(self, pf, df: pd.DataFrame) -> list:
        """VBT Portfolio에서 레거시 형식의 equity curve 생성"""
        equity_values = pf.value()
        close_prices = df['close']
        position_sizes = pf.asset_flow().cumsum()

        curve = []
        for ts in df.index:
            curve.append({
                'timestamp': ts,
                'equity': float(equity_values.loc[ts]),
                'price': float(close_prices.loc[ts]),
                'position': float(position_sizes.loc[ts]),
            })
        return curve

    def _no_trade_results(self, df: pd.DataFrame) -> Dict:
        """거래가 없을 때의 결과"""
        self.trades = []
        if len(df) > 0:
            self.equity_curve = [
                {
                    'timestamp': ts,
                    'equity': self.initial_capital,
                    'price': float(df.loc[ts, 'close']),
                    'position': 0.0,
                }
                for ts in df.index
            ]
        else:
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
            'total_slippage_cost': 0.0,
            'start_date': df.index[0] if len(df) > 0 else None,
            'end_date': df.index[-1] if len(df) > 0 else None,
        }

    def _empty_results(self, df: pd.DataFrame) -> Dict:
        """빈 DataFrame일 때의 결과"""
        self.trades = []
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
            'total_slippage_cost': 0.0,
            'start_date': None,
            'end_date': None,
        }
