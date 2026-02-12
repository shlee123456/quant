"""
주문 실행 정확성 검증 모듈

시그널과 실제 주문의 일치 여부, 포지션/자본금 정합성을 검증합니다.
- 시그널 대비 실제 주문 방향 확인
- 거래 기록 기반 포지션 재구성 및 검증
- 자본금 재계산 및 정합성 확인
- 검증 리포트 생성
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class OrderExecutionVerifier:
    """주문 실행의 정확성을 검증하는 클래스"""

    def __init__(self):
        self.verification_log: List[Dict] = []

    def verify_execution(
        self,
        expected_signal: int,
        executed_trade: Dict,
        current_position: float,
    ) -> Tuple[bool, str]:
        """
        시그널과 실제 주문이 일치하는지 확인

        검사 항목:
        - BUY 시그널인데 SELL 주문 실행 → 오류
        - SELL 시그널인데 BUY 주문 실행 → 오류
        - BUY 시그널인데 이미 포지션 있음 → 경고
        - SELL 시그널인데 포지션 없음 → 경고

        Args:
            expected_signal: 전략이 생성한 시그널 (1=BUY, -1=SELL, 0=HOLD)
            executed_trade: 실행된 거래 정보 {'type': 'BUY'|'SELL', ...}
            current_position: 거래 실행 전 현재 포지션 수량

        Returns:
            (is_valid, message) - is_valid가 False면 오류, True면 정상 또는 경고
        """
        trade_type = executed_trade.get('type', '').upper()
        # 'SELL (CLOSE)' 같은 형태도 처리
        is_buy = 'BUY' in trade_type
        is_sell = 'SELL' in trade_type

        result_is_valid = True
        message = "검증 통과"

        # 시그널과 주문 방향 불일치 검사 (오류)
        if expected_signal == 1 and is_sell:
            result_is_valid = False
            message = f"오류: BUY 시그널인데 SELL 주문 실행됨 (trade={trade_type})"
            logger.error(message)
        elif expected_signal == -1 and is_buy:
            result_is_valid = False
            message = f"오류: SELL 시그널인데 BUY 주문 실행됨 (trade={trade_type})"
            logger.error(message)
        # 상태 불일치 검사 (경고)
        elif expected_signal == 1 and is_buy and current_position > 0:
            message = f"경고: BUY 시그널이지만 이미 포지션 보유 중 (position={current_position:.6f})"
            logger.warning(message)
        elif expected_signal == -1 and is_sell and current_position <= 0:
            message = f"경고: SELL 시그널이지만 포지션 없음 (position={current_position:.6f})"
            logger.warning(message)

        # 검증 로그 기록
        log_entry = {
            'check_type': 'execution',
            'expected_signal': expected_signal,
            'executed_trade_type': trade_type,
            'current_position': current_position,
            'is_valid': result_is_valid,
            'message': message,
        }
        self.verification_log.append(log_entry)

        return result_is_valid, message

    def verify_position_consistency(
        self,
        positions: Dict[str, float],
        trades: List[Dict],
    ) -> List[str]:
        """
        현재 포지션이 거래 기록과 일치하는지 검증

        거래 기록을 처음부터 재구성하여 현재 포지션과 비교

        Args:
            positions: 현재 포지션 {symbol: quantity}
            trades: 거래 기록 리스트 [{'symbol': str, 'type': str, 'size': float, ...}]

        Returns:
            불일치 메시지 리스트 (빈 리스트면 정상)
        """
        inconsistencies: List[str] = []

        # 거래 기록으로 포지션 재구성
        reconstructed: Dict[str, float] = {}

        for trade in trades:
            symbol = trade.get('symbol', 'UNKNOWN')
            trade_type = trade.get('type', '').upper()
            size = trade.get('size', 0.0)

            if symbol not in reconstructed:
                reconstructed[symbol] = 0.0

            if 'BUY' in trade_type:
                reconstructed[symbol] += size
            elif 'SELL' in trade_type:
                reconstructed[symbol] = 0.0  # 전량 매도 가정

        # 재구성된 포지션과 현재 포지션 비교
        all_symbols = set(list(positions.keys()) + list(reconstructed.keys()))

        for symbol in all_symbols:
            current = positions.get(symbol, 0.0)
            expected = reconstructed.get(symbol, 0.0)

            if abs(current - expected) > 1e-8:
                msg = (
                    f"포지션 불일치 [{symbol}]: "
                    f"현재={current:.6f}, 거래기록 기반 재구성={expected:.6f}, "
                    f"차이={current - expected:.6f}"
                )
                inconsistencies.append(msg)
                logger.warning(msg)

        # 검증 로그 기록
        log_entry = {
            'check_type': 'position_consistency',
            'is_valid': len(inconsistencies) == 0,
            'inconsistency_count': len(inconsistencies),
            'message': "포지션 정합성 검증 통과" if not inconsistencies else f"{len(inconsistencies)}개 불일치 발견",
        }
        self.verification_log.append(log_entry)

        if not inconsistencies:
            logger.debug("포지션 정합성 검증 완료: 정상")

        return inconsistencies

    def verify_capital_consistency(
        self,
        initial_capital: float,
        trades: List[Dict],
        current_capital: float,
        tolerance: float = 0.01,
    ) -> Tuple[bool, str]:
        """
        자본금이 거래 기록과 일치하는지 검증

        초기 자본금에서 모든 거래를 재계산하여 현재 자본금과 비교

        Args:
            initial_capital: 초기 자본금
            trades: 거래 기록 리스트
            current_capital: 현재 자본금 (현금)
            tolerance: 허용 오차 (기본 0.01 = 1센트)

        Returns:
            (is_consistent, message)
        """
        reconstructed_capital = initial_capital

        for trade in trades:
            trade_type = trade.get('type', '').upper()
            commission = trade.get('commission', 0.0)

            if 'BUY' in trade_type:
                # BUY: capital 필드가 있으면 해당 값의 변화를 추적
                # 없으면 size * price + commission 차감
                price = trade.get('price', 0.0)
                size = trade.get('size', 0.0)
                if 'capital' in trade:
                    # trade에 기록된 capital이 거래 후 잔액이므로
                    # 직접 계산: 매수금액 = size * price / (1 - commission_rate)에 해당
                    # 하지만 정확한 매수 금액은 (이전 capital - trade['capital'])
                    trade_cost = reconstructed_capital - trade.get('capital', reconstructed_capital)
                    reconstructed_capital -= trade_cost
                else:
                    reconstructed_capital -= (size * price + commission)

            elif 'SELL' in trade_type:
                price = trade.get('price', 0.0)
                size = trade.get('size', 0.0)
                if 'capital' in trade:
                    # SELL 거래 후 자본금이 capital 필드에 기록됨
                    # sale_proceeds = capital(after) - capital(before)
                    sale_proceeds = trade['capital'] - reconstructed_capital
                    reconstructed_capital += sale_proceeds
                else:
                    reconstructed_capital += (size * price - commission)

        diff = abs(reconstructed_capital - current_capital)
        is_consistent = diff <= tolerance

        if is_consistent:
            message = f"자본금 정합성 검증 통과 (재구성={reconstructed_capital:.2f}, 현재={current_capital:.2f}, 차이={diff:.4f})"
            logger.debug(message)
        else:
            message = (
                f"자본금 불일치: 재구성={reconstructed_capital:.2f}, "
                f"현재={current_capital:.2f}, 차이={diff:.4f} (허용 오차={tolerance})"
            )
            logger.warning(message)

        # 검증 로그 기록
        log_entry = {
            'check_type': 'capital_consistency',
            'initial_capital': initial_capital,
            'reconstructed_capital': reconstructed_capital,
            'current_capital': current_capital,
            'difference': diff,
            'tolerance': tolerance,
            'is_valid': is_consistent,
            'message': message,
        }
        self.verification_log.append(log_entry)

        return is_consistent, message

    def generate_verification_report(self) -> Dict:
        """
        전체 검증 로그 기반 리포트 생성

        Returns:
            {
                'total_checks': int,
                'passed': int,
                'warnings': int,
                'errors': int,
                'details': List[Dict]
            }
        """
        total = len(self.verification_log)
        passed = 0
        warnings = 0
        errors = 0

        for entry in self.verification_log:
            msg = entry.get('message', '')
            if entry.get('is_valid', True):
                if msg.startswith('경고'):
                    warnings += 1
                else:
                    passed += 1
            else:
                errors += 1

        report = {
            'total_checks': total,
            'passed': passed,
            'warnings': warnings,
            'errors': errors,
            'details': list(self.verification_log),
        }

        logger.info(
            "검증 리포트 생성: 총 %d건 (통과=%d, 경고=%d, 오류=%d)",
            total, passed, warnings, errors,
        )

        return report
