#!/usr/bin/env python3
"""5-Layer Intelligence 가중치 최적화 실행 스크립트.

백테스트 -> 최적 가중치 탐색 -> 결과 출력.
자동 적용하지 않음 -- 결과를 검토 후 수동 적용.

Usage:
    python scripts/optimize_intelligence.py
    python scripts/optimize_intelligence.py --years 3 --forward-days 10
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="5-Layer Intelligence 가중치 최적화")
    parser.add_argument('--years', type=int, default=2, help='백테스트 기간 (기본: 2년)')
    parser.add_argument('--forward-days', type=int, default=5, help='시그널 후 측정 기간 (기본: 5일)')
    parser.add_argument('--step-days', type=int, default=5, help='분석 간격 (기본: 5일 = 주 1회)')
    parser.add_argument('--splits', type=int, default=5, help='Walk-Forward 분할 수 (기본: 5)')
    args = parser.parse_args()

    from trading_bot.intelligence_backtest import IntelligenceBacktester
    from trading_bot.weight_optimizer import WeightOptimizer

    # Step 1: 백테스트
    logger.info(f"Step 1: 백테스트 ({args.years}년, {args.forward_days}일 forward)")
    bt = IntelligenceBacktester(
        lookback_years=args.years,
        forward_days=args.forward_days,
        step_days=args.step_days,
    )
    bt_result = bt.run()

    print("\n" + bt_result.summary)

    if bt_result.total_days < 50:
        logger.error("백테스트 데이터 부족. 종료.")
        sys.exit(1)

    # Step 2: 가중치 최적화
    logger.info(f"\nStep 2: 가중치 최적화 ({args.splits}-fold Walk-Forward)")
    optimizer = WeightOptimizer(n_splits=args.splits)
    opt_result = optimizer.optimize(bt_result)

    print("\n" + "=" * 50)
    print("가중치 최적화 결과")
    print("=" * 50)
    print(opt_result.recommendation)
    print("=" * 50)

    if opt_result.is_improvement:
        print("\n적용 방법:")
        print("trading_bot/market_intelligence/__init__.py의 LAYER_WEIGHTS를 아래로 변경:")
        print(f"LAYER_WEIGHTS = {opt_result.optimal_weights}")

    sys.exit(0)


if __name__ == '__main__':
    main()
