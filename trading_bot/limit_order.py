"""
Limit Order System - 지정가 주문 관리

PendingOrder 데이터 클래스와 LimitOrderManager를 제공합니다.
- Paper Trading: OHLCV high/low 기반 체결 시뮬레이션
- Live Trading: 브로커 API 체결 확인
- 체인 주문: 체결 후 반대 방향 주문 자동 생성

Usage:
    from trading_bot.limit_order import LimitOrderManager, PendingOrder

    manager = LimitOrderManager(db=db, lock=lock)
    manager.create_limit_order(
        session_id='session_1',
        symbol='NVDA',
        side='buy',
        limit_price=172.0,
        amount=5000.0,
        trigger_order={'side': 'sell', 'price': 190.0},
    )
"""

import json
import logging
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class PendingOrder:
    """지정가 주문 데이터 클래스"""

    order_id: str
    session_id: str
    symbol: str
    side: str  # 'buy' | 'sell'
    limit_price: float
    amount: float  # buy: 달러 금액, sell: 주식 수량
    status: str = 'pending'  # 'pending' | 'filled' | 'canceled' | 'expired'
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    expires_at: Optional[datetime] = None  # None = GTC (Good Till Canceled)
    trigger_order: Optional[Dict[str, Any]] = None  # 체결 후 자동 생성할 반대 주문
    broker_order_id: Optional[str] = None  # 실거래용
    source: str = 'manual'  # 'manual' | 'preset' | 'chained'

    def to_db_dict(self) -> Dict[str, Any]:
        """DB 저장용 딕셔너리 변환"""
        return {
            'order_id': self.order_id,
            'session_id': self.session_id,
            'symbol': self.symbol,
            'side': self.side,
            'limit_price': self.limit_price,
            'amount': self.amount,
            'status': self.status,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'filled_at': self.filled_at.isoformat() if isinstance(self.filled_at, datetime) else self.filled_at,
            'fill_price': self.fill_price,
            'expires_at': self.expires_at.isoformat() if isinstance(self.expires_at, datetime) else self.expires_at,
            'trigger_order': json.dumps(self.trigger_order) if self.trigger_order else None,
            'broker_order_id': self.broker_order_id,
            'source': self.source,
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'PendingOrder':
        """DB 행에서 PendingOrder 생성"""
        trigger_order = None
        if row.get('trigger_order'):
            if isinstance(row['trigger_order'], dict):
                trigger_order = row['trigger_order']
            else:
                try:
                    trigger_order = json.loads(row['trigger_order'])
                except (json.JSONDecodeError, TypeError):
                    pass

        created_at = row['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        filled_at = row.get('filled_at')
        if isinstance(filled_at, str) and filled_at:
            filled_at = datetime.fromisoformat(filled_at)

        expires_at = row.get('expires_at')
        if isinstance(expires_at, str) and expires_at:
            expires_at = datetime.fromisoformat(expires_at)

        return cls(
            order_id=row['order_id'],
            session_id=row['session_id'],
            symbol=row['symbol'],
            side=row['side'],
            limit_price=row['limit_price'],
            amount=row['amount'],
            status=row.get('status', 'pending'),
            created_at=created_at,
            filled_at=filled_at,
            fill_price=row.get('fill_price'),
            expires_at=expires_at,
            trigger_order=trigger_order,
            broker_order_id=row.get('broker_order_id'),
            source=row.get('source', 'manual'),
        )


class LimitOrderManager:
    """
    지정가 주문 관리자

    Paper Trading과 Live Trading 모두를 지원합니다.
    - Paper: ticker의 high/low를 사용하여 체결 시뮬레이션
    - Live: broker.fetch_order()로 체결 상태 확인
    """

    def __init__(self, db=None, lock: Optional[threading.RLock] = None):
        """
        Initialize LimitOrderManager

        Args:
            db: TradingDatabase instance (optional)
            lock: Thread lock for state mutations (optional)
        """
        self._db = db
        self._lock = lock or threading.RLock()
        self._pending: Dict[str, PendingOrder] = {}  # order_id -> PendingOrder

    def create_limit_order(
        self,
        session_id: str,
        symbol: str,
        side: str,
        limit_price: float,
        amount: float,
        expires_at: Optional[datetime] = None,
        trigger_order: Optional[Dict[str, Any]] = None,
        broker_order_id: Optional[str] = None,
        source: str = 'manual',
    ) -> PendingOrder:
        """
        지정가 주문 생성

        Args:
            session_id: 세션 ID
            symbol: 종목 심볼
            side: 'buy' 또는 'sell'
            limit_price: 지정가
            amount: buy 시 달러 금액, sell 시 주식 수량
            expires_at: 만료 시간 (None = GTC)
            trigger_order: 체결 후 자동 생성할 반대 주문 {'side': 'sell', 'price': 190.0}
            broker_order_id: 실거래 브로커 주문 ID
            source: 주문 소스 ('manual', 'preset', 'chained')

        Returns:
            생성된 PendingOrder
        """
        if side not in ('buy', 'sell'):
            raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'")
        if limit_price <= 0:
            raise ValueError(f"Invalid limit_price: {limit_price}. Must be positive")
        if amount <= 0:
            raise ValueError(f"Invalid amount: {amount}. Must be positive")

        order = PendingOrder(
            order_id=str(uuid.uuid4()),
            session_id=session_id,
            symbol=symbol,
            side=side,
            limit_price=limit_price,
            amount=amount,
            status='pending',
            created_at=datetime.now(),
            expires_at=expires_at,
            trigger_order=trigger_order,
            broker_order_id=broker_order_id,
            source=source,
        )

        with self._lock:
            self._pending[order.order_id] = order

        # DB 저장
        if self._db:
            self._db.create_pending_order(order.to_db_dict())

        logger.info(
            f"[지정가 주문 생성] {side.upper()} {symbol} @ ${limit_price:.2f} "
            f"(amount={amount:.2f}, source={source}, order_id={order.order_id[:8]})"
        )

        return order

    def cancel_order(self, order_id: str) -> bool:
        """
        주문 취소

        Args:
            order_id: 취소할 주문 ID

        Returns:
            취소 성공 여부
        """
        with self._lock:
            order = self._pending.get(order_id)
            if not order:
                logger.warning(f"주문을 찾을 수 없음: {order_id[:8]}")
                return False

            if order.status != 'pending':
                logger.warning(f"취소 불가: 주문 상태={order.status} (order_id={order_id[:8]})")
                return False

            order.status = 'canceled'

        # DB 업데이트
        if self._db:
            self._db.update_pending_order(order_id, {'status': 'canceled'})

        logger.info(
            f"[지정가 주문 취소] {order.side.upper()} {order.symbol} "
            f"@ ${order.limit_price:.2f} (order_id={order_id[:8]})"
        )
        return True

    def get_pending_orders(
        self,
        session_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[PendingOrder]:
        """
        대기 중인 주문 조회

        Args:
            session_id: 세션 ID 필터 (optional)
            symbol: 심볼 필터 (optional)

        Returns:
            대기 중인 PendingOrder 리스트
        """
        with self._lock:
            orders = list(self._pending.values())

        result = [o for o in orders if o.status == 'pending']

        if session_id:
            result = [o for o in result if o.session_id == session_id]
        if symbol:
            result = [o for o in result if o.symbol == symbol]

        return result

    def get_all_orders(
        self,
        session_id: Optional[str] = None,
    ) -> List[PendingOrder]:
        """
        모든 주문 조회 (상태 무관)

        Args:
            session_id: 세션 ID 필터 (optional)

        Returns:
            모든 PendingOrder 리스트
        """
        with self._lock:
            orders = list(self._pending.values())

        if session_id:
            orders = [o for o in orders if o.session_id == session_id]

        return orders

    def check_and_fill_paper(
        self,
        symbol: str,
        ticker: Dict[str, Any],
        timestamp: datetime,
        execute_buy_fn: Callable,
        execute_sell_fn: Callable,
    ) -> List[PendingOrder]:
        """
        페이퍼 트레이딩 체결 시뮬레이션

        ticker의 high/low를 사용하여 지정가 도달 여부를 확인합니다.
        - buy limit: low <= limit_price -> 지정가에 체결
        - sell limit: high >= limit_price -> 지정가에 체결

        Args:
            symbol: 종목 심볼
            ticker: 시세 데이터 {'last': float, 'high': float, 'low': float}
            timestamp: 현재 타임스탬프
            execute_buy_fn: 매수 실행 함수 (symbol, price, timestamp)
            execute_sell_fn: 매도 실행 함수 (symbol, price, timestamp, reason)

        Returns:
            체결된 PendingOrder 리스트
        """
        # 만료 처리 먼저
        self._check_expirations(timestamp)

        # lock 안에서 pending 목록 스냅샷 생성 (이중 체결 방지)
        with self._lock:
            pending = [
                o for o in self._pending.values()
                if o.status == 'pending' and o.symbol == symbol
            ]

        if not pending:
            return []

        high = ticker.get('high', ticker.get('last', 0))
        low = ticker.get('low', ticker.get('last', 0))

        filled: List[PendingOrder] = []

        for order in pending:
            # 이중 체결 방지: 다른 스레드에서 상태 변경되었을 수 있음
            if order.status != 'pending':
                continue

            should_fill = False

            if order.side == 'buy' and low <= order.limit_price:
                # 매수 지정가: low가 지정가 이하면 체결
                should_fill = True
            elif order.side == 'sell' and high >= order.limit_price:
                # 매도 지정가: high가 지정가 이상이면 체결
                should_fill = True

            if not should_fill:
                continue

            # 체결 실행
            try:
                if order.side == 'buy':
                    execute_buy_fn(symbol, order.limit_price, timestamp, amount=order.amount)
                else:
                    execute_sell_fn(symbol, order.limit_price, timestamp, reason='limit_order')

                # 상태 업데이트
                with self._lock:
                    if order.status != 'pending':
                        # 체결 직전에 다른 스레드가 취소/만료 처리한 경우
                        logger.warning(f"주문 {order.order_id[:8]} 이미 {order.status} 상태, 체결 건너뜀")
                        continue
                    order.status = 'filled'
                    order.fill_price = order.limit_price
                    order.filled_at = timestamp

                # DB 업데이트
                if self._db:
                    self._db.update_pending_order(order.order_id, {
                        'status': 'filled',
                        'fill_price': order.limit_price,
                        'filled_at': timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
                    })

                filled.append(order)

                logger.info(
                    f"[지정가 체결] {order.side.upper()} {symbol} "
                    f"@ ${order.fill_price:.2f} (order_id={order.order_id[:8]})"
                )

                # 체인 주문 생성
                if order.trigger_order:
                    self._create_chained_order(order)

            except Exception as e:
                logger.error(
                    f"지정가 주문 체결 실패: {order.side.upper()} {symbol} "
                    f"@ ${order.limit_price:.2f}: {e}"
                )

        return filled

    def check_and_fill_live(
        self,
        symbol: str,
        broker,
        timestamp: datetime,
    ) -> List[PendingOrder]:
        """
        실거래 체결 확인

        broker.fetch_order()를 호출하여 브로커 측 체결 상태를 확인합니다.

        Args:
            symbol: 종목 심볼
            broker: BaseBroker 인스턴스
            timestamp: 현재 타임스탬프

        Returns:
            체결된 PendingOrder 리스트
        """
        # 만료 처리 먼저
        self._check_expirations(timestamp)

        # lock 안에서 pending 목록 스냅샷 생성
        with self._lock:
            pending = [
                o for o in self._pending.values()
                if o.status == 'pending' and o.symbol == symbol
            ]

        if not pending:
            return []

        filled: List[PendingOrder] = []

        for order in pending:
            if not order.broker_order_id:
                continue

            try:
                broker_order = broker.fetch_order(order.broker_order_id, symbol)

                if broker_order.get('status') == 'closed':
                    with self._lock:
                        order.status = 'filled'
                        order.fill_price = broker_order.get('price', order.limit_price)
                        order.filled_at = timestamp

                    if self._db:
                        self._db.update_pending_order(order.order_id, {
                            'status': 'filled',
                            'fill_price': order.fill_price,
                            'filled_at': timestamp.isoformat(),
                        })

                    filled.append(order)

                    logger.info(
                        f"[실거래 체결 확인] {order.side.upper()} {symbol} "
                        f"@ ${order.fill_price:.2f} (broker_id={order.broker_order_id})"
                    )

                    if order.trigger_order:
                        self._create_chained_order(order)

            except Exception as e:
                logger.error(
                    f"실거래 체결 확인 실패: {order.side.upper()} {symbol} "
                    f"(broker_id={order.broker_order_id}): {e}"
                )

        return filled

    def load_from_db(self, session_id: str):
        """
        DB에서 주문 복원 (재시작 시 사용)

        Args:
            session_id: 복원할 세션 ID
        """
        if not self._db:
            logger.warning("DB 없이 load_from_db 호출됨")
            return

        rows = self._db.get_pending_orders(session_id, status='pending')

        with self._lock:
            for row in rows:
                order = PendingOrder.from_db_row(row)
                self._pending[order.order_id] = order

        logger.info(f"DB에서 {len(rows)}개 대기 주문 복원 (session_id={session_id})")

    def cancel_all(self, session_id: str) -> int:
        """
        세션의 모든 대기 주문 취소

        Args:
            session_id: 세션 ID

        Returns:
            취소된 주문 수
        """
        pending = self.get_pending_orders(session_id=session_id)
        canceled_count = 0

        for order in pending:
            if self.cancel_order(order.order_id):
                canceled_count += 1

        if canceled_count > 0:
            logger.info(f"세션 {session_id}의 {canceled_count}개 대기 주문 취소")

        return canceled_count

    def _create_chained_order(self, filled_order: PendingOrder):
        """
        체인 주문 생성 (체결된 주문의 trigger_order 기반)

        Args:
            filled_order: 체결된 원본 주문
        """
        trigger = filled_order.trigger_order
        if not trigger:
            return

        trigger_side = trigger.get('side')
        trigger_price = trigger.get('price')

        if not trigger_side or not trigger_price:
            logger.warning(f"체인 주문 정보 불완전: {trigger}")
            return

        # amount 결정: sell일 때는 체결된 주식 수량, buy일 때는 원본 금액
        fill_price = filled_order.fill_price or filled_order.limit_price
        if trigger_side == 'sell' and filled_order.side == 'buy':
            # 매수 체결 후 매도 체인: 매수로 획득한 수량 추정
            # amount는 원래 달러 금액이므로 fill_price로 나누어 수량 추정
            trigger_amount = filled_order.amount / fill_price
        elif trigger_side == 'buy' and filled_order.side == 'sell':
            # 매도 체결 후 매수 체인: 매도 수익금
            trigger_amount = filled_order.amount * fill_price
        else:
            trigger_amount = filled_order.amount

        chained = self.create_limit_order(
            session_id=filled_order.session_id,
            symbol=filled_order.symbol,
            side=trigger_side,
            limit_price=trigger_price,
            amount=trigger_amount,
            source='chained',
        )

        logger.info(
            f"[체인 주문 생성] {trigger_side.upper()} {filled_order.symbol} "
            f"@ ${trigger_price:.2f} (원본={filled_order.order_id[:8]}, "
            f"체인={chained.order_id[:8]})"
        )

    def _check_expirations(self, current_time: datetime):
        """
        만료된 주문 처리

        Args:
            current_time: 현재 시간
        """
        with self._lock:
            for order in list(self._pending.values()):
                if (order.status == 'pending'
                        and order.expires_at
                        and current_time >= order.expires_at):
                    order.status = 'expired'

                    if self._db:
                        self._db.update_pending_order(order.order_id, {
                            'status': 'expired',
                        })

                    logger.info(
                        f"[지정가 주문 만료] {order.side.upper()} {order.symbol} "
                        f"@ ${order.limit_price:.2f} (order_id={order.order_id[:8]})"
                    )
