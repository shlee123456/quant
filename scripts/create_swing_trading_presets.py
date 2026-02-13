"""
스윙트레이딩 전략 프리셋 생성 스크립트

스윙트레이딩 특성:
- 긴 기간 지표 (일봉/주봉 사용)
- 큰 손익 범위 (손절 5%, 익절 10%)
- 낮은 포지션 크기 (종목당 20% - 데이터 수집 목적)
- 장기 보유 전략

생성 프리셋:
1. 스윙트레이딩 - RSI 보수적
2. 스윙트레이딩 - MACD 추세 추종
3. 스윙트레이딩 - RSI+MACD 복합

Usage:
    python scripts/create_swing_trading_presets.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy_presets import StrategyPresetManager


def create_swing_trading_presets():
    """스윙트레이딩 전략 프리셋 생성"""
    manager = StrategyPresetManager()

    # 공통 설정
    common_config = {
        'initial_capital': 10000.0,
        'position_size': 0.2,  # 종목당 20% (5종목 동시 진입 가능)
        'symbols': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
        'stop_loss_pct': 0.05,  # 5% 손절
        'take_profit_pct': 0.10,  # 10% 익절
        'enable_stop_loss': True,
        'enable_take_profit': True
    }

    # 1. RSI 보수적 전략 (스윙트레이딩)
    print("=" * 60)
    print("1. 스윙트레이딩 - RSI 보수적 전략 생성 중...")
    print("=" * 60)

    rsi_params = {
        'period': 21,  # 긴 기간 (기본 14 → 21)
        'overbought': 75,  # 과매수 레벨 상향 (신호 빈도 감소)
        'oversold': 25  # 과매도 레벨 하향 (신호 빈도 감소)
    }

    success = manager.save_preset(
        name="스윙트레이딩 - RSI 보수적",
        description=(
            "스윙트레이딩에 최적화된 보수적 RSI 전략. "
            "긴 기간(21일) 사용, 넓은 과매수/과매도 레벨(75/25)로 신호 빈도 감소. "
            "일봉 데이터 사용 권장. 큰 손익 범위(5%/10%)로 장기 보유."
        ),
        strategy="RSI Strategy",
        strategy_params=rsi_params,
        **common_config
    )

    if success:
        print("✓ RSI 보수적 전략 프리셋 저장 완료")
        print(f"  - RSI 기간: {rsi_params['period']}일")
        print(f"  - 과매수: {rsi_params['overbought']}, 과매도: {rsi_params['oversold']}")
        print(f"  - 손절: {common_config['stop_loss_pct']*100}%, 익절: {common_config['take_profit_pct']*100}%")
    else:
        print("✗ RSI 보수적 전략 프리셋 저장 실패")

    # 2. MACD 추세 추종 전략 (스윙트레이딩)
    print("\n" + "=" * 60)
    print("2. 스윙트레이딩 - MACD 추세 추종 전략 생성 중...")
    print("=" * 60)

    macd_params = {
        'fast_period': 19,  # 긴 기간 (기본 12 → 19)
        'slow_period': 39,  # 긴 기간 (기본 26 → 39)
        'signal_period': 9  # 시그널 라인 (기본 유지)
    }

    success = manager.save_preset(
        name="스윙트레이딩 - MACD 추세 추종",
        description=(
            "스윙트레이딩에 최적화된 MACD 추세 추종 전략. "
            "긴 기간(19/39/9) 사용으로 노이즈 감소, 강한 추세 포착. "
            "일봉/주봉 데이터 사용 권장. 큰 손익 범위(5%/10%)로 장기 보유."
        ),
        strategy="MACD Strategy",
        strategy_params=macd_params,
        **common_config
    )

    if success:
        print("✓ MACD 추세 추종 전략 프리셋 저장 완료")
        print(f"  - MACD 기간: Fast={macd_params['fast_period']}, Slow={macd_params['slow_period']}, Signal={macd_params['signal_period']}")
        print(f"  - 손절: {common_config['stop_loss_pct']*100}%, 익절: {common_config['take_profit_pct']*100}%")
    else:
        print("✗ MACD 추세 추종 전략 프리셋 저장 실패")

    # 3. RSI+MACD 복합 전략 (스윙트레이딩)
    print("\n" + "=" * 60)
    print("3. 스윙트레이딩 - RSI+MACD 복합 전략 생성 중...")
    print("=" * 60)

    combo_params = {
        'rsi_period': 21,
        'rsi_overbought': 75,
        'rsi_oversold': 25,
        'macd_fast': 19,
        'macd_slow': 39,
        'macd_signal': 9
    }

    success = manager.save_preset(
        name="스윙트레이딩 - RSI+MACD 복합",
        description=(
            "스윙트레이딩에 최적화된 RSI+MACD 복합 전략. "
            "RSI(21, 75/25)와 MACD(19/39/9)를 결합하여 고신뢰도 신호 생성. "
            "일봉/주봉 데이터 사용 권장. 큰 손익 범위(5%/10%)로 장기 보유. "
            "데이터 수집 목적으로 최적화됨."
        ),
        strategy="RSI+MACD Combo Strategy",
        strategy_params=combo_params,
        **common_config
    )

    if success:
        print("✓ RSI+MACD 복합 전략 프리셋 저장 완료")
        print(f"  - RSI: {combo_params['rsi_period']}일, {combo_params['rsi_overbought']}/{combo_params['rsi_oversold']}")
        print(f"  - MACD: {combo_params['macd_fast']}/{combo_params['macd_slow']}/{combo_params['macd_signal']}")
        print(f"  - 손절: {common_config['stop_loss_pct']*100}%, 익절: {common_config['take_profit_pct']*100}%")
    else:
        print("✗ RSI+MACD 복합 전략 프리셋 저장 실패")

    # 4. 저장된 프리셋 확인
    print("\n" + "=" * 60)
    print("저장된 스윙트레이딩 프리셋 목록:")
    print("=" * 60)

    all_presets = manager.list_presets()
    swing_presets = [p for p in all_presets if '스윙트레이딩' in p['name']]

    for preset in swing_presets:
        print(f"  - {preset['name']}")
        print(f"    전략: {preset['strategy']}")
        print(f"    종목: {', '.join(preset['symbols'])}")
        print(f"    포지션 크기: {preset['position_size']:.0%}")
        print(f"    손익: 손절 {preset['stop_loss_pct']*100}% / 익절 {preset['take_profit_pct']*100}%")
        print()

    print("=" * 60)
    print("✓ 스윙트레이딩 프리셋 생성 완료!")
    print("=" * 60)
    print("\n사용 방법:")
    print("1. Dashboard → Paper Trading 탭")
    print("2. 'Select Preset' 드롭다운에서 '스윙트레이딩' 프리셋 선택")
    print("3. '불러오기' 버튼 클릭")
    print("4. 설정 확인 후 'Start Paper Trading' 실행")
    print("\n권장 설정:")
    print("- Timeframe: 1d (일봉) 또는 1w (주봉)")
    print("- Interval: 3600초 (1시간) 이상 (빈번한 체크 불필요)")


if __name__ == '__main__':
    create_swing_trading_presets()
