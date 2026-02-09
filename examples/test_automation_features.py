"""
Test Automation Features

남은 기능 테스트:
1. CSV 리포트 생성
2. Parameter Persistence
3. Retry Logic
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.database import TradingDatabase
from trading_bot.reports import ReportGenerator
from trading_bot.strategy_presets import StrategyPresetManager
from trading_bot.retry_utils import retry_with_backoff, CircuitBreaker
import tempfile
import os
import time


def test_report_generation():
    """Test 1: CSV/JSON 리포트 생성"""
    print("\n" + "=" * 60)
    print("TEST 1: CSV/JSON 리포트 생성")
    print("=" * 60)

    # Temporary database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test.db')

    try:
        # Create database and sample session
        db = TradingDatabase(db_path=db_path)

        # Create session
        session_id = db.create_session('TestStrategy', 10000.0)
        print(f"✓ 세션 생성: {session_id}")

        # Log some trades
        db.log_trade(session_id, {
            'symbol': 'AAPL',
            'timestamp': '2026-02-09 10:00:00',
            'type': 'BUY',
            'price': 150.0,
            'size': 10.0,
            'commission': 1.5,
            'pnl': 0,
            'portfolio_value': 10000.0
        })

        db.log_trade(session_id, {
            'symbol': 'AAPL',
            'timestamp': '2026-02-09 15:00:00',
            'type': 'SELL',
            'price': 155.0,
            'size': 10.0,
            'commission': 1.55,
            'pnl': 46.95,
            'portfolio_value': 10046.95
        })

        print("✓ 거래 로그 기록")

        # Update session with final metrics
        db.update_session(session_id, {
            'final_capital': 10046.95,
            'total_return': 0.47,
            'sharpe_ratio': 1.2,
            'max_drawdown': -0.5,
            'win_rate': 100.0,
            'status': 'completed'
        })

        print("✓ 세션 업데이트")

        # Generate reports
        report_gen = ReportGenerator(db)
        report_files = report_gen.generate_session_report(
            session_id,
            output_dir=os.path.join(temp_dir, 'reports'),
            formats=['csv', 'json']
        )

        print("\n리포트 생성 결과:")
        for format_name, file_path in report_files.items():
            file_exists = os.path.exists(file_path)
            status = "✓" if file_exists else "✗"
            print(f"  {status} {format_name.upper()}: {file_path}")

        # Check files exist
        assert all(os.path.exists(f) for f in report_files.values()), "리포트 파일 생성 실패"

        print("\n✅ TEST 1 통과: 리포트 생성 성공")

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_parameter_persistence():
    """Test 2: 파라미터 영속성 (프리셋 저장/로드)"""
    print("\n" + "=" * 60)
    print("TEST 2: 파라미터 영속성")
    print("=" * 60)

    # Temporary preset file
    temp_dir = tempfile.mkdtemp()
    preset_file = os.path.join(temp_dir, 'presets.json')

    try:
        manager = StrategyPresetManager(presets_file=preset_file)

        # Save optimized parameters
        optimized_params = {
            'period': 14,
            'overbought': 75,
            'oversold': 25
        }

        preset_name = "자동최적화_test"
        manager.save_preset(
            name=preset_name,
            description="테스트 최적화 결과",
            strategy="RSI Strategy",
            strategy_params=optimized_params,
            symbols=['AAPL', 'MSFT'],
            initial_capital=10000.0,
            position_size=0.3
        )

        print(f"✓ 프리셋 저장: {preset_name}")

        # Load preset
        loaded_preset = manager.load_preset(preset_name)

        assert loaded_preset is not None, "프리셋 로드 실패"
        assert loaded_preset['strategy_params'] == optimized_params, "파라미터 불일치"

        print(f"✓ 프리셋 로드 성공")
        print(f"  파라미터: {loaded_preset['strategy_params']}")
        print(f"  종목: {loaded_preset['symbols']}")

        print("\n✅ TEST 2 통과: 파라미터 영속성 성공")

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_retry_logic():
    """Test 3: 재시도 로직"""
    print("\n" + "=" * 60)
    print("TEST 3: 재시도 로직")
    print("=" * 60)

    # Test retry_with_backoff
    call_count = 0

    @retry_with_backoff(max_retries=3, backoff_factor=1.5, initial_delay=0.1)
    def flaky_function():
        nonlocal call_count
        call_count += 1
        print(f"  호출 {call_count}회")

        if call_count < 3:
            raise Exception("일시적 오류")

        return "성공"

    result = flaky_function()
    assert result == "성공", "재시도 로직 실패"
    assert call_count == 3, f"재시도 횟수 불일치: {call_count} != 3"

    print("✓ retry_with_backoff 테스트 통과")

    # Test Circuit Breaker
    breaker = CircuitBreaker(failure_threshold=3, timeout=1.0)

    fail_count = 0

    @breaker
    def failing_function():
        nonlocal fail_count
        fail_count += 1
        raise Exception("API 오류")

    # Trigger circuit breaker
    for i in range(3):
        try:
            failing_function()
        except:
            pass

    print(f"✓ Circuit Breaker 상태: {breaker.state}")
    assert breaker.state == 'OPEN', f"Circuit Breaker 상태 불일치: {breaker.state}"

    # Wait for timeout
    print("  1초 대기 중...")
    time.sleep(1.1)

    # Should transition to HALF_OPEN
    try:
        failing_function()
    except:
        pass

    print(f"✓ Circuit Breaker 상태: {breaker.state} (타임아웃 후)")

    print("\n✅ TEST 3 통과: 재시도 로직 성공")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("자동화 기능 테스트 시작")
    print("=" * 60)

    try:
        test_report_generation()
        test_parameter_persistence()
        test_retry_logic()

        print("\n" + "=" * 60)
        print("✅ 모든 테스트 통과!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
