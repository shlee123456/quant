"""
포트폴리오 자본 배분 모듈.

여러 종목에 자본을 배분하는 전략을 구현한다.
지원 방식: equal (균등), rank_weighted (순위 가중), score_weighted (점수 가중).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PortfolioAllocator:
    """포트폴리오 자본 배분기.

    Args:
        method: 배분 방식 ('equal', 'rank_weighted', 'score_weighted')
        max_symbols: 최대 투자 종목 수
    """

    VALID_METHODS = ('equal', 'rank_weighted', 'score_weighted')

    def __init__(self, method: str = 'equal', max_symbols: int = 5) -> None:
        if method not in self.VALID_METHODS:
            raise ValueError(f"지원하지 않는 배분 방식: {method}. 가능: {self.VALID_METHODS}")
        self.method = method
        self.max_symbols = max_symbols

    def allocate(
        self,
        total_capital: float,
        ranked_stocks: List[Dict[str, Any]],
        current_positions: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """종목별 배분 자본을 계산한다.

        Args:
            total_capital: 배분 가능한 총 자본금
            ranked_stocks: StockRanker.rank() 반환 형식의 리스트.
                           각 항목에 'symbol', 'total_score', 'rank' 키 필요.
            current_positions: 현재 보유 중인 포지션 {symbol: position_size}.
                               보유 중인 종목은 배분에서 제외.

        Returns:
            {symbol: allocated_capital} 딕셔너리
        """
        if not ranked_stocks or total_capital <= 0:
            return {}

        current_positions = current_positions or {}

        # 이미 포지션이 있는 종목 제외
        available = [
            s for s in ranked_stocks
            if current_positions.get(s['symbol'], 0) == 0
        ]

        # max_symbols 제한 적용
        available = available[:self.max_symbols]

        if not available:
            return {}

        if self.method == 'equal':
            return self._equal_allocation(total_capital, available)
        elif self.method == 'rank_weighted':
            return self._rank_weighted_allocation(total_capital, available)
        elif self.method == 'score_weighted':
            return self._score_weighted_allocation(total_capital, available)
        else:
            return self._equal_allocation(total_capital, available)

    def _equal_allocation(
        self, capital: float, stocks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """균등 배분: 모든 종목에 동일 금액."""
        per_symbol = capital / len(stocks)
        return {s['symbol']: per_symbol for s in stocks}

    def _rank_weighted_allocation(
        self, capital: float, stocks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """순위 가중 배분: 1등이 가장 많은 비중.

        가중치: N, N-1, ..., 1 (N = 종목 수)
        """
        n = len(stocks)
        weights = {s['symbol']: n - i for i, s in enumerate(stocks)}
        total_weight = sum(weights.values())

        return {
            symbol: capital * (w / total_weight)
            for symbol, w in weights.items()
        }

    def _score_weighted_allocation(
        self, capital: float, stocks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """점수 가중 배분: total_score에 비례.

        모든 점수가 0 이하이면 균등 배분으로 폴백.
        """
        scores = {s['symbol']: max(s.get('total_score', 0), 0) for s in stocks}
        total_score = sum(scores.values())

        if total_score <= 0:
            return self._equal_allocation(capital, stocks)

        return {
            symbol: capital * (score / total_score)
            for symbol, score in scores.items()
        }
