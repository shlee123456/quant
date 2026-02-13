"""
미국 시가총액 상위 10개 기업 최적 전략 프리셋 생성

대상 종목 (2026년 시가총액 기준):
1. AAPL  - Apple (NASDAQ)
2. MSFT  - Microsoft (NASDAQ)
3. NVDA  - NVIDIA (NASDAQ)
4. AMZN  - Amazon (NASDAQ)
5. GOOGL - Alphabet (NASDAQ)
6. META  - Meta Platforms (NASDAQ)
7. TSLA  - Tesla (NASDAQ)
8. AVGO  - Broadcom (NASDAQ)
9. LLY   - Eli Lilly (NYSE)
10. WMT  - Walmart (NYSE)

전략 설계 원칙:
- 10종목 분산투자: position_size=0.1 (종목당 10%)
- 대형주 특성 반영: 낮은 변동성, 안정적 추세
- 다전략 비교: RSI, MACD, Bollinger Bands 각각 최적화
- 실전 적용 가능한 파라미터 (과최적화 방지)

생성 프리셋:
1. Top10 US - RSI 평균회귀
2. Top10 US - MACD 추세추종
3. Top10 US - 볼린저밴드 변동성
4. Top10 US - 듀얼 세션 (A조 5종목 + B조 5종목)

Usage:
    python scripts/create_top10_us_presets.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy_presets import StrategyPresetManager


# Top 10 US Market Cap 종목
TOP10_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT']

# 듀얼 세션 분할 (A조: 테크 중심, B조: 다각화)
SESSION_A_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL']  # 빅테크
SESSION_B_SYMBOLS = ['META', 'TSLA', 'AVGO', 'LLY', 'WMT']     # 다각화


def create_top10_presets():
    """미국 시가총액 상위 10개 기업 전략 프리셋 생성"""
    manager = StrategyPresetManager()

    # 공통 설정 (10종목)
    common_10 = {
        'initial_capital': 10000.0,
        'position_size': 0.1,       # 종목당 10% (10종목 × 10% = 100%)
        'symbols': TOP10_SYMBOLS,
        'stop_loss_pct': 0.05,      # 5% 손절 (대형주 기준)
        'take_profit_pct': 0.08,    # 8% 익절
        'enable_stop_loss': True,
        'enable_take_profit': True,
    }

    # 공통 설정 (5종목 세션)
    common_5 = {
        'initial_capital': 5000.0,
        'position_size': 0.2,       # 종목당 20% (5종목 × 20% = 100%)
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.08,
        'enable_stop_loss': True,
        'enable_take_profit': True,
    }

    # ============================================================
    # 1. RSI 평균회귀 전략
    # ============================================================
    print("=" * 60)
    print("1. Top10 US - RSI 평균회귀 전략 생성 중...")
    print("=" * 60)

    # 대형주 특성: 변동성이 낮아 RSI 극단값에 덜 도달
    # → 과매수/과매도 레벨을 좁혀서 신호 빈도 확보
    rsi_params = {
        'period': 14,           # 표준 RSI 기간
        'overbought': 65,       # 과매수 하향 (70→65) - 대형주 특성 반영
        'oversold': 35,         # 과매도 상향 (30→35) - 신호 빈도 확보
    }

    success = manager.save_preset(
        name="Top10 US - RSI 평균회귀",
        description=(
            "미국 시총 상위 10개 기업 RSI 평균회귀 전략. "
            "대형주 낮은 변동성 반영하여 과매수/과매도 레벨 조정(65/35). "
            "10종목 분산투자(종목당 10%). 손절 5%, 익절 8%."
        ),
        strategy="RSI Strategy",
        strategy_params=rsi_params,
        **common_10
    )

    if success:
        print(f"  RSI 기간: {rsi_params['period']}일")
        print(f"  과매수/과매도: {rsi_params['overbought']}/{rsi_params['oversold']}")
        print(f"  종목: {', '.join(TOP10_SYMBOLS)}")
        print(f"  포지션: 종목당 10%")
        print("  -> 저장 완료")
    else:
        print("  -> 저장 실패")

    # ============================================================
    # 2. MACD 추세추종 전략
    # ============================================================
    print("\n" + "=" * 60)
    print("2. Top10 US - MACD 추세추종 전략 생성 중...")
    print("=" * 60)

    # 대형주: 추세가 형성되면 오래 지속
    # → 표준 MACD 파라미터가 적합
    macd_params = {
        'fast_period': 12,      # 표준
        'slow_period': 26,      # 표준
        'signal_period': 9,     # 표준
    }

    success = manager.save_preset(
        name="Top10 US - MACD 추세추종",
        description=(
            "미국 시총 상위 10개 기업 MACD 추세추종 전략. "
            "표준 MACD(12/26/9) 사용. 대형주의 안정적 추세 포착에 적합. "
            "10종목 분산투자(종목당 10%). 손절 5%, 익절 8%."
        ),
        strategy="MACD Strategy",
        strategy_params=macd_params,
        **common_10
    )

    if success:
        print(f"  MACD: Fast={macd_params['fast_period']}, Slow={macd_params['slow_period']}, Signal={macd_params['signal_period']}")
        print(f"  종목: {', '.join(TOP10_SYMBOLS)}")
        print(f"  포지션: 종목당 10%")
        print("  -> 저장 완료")
    else:
        print("  -> 저장 실패")

    # ============================================================
    # 3. 볼린저밴드 변동성 전략
    # ============================================================
    print("\n" + "=" * 60)
    print("3. Top10 US - 볼린저밴드 변동성 전략 생성 중...")
    print("=" * 60)

    # 대형주: 볼린저밴드 이탈 시 반등 확률 높음
    # → 1.5 표준편차로 신호 빈도 확보 (기본 2.0은 너무 넓음)
    bb_params = {
        'period': 20,           # 표준 기간
        'std_dev': 1.5,         # 표준편차 축소 (2.0→1.5) - 신호 빈도 확보
    }

    success = manager.save_preset(
        name="Top10 US - 볼린저밴드 변동성",
        description=(
            "미국 시총 상위 10개 기업 볼린저밴드 전략. "
            "20일 기간, 1.5 표준편차(기본 2.0에서 축소)로 신호 빈도 확보. "
            "대형주 볼린저밴드 이탈 시 반등 특성 활용. "
            "10종목 분산투자(종목당 10%). 손절 5%, 익절 8%."
        ),
        strategy="Bollinger Bands",
        strategy_params=bb_params,
        **common_10
    )

    if success:
        print(f"  기간: {bb_params['period']}일, 표준편차: {bb_params['std_dev']}")
        print(f"  종목: {', '.join(TOP10_SYMBOLS)}")
        print(f"  포지션: 종목당 10%")
        print("  -> 저장 완료")
    else:
        print("  -> 저장 실패")

    # ============================================================
    # 4. 듀얼 세션 - A조 (빅테크 5종목)
    # ============================================================
    print("\n" + "=" * 60)
    print("4. Top10 US - 듀얼 A조 (빅테크) 생성 중...")
    print("=" * 60)

    success = manager.save_preset(
        name="Top10 US - 듀얼 A조 빅테크",
        description=(
            "Top 10 듀얼 세션 A조: AAPL, MSFT, NVDA, AMZN, GOOGL. "
            "빅테크 5종목에 MACD 추세추종. "
            "B조와 함께 실행하여 10종목 분산투자 완성. "
            "scheduler --presets 'Top10 US - 듀얼 A조 빅테크' 'Top10 US - 듀얼 B조 다각화'"
        ),
        strategy="MACD Strategy",
        strategy_params={'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
        symbols=SESSION_A_SYMBOLS,
        **common_5
    )

    if success:
        print(f"  종목: {', '.join(SESSION_A_SYMBOLS)}")
        print(f"  자본: $5,000 (종목당 20%)")
        print("  -> 저장 완료")
    else:
        print("  -> 저장 실패")

    # ============================================================
    # 5. 듀얼 세션 - B조 (다각화 5종목)
    # ============================================================
    print("\n" + "=" * 60)
    print("5. Top10 US - 듀얼 B조 (다각화) 생성 중...")
    print("=" * 60)

    success = manager.save_preset(
        name="Top10 US - 듀얼 B조 다각화",
        description=(
            "Top 10 듀얼 세션 B조: META, TSLA, AVGO, LLY, WMT. "
            "테크+헬스케어+유통 다각화. RSI 평균회귀. "
            "A조와 함께 실행하여 10종목 분산투자 완성. "
            "scheduler --presets 'Top10 US - 듀얼 A조 빅테크' 'Top10 US - 듀얼 B조 다각화'"
        ),
        strategy="RSI Strategy",
        strategy_params={'period': 14, 'overbought': 65, 'oversold': 35},
        symbols=SESSION_B_SYMBOLS,
        **common_5
    )

    if success:
        print(f"  종목: {', '.join(SESSION_B_SYMBOLS)}")
        print(f"  자본: $5,000 (종목당 20%)")
        print("  -> 저장 완료")
    else:
        print("  -> 저장 실패")

    # ============================================================
    # 결과 요약
    # ============================================================
    print("\n" + "=" * 60)
    print("생성된 Top 10 프리셋 목록:")
    print("=" * 60)

    all_presets = manager.list_presets()
    top10_presets = [p for p in all_presets if 'Top10' in p['name']]

    for preset in top10_presets:
        print(f"\n  [{preset['strategy']}] {preset['name']}")
        print(f"    종목: {', '.join(preset['symbols'])}")
        print(f"    포지션: {preset['position_size']:.0%}/종목")
        print(f"    자본: ${preset['initial_capital']:,.0f}")
        print(f"    손절/익절: {preset['stop_loss_pct']*100:.0f}%/{preset['take_profit_pct']*100:.0f}%")

    print("\n" + "=" * 60)
    print("프리셋 생성 완료!")
    print("=" * 60)

    print("\n사용 방법:")
    print("-" * 40)
    print("# 단일 세션 (10종목, 전략 1개):")
    print('  python scheduler.py --preset "Top10 US - RSI 평균회귀"')
    print('  python scheduler.py --preset "Top10 US - MACD 추세추종"')
    print('  python scheduler.py --preset "Top10 US - 볼린저밴드 변동성"')
    print()
    print("# 듀얼 세션 (5종목 x 2, 서로 다른 전략):")
    print('  python scheduler.py --presets "Top10 US - 듀얼 A조 빅테크" "Top10 US - 듀얼 B조 다각화"')
    print()
    print("# 전략 비교 (3개 세션 동시 실행):")
    print('  python scheduler.py --presets "Top10 US - RSI 평균회귀" "Top10 US - MACD 추세추종" "Top10 US - 볼린저밴드 변동성"')


if __name__ == '__main__':
    create_top10_presets()
