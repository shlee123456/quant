"""
PortfolioAllocator 테스트.

균등 배분, 순위 가중 배분, 점수 가중 배분, 최대 종목 수 제한,
기존 포지션 제외 동작을 검증한다.
"""

import unittest
from trading_bot.portfolio_allocator import PortfolioAllocator


def _make_ranked(symbols_scores):
    """(symbol, score) 리스트로 ranked_stocks 생성."""
    return [
        {'symbol': sym, 'total_score': score, 'rank': i + 1}
        for i, (sym, score) in enumerate(symbols_scores)
    ]


class TestEqualAllocation(unittest.TestCase):

    def test_equal_allocation(self):
        """균등 배분: 3종목에 10000 → 각 3333.33."""
        allocator = PortfolioAllocator(method='equal', max_symbols=5)
        ranked = _make_ranked([('AAPL', 80), ('MSFT', 60), ('GOOGL', 40)])

        result = allocator.allocate(10000.0, ranked)

        self.assertEqual(len(result), 3)
        for symbol, capital in result.items():
            self.assertAlmostEqual(capital, 10000.0 / 3, places=2)

    def test_equal_allocation_total(self):
        """균등 배분 합계가 총 자본과 일치."""
        allocator = PortfolioAllocator(method='equal', max_symbols=5)
        ranked = _make_ranked([('A', 50), ('B', 50)])
        result = allocator.allocate(10000.0, ranked)
        self.assertAlmostEqual(sum(result.values()), 10000.0, places=2)


class TestRankWeightedAllocation(unittest.TestCase):

    def test_rank_weighted_allocation(self):
        """순위 가중 배분: 1등이 가장 많은 비중."""
        allocator = PortfolioAllocator(method='rank_weighted', max_symbols=5)
        ranked = _make_ranked([('AAPL', 80), ('MSFT', 60), ('GOOGL', 40)])

        result = allocator.allocate(10000.0, ranked)

        self.assertGreater(result['AAPL'], result['MSFT'])
        self.assertGreater(result['MSFT'], result['GOOGL'])
        self.assertAlmostEqual(sum(result.values()), 10000.0, places=2)

    def test_rank_weighted_two_stocks(self):
        """2종목 순위 가중: 1등 2/3, 2등 1/3."""
        allocator = PortfolioAllocator(method='rank_weighted', max_symbols=5)
        ranked = _make_ranked([('A', 90), ('B', 50)])

        result = allocator.allocate(9000.0, ranked)

        # weights: A=2, B=1, total=3 → A=6000, B=3000
        self.assertAlmostEqual(result['A'], 6000.0, places=2)
        self.assertAlmostEqual(result['B'], 3000.0, places=2)


class TestScoreWeightedAllocation(unittest.TestCase):

    def test_score_weighted_allocation(self):
        """점수 가중 배분: total_score에 비례."""
        allocator = PortfolioAllocator(method='score_weighted', max_symbols=5)
        ranked = _make_ranked([('AAPL', 80), ('MSFT', 20)])

        result = allocator.allocate(10000.0, ranked)

        # 80/(80+20) = 0.8 → AAPL=8000, MSFT=2000
        self.assertAlmostEqual(result['AAPL'], 8000.0, places=2)
        self.assertAlmostEqual(result['MSFT'], 2000.0, places=2)

    def test_score_weighted_zero_scores(self):
        """모든 점수가 0이면 균등 배분 폴백."""
        allocator = PortfolioAllocator(method='score_weighted', max_symbols=5)
        ranked = _make_ranked([('A', 0), ('B', 0)])

        result = allocator.allocate(10000.0, ranked)

        self.assertAlmostEqual(result['A'], 5000.0, places=2)
        self.assertAlmostEqual(result['B'], 5000.0, places=2)


class TestMaxSymbolsLimit(unittest.TestCase):

    def test_max_symbols_limit(self):
        """max_symbols=2일 때 상위 2종목만 배분."""
        allocator = PortfolioAllocator(method='equal', max_symbols=2)
        ranked = _make_ranked([('A', 90), ('B', 80), ('C', 70), ('D', 60)])

        result = allocator.allocate(10000.0, ranked)

        self.assertEqual(len(result), 2)
        self.assertIn('A', result)
        self.assertIn('B', result)
        self.assertNotIn('C', result)

    def test_fewer_stocks_than_max(self):
        """종목 수가 max_symbols보다 적으면 전체 배분."""
        allocator = PortfolioAllocator(method='equal', max_symbols=10)
        ranked = _make_ranked([('A', 90), ('B', 80)])

        result = allocator.allocate(10000.0, ranked)
        self.assertEqual(len(result), 2)


class TestWithExistingPositions(unittest.TestCase):

    def test_with_existing_positions(self):
        """이미 포지션이 있는 종목은 배분에서 제외."""
        allocator = PortfolioAllocator(method='equal', max_symbols=5)
        ranked = _make_ranked([('AAPL', 80), ('MSFT', 60), ('GOOGL', 40)])

        result = allocator.allocate(
            10000.0, ranked,
            current_positions={'AAPL': 10.0}  # AAPL 이미 보유
        )

        self.assertNotIn('AAPL', result)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(sum(result.values()), 10000.0, places=2)

    def test_all_positions_held(self):
        """모든 종목이 이미 보유 중이면 빈 딕셔너리."""
        allocator = PortfolioAllocator(method='equal', max_symbols=5)
        ranked = _make_ranked([('AAPL', 80), ('MSFT', 60)])

        result = allocator.allocate(
            10000.0, ranked,
            current_positions={'AAPL': 10.0, 'MSFT': 5.0}
        )
        self.assertEqual(len(result), 0)


class TestAllocatorEdgeCases(unittest.TestCase):

    def test_empty_ranked(self):
        """빈 종목 리스트 → 빈 결과."""
        allocator = PortfolioAllocator(method='equal')
        result = allocator.allocate(10000.0, [])
        self.assertEqual(len(result), 0)

    def test_zero_capital(self):
        """자본금 0 → 빈 결과."""
        allocator = PortfolioAllocator(method='equal')
        ranked = _make_ranked([('AAPL', 80)])
        result = allocator.allocate(0.0, ranked)
        self.assertEqual(len(result), 0)

    def test_invalid_method(self):
        """지원하지 않는 방식 → ValueError."""
        with self.assertRaises(ValueError):
            PortfolioAllocator(method='invalid')


if __name__ == '__main__':
    unittest.main()
