"""
Custom Combo Strategy Builder

사용자가 여러 전략을 조합하여 커스텀 전략을 만들 수 있는 기능을 제공합니다.
"""
from typing import Dict, List, Tuple, Any
import pandas as pd
import numpy as np
from trading_bot.logging_config import get_strategy_logger
from trading_bot.strategies.base_strategy import BaseStrategy

logger = get_strategy_logger()


class CustomComboStrategy(BaseStrategy):
    """
    여러 전략을 조합한 커스텀 전략

    Parameters:
        strategies (List[Any]): 조합할 전략 리스트
        strategy_names (List[str]): 각 전략의 이름
        combination_logic (str): 조합 로직 ('AND', 'OR', 'MAJORITY', 'WEIGHTED')
        weights (List[float]): 가중치 (WEIGHTED 모드일 때 사용)
        threshold (float): 가중치 합 임계값 (WEIGHTED 모드, 기본 0.5)
    """

    def __init__(
        self,
        strategies: List[Any],
        strategy_names: List[str],
        combination_logic: str = 'MAJORITY',
        weights: List[float] = None,
        threshold: float = 0.5
    ):
        if not strategies:
            raise ValueError("최소 1개 이상의 전략이 필요합니다")

        self.strategies = strategies
        self.strategy_names = strategy_names
        self.combination_logic = combination_logic.upper()
        self.weights = weights or [1.0 / len(strategies)] * len(strategies)
        self.threshold = threshold

        # 가중치 검증
        if len(self.weights) != len(self.strategies):
            raise ValueError("전략 개수와 가중치 개수가 일치해야 합니다")

        # 가중치 정규화
        total_weight = sum(self.weights)
        self.weights = [w / total_weight for w in self.weights]

        # 전략 이름 생성
        logic_short = {
            'AND': 'ALL',
            'OR': 'ANY',
            'MAJORITY': 'MAJ',
            'WEIGHTED': 'WGT'
        }
        strategy_short = '+'.join([name.split()[0][:3].upper() for name in strategy_names])
        super().__init__(name=f"Custom_{logic_short.get(self.combination_logic, 'CMB')}_{strategy_short}")

        logger.debug(
            f"Initialized {self.name} - "
            f"Strategies: {strategy_names}, "
            f"Logic: {self.combination_logic}, "
            f"Weights: {self.weights}"
        )

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        모든 전략의 지표를 계산하고 신호를 조합

        Args:
            df: OHLCV 데이터

        Returns:
            DataFrame with combined signals
        """
        if df.empty:
            return df.copy()

        self.validate_dataframe(df)

        data = df.copy()

        # 각 전략의 신호 계산
        strategy_signals = []
        for i, strategy in enumerate(self.strategies):
            strategy_data = strategy.calculate_indicators(df)
            strategy_signals.append(strategy_data['signal'])

            # 각 전략의 지표를 컬럼으로 추가 (디버깅용)
            prefix = f"strat{i+1}_"
            for col in strategy_data.columns:
                if col not in ['open', 'high', 'low', 'close', 'volume']:
                    data[f"{prefix}{col}"] = strategy_data[col]

        # 신호 조합
        data['signal'] = self._combine_signals(strategy_signals)

        # 포지션 계산
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)

        return data

    def _combine_signals(self, signals: List[pd.Series]) -> pd.Series:
        """
        여러 전략의 신호를 조합 로직에 따라 결합

        Args:
            signals: 각 전략의 신호 시리즈 리스트

        Returns:
            Combined signal series
        """
        # 신호를 DataFrame으로 변환
        signals_df = pd.DataFrame({f's{i}': s for i, s in enumerate(signals)})

        if self.combination_logic == 'AND':
            # 모든 전략이 동일한 신호를 보낼 때만 신호 발생
            combined = pd.Series(0, index=signals_df.index)

            # 모든 전략이 1 (BUY)
            all_buy = (signals_df == 1).all(axis=1)
            combined[all_buy] = 1

            # 모든 전략이 -1 (SELL)
            all_sell = (signals_df == -1).all(axis=1)
            combined[all_sell] = -1

        elif self.combination_logic == 'OR':
            # 하나라도 신호를 보내면 신호 발생
            combined = pd.Series(0, index=signals_df.index)

            # 하나라도 BUY
            any_buy = (signals_df == 1).any(axis=1)
            combined[any_buy] = 1

            # 하나라도 SELL (BUY보다 우선순위 낮음)
            any_sell = (signals_df == -1).any(axis=1) & ~any_buy
            combined[any_sell] = -1

        elif self.combination_logic == 'MAJORITY':
            # 과반수 이상이 같은 신호를 보낼 때 신호 발생
            combined = pd.Series(0, index=signals_df.index)

            majority_threshold = len(signals) / 2

            # BUY 신호 개수
            buy_count = (signals_df == 1).sum(axis=1)
            combined[buy_count > majority_threshold] = 1

            # SELL 신호 개수
            sell_count = (signals_df == -1).sum(axis=1)
            combined[sell_count > majority_threshold] = -1

        elif self.combination_logic == 'WEIGHTED':
            # 가중치 합으로 신호 결정
            combined = pd.Series(0, index=signals_df.index)

            # 각 행마다 가중치 합 계산
            for idx in signals_df.index:
                weighted_sum = sum(
                    signals_df.loc[idx, f's{i}'] * self.weights[i]
                    for i in range(len(signals))
                )

                if weighted_sum > self.threshold:
                    combined[idx] = 1
                elif weighted_sum < -self.threshold:
                    combined[idx] = -1

        else:
            raise ValueError(f"Unknown combination logic: {self.combination_logic}")

        return combined

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """
        현재 시그널 반환

        Returns:
            (signal, info_dict)
        """
        data = self.calculate_indicators(df)

        if data.empty:
            return 0, {}

        last_row = data.iloc[-1]

        # 각 전략의 개별 신호 수집
        individual_signals = {}
        for i, name in enumerate(self.strategy_names):
            individual_signals[name] = int(last_row[f'strat{i+1}_signal'])

        info = {
            'timestamp': last_row.name,
            'close': last_row['close'],
            'signal': int(last_row['signal']),
            'position': int(last_row['position']),
            'combination_logic': self.combination_logic,
            'individual_signals': individual_signals,
            'weights': dict(zip(self.strategy_names, self.weights))
        }

        return int(last_row['signal']), info

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        모든 시그널 이벤트 반환

        Returns:
            List of signal dictionaries
        """
        data = self.calculate_indicators(df)
        signals_df = data[data['signal'] != 0].copy()

        signals = []
        for idx, row in signals_df.iterrows():
            # 각 전략의 개별 신호
            individual_signals = {}
            for i, name in enumerate(self.strategy_names):
                individual_signals[name] = int(row[f'strat{i+1}_signal'])

            signals.append({
                'timestamp': idx,
                'signal': 'BUY' if row['signal'] == 1 else 'SELL',
                'price': row['close'],
                'individual_signals': individual_signals
            })

        return signals

    def get_entries_exits(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        VBT 호환 진입/청산 Boolean Series 반환

        각 하위 전략의 entries/exits를 조합 로직에 따라 결합합니다.
        """
        if df.empty:
            return pd.Series(dtype=bool), pd.Series(dtype=bool)

        self.validate_dataframe(df)

        all_entries = []
        all_exits = []
        for strategy in self.strategies:
            e, x = strategy.get_entries_exits(df)
            all_entries.append(e)
            all_exits.append(x)

        entries_df = pd.DataFrame({f's{i}': s for i, s in enumerate(all_entries)})
        exits_df = pd.DataFrame({f's{i}': s for i, s in enumerate(all_exits)})

        if self.combination_logic == 'AND':
            entries = entries_df.all(axis=1)
            exits = exits_df.all(axis=1)
        elif self.combination_logic == 'OR':
            entries = entries_df.any(axis=1)
            exits = exits_df.any(axis=1)
        elif self.combination_logic == 'MAJORITY':
            majority = len(self.strategies) / 2
            entries = entries_df.sum(axis=1) > majority
            exits = exits_df.sum(axis=1) > majority
        elif self.combination_logic == 'WEIGHTED':
            w = pd.Series(self.weights)
            entry_score = entries_df.astype(float).multiply(w.values).sum(axis=1)
            exit_score = exits_df.astype(float).multiply(w.values).sum(axis=1)
            entries = entry_score > self.threshold
            exits = exit_score > self.threshold
        else:
            raise ValueError(f"Unknown combination logic: {self.combination_logic}")

        # Prevent overlap
        overlap = entries & exits
        entries = entries & ~overlap
        exits = exits & ~overlap

        return entries.astype(bool), exits.astype(bool)

    def get_params(self) -> Dict:
        return {
            'combination_logic': self.combination_logic,
            'strategy_names': self.strategy_names,
            'weights': self.weights,
            'threshold': self.threshold,
        }

    def get_param_info(self) -> Dict:
        return {
            'combination_logic': '조합 로직 (AND, OR, MAJORITY, WEIGHTED)',
            'strategy_names': '조합할 전략 이름 리스트',
            'weights': '가중치 리스트 (WEIGHTED 모드)',
            'threshold': '가중치 합 임계값 (WEIGHTED 모드)',
        }

    def __str__(self) -> str:
        return (
            f"Custom Combo Strategy "
            f"(Logic: {self.combination_logic}, "
            f"Strategies: {', '.join(self.strategy_names)})"
        )
