"""
RSI+MACD 복합 전략 프리셋 생성 스크립트
"""
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategy_presets import StrategyPresetManager


def create_tech_bounce_presets():
    """기술주 반등 전략 프리셋 생성"""
    manager = StrategyPresetManager()

    # 1. 보수적 전략
    print("1️⃣ 보수적 기술주 반등 전략 생성 중...")
    manager.save_preset(
        name="기술주 반등 - 보수적",
        description="안정적인 수익을 위한 보수적 RSI+MACD 조합. Stop Loss 3%, Take Profit 8%",
        strategy="RSI+MACD Combo",
        strategy_params={
            'rsi_period': 14,
            'rsi_oversold': 30,  # 더 엄격한 진입
            'rsi_overbought': 70,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9
        },
        symbols=['AAPL', 'MSFT'],
        initial_capital=10000.0,
        position_size=0.25,  # 25%
        stop_loss_pct=0.03,  # 3%
        take_profit_pct=0.08,  # 8%
        enable_stop_loss=True,
        enable_take_profit=True
    )
    print("   ✅ 저장 완료!")

    # 2. 균형형 전략 (권장)
    print("\n2️⃣ 균형형 기술주 반등 전략 생성 중...")
    manager.save_preset(
        name="기술주 반등 - 균형형 (권장)",
        description="리스크와 수익의 균형을 맞춘 전략. Stop Loss 5%, Take Profit 12%",
        strategy="RSI+MACD Combo",
        strategy_params={
            'rsi_period': 14,
            'rsi_oversold': 35,
            'rsi_overbought': 70,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9
        },
        symbols=['AAPL', 'MSFT', 'GOOGL'],
        initial_capital=10000.0,
        position_size=0.30,  # 30%
        stop_loss_pct=0.05,  # 5%
        take_profit_pct=0.12,  # 12%
        enable_stop_loss=True,
        enable_take_profit=True
    )
    print("   ✅ 저장 완료!")

    # 3. 공격적 전략
    print("\n3️⃣ 공격적 기술주 반등 전략 생성 중...")
    manager.save_preset(
        name="기술주 반등 - 공격적",
        description="높은 수익을 노리는 공격적 전략. 변동성 높은 종목 포함. Stop Loss 7%, Take Profit 20%",
        strategy="RSI+MACD Combo",
        strategy_params={
            'rsi_period': 14,
            'rsi_oversold': 40,  # 더 자주 진입
            'rsi_overbought': 70,
            'macd_fast': 10,  # 더 민감하게
            'macd_slow': 24,
            'macd_signal': 9
        },
        symbols=['NVDA', 'TSLA', 'AMD'],
        initial_capital=10000.0,
        position_size=0.40,  # 40%
        stop_loss_pct=0.07,  # 7%
        take_profit_pct=0.20,  # 20%
        enable_stop_loss=True,
        enable_take_profit=True
    )
    print("   ✅ 저장 완료!")

    # 4. 대형주 안정 전략
    print("\n4️⃣ 대형 기술주 안정 전략 생성 중...")
    manager.save_preset(
        name="대형 기술주 - 안정형",
        description="FAANG 대형주 중심의 안정적 전략. Stop Loss 4%, Take Profit 10%",
        strategy="RSI+MACD Combo",
        strategy_params={
            'rsi_period': 14,
            'rsi_oversold': 33,
            'rsi_overbought': 70,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9
        },
        symbols=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
        initial_capital=10000.0,
        position_size=0.20,  # 20% (분산)
        stop_loss_pct=0.04,  # 4%
        take_profit_pct=0.10,  # 10%
        enable_stop_loss=True,
        enable_take_profit=True
    )
    print("   ✅ 저장 완료!")

    # 5. 빠른 매매 전략
    print("\n5️⃣ 빠른 매매 전략 생성 중...")
    manager.save_preset(
        name="기술주 반등 - 빠른 매매",
        description="짧은 기간으로 더 자주 거래. Stop Loss 3%, Take Profit 6%",
        strategy="RSI+MACD Combo",
        strategy_params={
            'rsi_period': 10,  # 짧은 기간
            'rsi_oversold': 40,
            'rsi_overbought': 65,
            'macd_fast': 8,
            'macd_slow': 17,
            'macd_signal': 9
        },
        symbols=['AAPL', 'MSFT', 'NVDA'],
        initial_capital=10000.0,
        position_size=0.35,  # 35%
        stop_loss_pct=0.03,  # 3%
        take_profit_pct=0.06,  # 6%
        enable_stop_loss=True,
        enable_take_profit=True
    )
    print("   ✅ 저장 완료!")

    # 프리셋 목록 출력
    print("\n\n" + "="*60)
    print("✅ 모든 프리셋 생성 완료!")
    print("="*60)
    print("\n📋 생성된 프리셋 목록:\n")

    all_presets = manager.list_presets()
    for i, preset_name in enumerate(all_presets, 1):
        preset = manager.load_preset(preset_name)
        print(f"{i}. {preset_name}")
        print(f"   - 전략: {preset['strategy']}")
        print(f"   - 종목: {', '.join(preset['symbols'])}")
        print(f"   - 손절/익절: {preset['stop_loss_pct']*100:.1f}% / {preset['take_profit_pct']*100:.1f}%")
        print(f"   - 설명: {preset.get('description', 'N/A')}")
        print()

    print("="*60)
    print("🎯 대시보드에서 사용하기:")
    print("1. Paper Trading 탭으로 이동")
    print("2. 프리셋 드롭다운에서 원하는 프리셋 선택")
    print("3. '불러오기' 버튼 클릭")
    print("4. 'Start Paper Trading' 클릭!")
    print("="*60)


if __name__ == '__main__':
    create_tech_bounce_presets()
