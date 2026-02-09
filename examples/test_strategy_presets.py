"""
전략 프리셋 관리 기능 테스트

목적: StrategyPresetManager의 저장/불러오기/삭제 기능 검증

실행: python examples/test_strategy_presets.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy_presets import StrategyPresetManager


def test_save_and_load_preset():
    """프리셋 저장 및 불러오기 테스트"""
    print("=" * 60)
    print("TEST 1: 프리셋 저장 및 불러오기")
    print("=" * 60)

    manager = StrategyPresetManager(presets_file="data/test_presets.json")

    # 프리셋 저장
    print("\n1. 프리셋 저장 중...")
    success = manager.save_preset(
        name="보수적 RSI 전략",
        strategy="RSI Strategy",
        strategy_params={"period": 14, "overbought": 70, "oversold": 30},
        initial_capital=10000.0,
        position_size=0.3,
        symbols=["AAPL", "MSFT"],
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
        enable_stop_loss=True,
        enable_take_profit=True,
        description="안정적인 수익을 추구하는 보수적 전략"
    )

    if success:
        print("✅ 프리셋 저장 성공!")
    else:
        print("❌ 프리셋 저장 실패")
        return

    # 프리셋 불러오기
    print("\n2. 프리셋 불러오기 중...")
    preset = manager.load_preset("보수적 RSI 전략")

    if preset:
        print("✅ 프리셋 불러오기 성공!")
        print(f"   전략: {preset['strategy']}")
        print(f"   종목: {preset['symbols']}")
        print(f"   초기 자본: ${preset['initial_capital']:,.2f}")
        print(f"   포지션 크기: {preset['position_size']:.0%}")
        print(f"   손절매: {preset['stop_loss_pct']:.0%}")
        print(f"   익절매: {preset['take_profit_pct']:.0%}")
        print(f"   파라미터: {preset['strategy_params']}")
        print(f"   설명: {preset['description']}")
    else:
        print("❌ 프리셋 불러오기 실패")


def test_list_presets():
    """프리셋 목록 조회 테스트"""
    print("\n\n" + "=" * 60)
    print("TEST 2: 프리셋 목록 조회")
    print("=" * 60)

    manager = StrategyPresetManager(presets_file="data/test_presets.json")

    # 여러 개의 프리셋 저장
    presets = [
        {
            "name": "공격적 RSI 전략",
            "strategy": "RSI Strategy",
            "strategy_params": {"period": 10, "overbought": 80, "oversold": 20},
            "initial_capital": 50000.0,
            "position_size": 0.5,
            "symbols": ["TSLA", "NVDA"],
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
            "description": "높은 수익을 추구하는 공격적 전략"
        },
        {
            "name": "MACD 전략",
            "strategy": "MACD Strategy",
            "strategy_params": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            "initial_capital": 20000.0,
            "position_size": 0.4,
            "symbols": ["GOOGL", "AMZN"],
            "stop_loss_pct": 0.04,
            "take_profit_pct": 0.10,
            "description": "MACD 지표 기반 중기 트레이딩"
        }
    ]

    for preset_data in presets:
        manager.save_preset(**preset_data)

    # 모든 프리셋 조회
    all_presets = manager.list_presets()
    print(f"\n저장된 프리셋: {len(all_presets)}개\n")

    for preset in all_presets:
        print(f"📋 {preset['name']}")
        print(f"   전략: {preset['strategy']}")
        print(f"   종목: {', '.join(preset['symbols'])}")
        print(f"   초기 자본: ${preset['initial_capital']:,.2f}")
        print(f"   설명: {preset.get('description', 'N/A')}")
        print()


def test_delete_preset():
    """프리셋 삭제 테스트"""
    print("\n" + "=" * 60)
    print("TEST 3: 프리셋 삭제")
    print("=" * 60)

    manager = StrategyPresetManager(presets_file="data/test_presets.json")

    print("\n삭제 전 프리셋 수:", len(manager.list_presets()))

    # 프리셋 삭제
    success = manager.delete_preset("공격적 RSI 전략")

    if success:
        print("✅ 프리셋 삭제 성공!")
    else:
        print("❌ 프리셋 삭제 실패")

    print("삭제 후 프리셋 수:", len(manager.list_presets()))


def test_update_preset():
    """프리셋 업데이트 테스트"""
    print("\n" + "=" * 60)
    print("TEST 4: 프리셋 업데이트")
    print("=" * 60)

    manager = StrategyPresetManager(presets_file="data/test_presets.json")

    # 기존 프리셋 수정 (같은 이름으로 다시 저장)
    print("\n기존 프리셋 수정 중...")
    manager.save_preset(
        name="보수적 RSI 전략",
        strategy="RSI Strategy",
        strategy_params={"period": 20, "overbought": 75, "oversold": 25},  # 파라미터 변경
        initial_capital=15000.0,  # 자본 변경
        position_size=0.25,  # 포지션 크기 변경
        symbols=["AAPL", "MSFT", "GOOGL"],  # 종목 추가
        stop_loss_pct=0.04,
        take_profit_pct=0.08,
        enable_stop_loss=True,
        enable_take_profit=True,
        description="파라미터를 조정한 보수적 전략"
    )

    # 변경된 프리셋 확인
    updated = manager.load_preset("보수적 RSI 전략")
    print("✅ 프리셋 업데이트 성공!")
    print(f"   새 파라미터: {updated['strategy_params']}")
    print(f"   새 초기 자본: ${updated['initial_capital']:,.2f}")
    print(f"   새 종목: {updated['symbols']}")


def test_export_import():
    """프리셋 내보내기/가져오기 테스트"""
    print("\n" + "=" * 60)
    print("TEST 5: 프리셋 내보내기/가져오기")
    print("=" * 60)

    manager = StrategyPresetManager(presets_file="data/test_presets.json")

    # 프리셋 내보내기
    print("\n프리셋 내보내기 중...")
    export_path = "data/exported_preset.json"
    success = manager.export_preset("보수적 RSI 전략", export_path)

    if success:
        print(f"✅ 프리셋을 {export_path}로 내보냈습니다")
    else:
        print("❌ 내보내기 실패")
        return

    # 새 매니저로 프리셋 가져오기
    manager2 = StrategyPresetManager(presets_file="data/test_presets2.json")
    print("\n프리셋 가져오기 중...")
    success = manager2.import_preset(export_path)

    if success:
        print("✅ 프리셋 가져오기 성공!")
        imported = manager2.load_preset("보수적 RSI 전략")
        print(f"   가져온 전략: {imported['strategy']}")
        print(f"   가져온 종목: {imported['symbols']}")
    else:
        print("❌ 가져오기 실패")


def main():
    """모든 테스트 실행"""
    print("\n" + "=" * 60)
    print("전략 프리셋 관리 기능 테스트")
    print("=" * 60 + "\n")

    # 테스트 실행
    test_save_and_load_preset()
    test_list_presets()
    test_delete_preset()
    test_update_preset()
    test_export_import()

    print("\n" + "=" * 60)
    print("모든 테스트 완료")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
