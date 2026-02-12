"""
OrderExecutionVerifier 단위 테스트
"""

import unittest

from trading_bot.execution_verifier import OrderExecutionVerifier


class TestVerifyExecution(unittest.TestCase):
    """verify_execution 테스트"""

    def setUp(self):
        self.verifier = OrderExecutionVerifier()

    def test_valid_buy_signal_buy_trade(self):
        """BUY 시그널에 BUY 주문 실행 - 정상"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0, 'size': 10.0},
            current_position=0.0,
        )
        self.assertTrue(is_valid)
        self.assertIn("검증 통과", msg)

    def test_valid_sell_signal_sell_trade(self):
        """SELL 시그널에 SELL 주문 실행 - 정상"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=-1,
            executed_trade={'type': 'SELL', 'price': 110.0, 'size': 10.0},
            current_position=10.0,
        )
        self.assertTrue(is_valid)
        self.assertIn("검증 통과", msg)

    def test_buy_signal_sell_trade_error(self):
        """BUY 시그널인데 SELL 주문 - 오류"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'SELL', 'price': 100.0, 'size': 10.0},
            current_position=10.0,
        )
        self.assertFalse(is_valid)
        self.assertIn("오류", msg)

    def test_sell_signal_buy_trade_error(self):
        """SELL 시그널인데 BUY 주문 - 오류"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=-1,
            executed_trade={'type': 'BUY', 'price': 100.0, 'size': 10.0},
            current_position=0.0,
        )
        self.assertFalse(is_valid)
        self.assertIn("오류", msg)

    def test_buy_signal_already_in_position_warning(self):
        """BUY 시그널이지만 이미 포지션 보유 - 경고"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0, 'size': 5.0},
            current_position=10.0,
        )
        self.assertTrue(is_valid)
        self.assertIn("경고", msg)

    def test_sell_signal_no_position_warning(self):
        """SELL 시그널이지만 포지션 없음 - 경고"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=-1,
            executed_trade={'type': 'SELL', 'price': 100.0, 'size': 0.0},
            current_position=0.0,
        )
        self.assertTrue(is_valid)
        self.assertIn("경고", msg)

    def test_sell_close_type(self):
        """SELL (CLOSE) 타입 처리"""
        is_valid, msg = self.verifier.verify_execution(
            expected_signal=-1,
            executed_trade={'type': 'SELL (CLOSE)', 'price': 110.0, 'size': 10.0},
            current_position=10.0,
        )
        self.assertTrue(is_valid)

    def test_verification_log_recorded(self):
        """검증 로그가 기록되는지 확인"""
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0},
            current_position=0.0,
        )
        self.assertEqual(len(self.verifier.verification_log), 1)
        self.assertEqual(self.verifier.verification_log[0]['check_type'], 'execution')


class TestVerifyPositionConsistency(unittest.TestCase):
    """verify_position_consistency 테스트"""

    def setUp(self):
        self.verifier = OrderExecutionVerifier()

    def test_consistent_positions(self):
        """포지션이 거래 기록과 일치"""
        positions = {'AAPL': 10.0, 'MSFT': 0.0}
        trades = [
            {'symbol': 'AAPL', 'type': 'BUY', 'size': 10.0},
            {'symbol': 'MSFT', 'type': 'BUY', 'size': 5.0},
            {'symbol': 'MSFT', 'type': 'SELL', 'size': 5.0},
        ]
        inconsistencies = self.verifier.verify_position_consistency(positions, trades)
        self.assertEqual(len(inconsistencies), 0)

    def test_inconsistent_position(self):
        """포지션 불일치 탐지"""
        positions = {'AAPL': 15.0}  # 실제 거래 기록은 10.0
        trades = [
            {'symbol': 'AAPL', 'type': 'BUY', 'size': 10.0},
        ]
        inconsistencies = self.verifier.verify_position_consistency(positions, trades)
        self.assertEqual(len(inconsistencies), 1)
        self.assertIn("불일치", inconsistencies[0])

    def test_empty_trades(self):
        """거래 기록 없을 때"""
        positions = {'AAPL': 0.0}
        trades = []
        inconsistencies = self.verifier.verify_position_consistency(positions, trades)
        self.assertEqual(len(inconsistencies), 0)

    def test_multiple_buy_sell_cycles(self):
        """여러 번 매수-매도 사이클"""
        positions = {'AAPL': 8.0}
        trades = [
            {'symbol': 'AAPL', 'type': 'BUY', 'size': 10.0},
            {'symbol': 'AAPL', 'type': 'SELL', 'size': 10.0},
            {'symbol': 'AAPL', 'type': 'BUY', 'size': 8.0},
        ]
        inconsistencies = self.verifier.verify_position_consistency(positions, trades)
        self.assertEqual(len(inconsistencies), 0)

    def test_multi_symbol_consistency(self):
        """멀티 심볼 포지션 정합성"""
        positions = {'AAPL': 10.0, 'MSFT': 5.0, 'GOOGL': 0.0}
        trades = [
            {'symbol': 'AAPL', 'type': 'BUY', 'size': 10.0},
            {'symbol': 'MSFT', 'type': 'BUY', 'size': 5.0},
            {'symbol': 'GOOGL', 'type': 'BUY', 'size': 3.0},
            {'symbol': 'GOOGL', 'type': 'SELL', 'size': 3.0},
        ]
        inconsistencies = self.verifier.verify_position_consistency(positions, trades)
        self.assertEqual(len(inconsistencies), 0)

    def test_verification_log_recorded(self):
        """검증 로그 기록 확인"""
        self.verifier.verify_position_consistency({'AAPL': 0.0}, [])
        log_entries = [e for e in self.verifier.verification_log if e['check_type'] == 'position_consistency']
        self.assertEqual(len(log_entries), 1)


class TestVerifyCapitalConsistency(unittest.TestCase):
    """verify_capital_consistency 테스트"""

    def setUp(self):
        self.verifier = OrderExecutionVerifier()

    def test_consistent_capital_no_trades(self):
        """거래 없이 자본금 일치"""
        is_consistent, msg = self.verifier.verify_capital_consistency(
            initial_capital=10000.0,
            trades=[],
            current_capital=10000.0,
        )
        self.assertTrue(is_consistent)

    def test_consistent_capital_with_trades(self):
        """거래 후 자본금 일치"""
        # 매수: $1000 투자, 이후 자본금 $9000
        # 매도: 수익 포함 $1100, 자본금 $10100
        trades = [
            {'type': 'BUY', 'price': 100.0, 'size': 10.0, 'capital': 9000.0, 'commission': 1.0},
            {'type': 'SELL', 'price': 110.0, 'size': 10.0, 'capital': 10100.0, 'commission': 1.1},
        ]
        is_consistent, msg = self.verifier.verify_capital_consistency(
            initial_capital=10000.0,
            trades=trades,
            current_capital=10100.0,
        )
        self.assertTrue(is_consistent)

    def test_inconsistent_capital(self):
        """자본금 불일치 탐지"""
        trades = [
            {'type': 'BUY', 'price': 100.0, 'size': 10.0, 'capital': 9000.0, 'commission': 1.0},
        ]
        # 거래 기록상 9000이어야 하지만 8000으로 기록
        is_consistent, msg = self.verifier.verify_capital_consistency(
            initial_capital=10000.0,
            trades=trades,
            current_capital=8000.0,
        )
        self.assertFalse(is_consistent)
        self.assertIn("불일치", msg)

    def test_tolerance(self):
        """허용 오차 내 차이"""
        is_consistent, msg = self.verifier.verify_capital_consistency(
            initial_capital=10000.0,
            trades=[],
            current_capital=10000.005,
            tolerance=0.01,
        )
        self.assertTrue(is_consistent)

    def test_tolerance_exceeded(self):
        """허용 오차 초과"""
        is_consistent, msg = self.verifier.verify_capital_consistency(
            initial_capital=10000.0,
            trades=[],
            current_capital=10000.02,
            tolerance=0.01,
        )
        self.assertFalse(is_consistent)

    def test_verification_log_recorded(self):
        """검증 로그 기록 확인"""
        self.verifier.verify_capital_consistency(10000.0, [], 10000.0)
        log_entries = [e for e in self.verifier.verification_log if e['check_type'] == 'capital_consistency']
        self.assertEqual(len(log_entries), 1)


class TestGenerateVerificationReport(unittest.TestCase):
    """generate_verification_report 테스트"""

    def setUp(self):
        self.verifier = OrderExecutionVerifier()

    def test_empty_report(self):
        """검증 없을 때 빈 리포트"""
        report = self.verifier.generate_verification_report()
        self.assertEqual(report['total_checks'], 0)
        self.assertEqual(report['passed'], 0)
        self.assertEqual(report['warnings'], 0)
        self.assertEqual(report['errors'], 0)

    def test_report_with_mixed_results(self):
        """다양한 결과가 포함된 리포트"""
        # 정상 케이스
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0},
            current_position=0.0,
        )
        # 오류 케이스
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'SELL', 'price': 100.0},
            current_position=10.0,
        )
        # 경고 케이스
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0},
            current_position=10.0,
        )

        report = self.verifier.generate_verification_report()
        self.assertEqual(report['total_checks'], 3)
        self.assertEqual(report['passed'], 1)
        self.assertEqual(report['errors'], 1)
        self.assertEqual(report['warnings'], 1)
        self.assertEqual(len(report['details']), 3)

    def test_report_structure(self):
        """리포트 구조 확인"""
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0},
            current_position=0.0,
        )
        report = self.verifier.generate_verification_report()

        self.assertIn('total_checks', report)
        self.assertIn('passed', report)
        self.assertIn('warnings', report)
        self.assertIn('errors', report)
        self.assertIn('details', report)
        self.assertIsInstance(report['details'], list)

    def test_report_after_all_check_types(self):
        """모든 검증 타입 실행 후 리포트"""
        self.verifier.verify_execution(
            expected_signal=1,
            executed_trade={'type': 'BUY', 'price': 100.0},
            current_position=0.0,
        )
        self.verifier.verify_position_consistency({'AAPL': 0.0}, [])
        self.verifier.verify_capital_consistency(10000.0, [], 10000.0)

        report = self.verifier.generate_verification_report()
        self.assertEqual(report['total_checks'], 3)
        self.assertEqual(report['passed'], 3)

        check_types = {entry['check_type'] for entry in report['details']}
        self.assertIn('execution', check_types)
        self.assertIn('position_consistency', check_types)
        self.assertIn('capital_consistency', check_types)


if __name__ == '__main__':
    unittest.main()
