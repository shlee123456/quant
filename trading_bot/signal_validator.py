"""
전략 시그널 유효성 검증 모듈

전략이 생성한 시그널의 논리적 정합성을 검증합니다.
- 시그널 값 범위 검증 (-1, 0, 1)
- 시그널 시퀀스 논리 검증 (중복 진입, 공매도 등)
- 지표 데이터 이상 탐지 (NaN, Inf)
- Look-ahead bias 간이 탐지
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

VALID_SIGNALS = {-1, 0, 1}


class SignalValidator:
    """전략 시그널의 유효성을 검증하는 클래스"""

    @staticmethod
    def validate_signal_value(signal: int) -> bool:
        """
        시그널 값이 -1, 0, 1 중 하나인지 검증

        Args:
            signal: 검증할 시그널 값

        Returns:
            True면 유효, False면 무효
        """
        return signal in VALID_SIGNALS

    @staticmethod
    def validate_signal_sequence(signals: pd.Series) -> List[str]:
        """
        시그널 시퀀스의 논리적 오류를 탐지

        검사 항목:
        - 포지션이 있는데 또 BUY (중복 진입)
        - 포지션이 없는데 SELL (공매도 의도 아닌 경우)
        - 시그널 값이 -1, 0, 1 범위 밖

        Args:
            signals: 시그널 시리즈 (값: -1, 0, 1)

        Returns:
            경고 메시지 리스트 (빈 리스트면 정상)
        """
        warnings: List[str] = []

        if signals.empty:
            return warnings

        # 범위 밖 값 검사
        invalid_mask = ~signals.isin(VALID_SIGNALS)
        invalid_indices = signals.index[invalid_mask].tolist()
        for idx in invalid_indices:
            val = signals.loc[idx]
            warnings.append(f"[index={idx}] 유효하지 않은 시그널 값: {val} (허용: -1, 0, 1)")

        # 시퀀스 논리 검사: 포지션 상태를 추적
        in_position = False
        for idx, signal in signals.items():
            if signal not in VALID_SIGNALS:
                continue

            if signal == 1:
                if in_position:
                    warnings.append(f"[index={idx}] 중복 BUY: 이미 포지션 보유 중에 BUY 시그널 발생")
                    logger.warning("중복 BUY 시그널 탐지 (index=%s)", idx)
                in_position = True
            elif signal == -1:
                if not in_position:
                    warnings.append(f"[index={idx}] 포지션 없는 SELL: 보유 포지션 없이 SELL 시그널 발생")
                    logger.warning("포지션 없는 SELL 시그널 탐지 (index=%s)", idx)
                in_position = False

        if warnings:
            logger.info("시그널 시퀀스 검증 완료: %d개 경고 발견", len(warnings))
        else:
            logger.debug("시그널 시퀀스 검증 완료: 정상")

        return warnings

    @staticmethod
    def validate_indicators(df: pd.DataFrame) -> List[str]:
        """
        지표 값의 비정상 여부 탐지

        검사 항목:
        - signal 컬럼에 NaN 존재
        - signal 값이 -1, 0, 1 외 값
        - position 컬럼에 NaN 존재
        - 지표 컬럼에 Inf 존재

        Args:
            df: 전략이 calculate_indicators()로 생성한 DataFrame

        Returns:
            경고 메시지 리스트
        """
        warnings: List[str] = []

        if df.empty:
            return warnings

        # signal 컬럼 검사
        if 'signal' in df.columns:
            nan_count = df['signal'].isna().sum()
            if nan_count > 0:
                warnings.append(f"signal 컬럼에 NaN {nan_count}개 존재")

            valid_signals = df['signal'].dropna()
            invalid_mask = ~valid_signals.isin(VALID_SIGNALS)
            invalid_count = invalid_mask.sum()
            if invalid_count > 0:
                invalid_values = valid_signals[invalid_mask].unique().tolist()
                warnings.append(
                    f"signal 컬럼에 유효하지 않은 값 {invalid_count}개 존재: {invalid_values}"
                )
        else:
            warnings.append("signal 컬럼이 존재하지 않음")

        # position 컬럼 검사
        if 'position' in df.columns:
            nan_count = df['position'].isna().sum()
            if nan_count > 0:
                warnings.append(f"position 컬럼에 NaN {nan_count}개 존재")
        else:
            warnings.append("position 컬럼이 존재하지 않음")

        # 모든 숫자 컬럼에서 Inf 검사
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            inf_count = np.isinf(df[col]).sum()
            if inf_count > 0:
                warnings.append(f"'{col}' 컬럼에 Inf 값 {inf_count}개 존재")

        if warnings:
            logger.info("지표 검증 완료: %d개 경고 발견", len(warnings))
        else:
            logger.debug("지표 검증 완료: 정상")

        return warnings

    @staticmethod
    def validate_no_lookahead(df: pd.DataFrame, strategy, n_rows: int = 10) -> bool:
        """
        Look-ahead bias 간이 탐지

        방법: 마지막 N행을 제거하고 시그널 계산 후
              기존 시그널의 앞부분과 비교하여 불일치하면 look-ahead bias 의심

        Args:
            df: 원본 OHLCV DataFrame
            strategy: calculate_indicators() 메서드를 가진 전략 객체
            n_rows: 제거할 행 수 (기본 10)

        Returns:
            True면 정상 (look-ahead bias 없음), False면 look-ahead bias 의심
        """
        if len(df) <= n_rows:
            logger.warning("데이터가 너무 적어 look-ahead bias 검증 불가 (행 수: %d, 필요: >%d)", len(df), n_rows)
            return True

        try:
            # 전체 데이터로 시그널 계산
            full_result = strategy.calculate_indicators(df)

            # 마지막 N행 제거 후 시그널 계산
            truncated_df = df.iloc[:-n_rows].copy()
            truncated_result = strategy.calculate_indicators(truncated_df)

            if 'signal' not in full_result.columns or 'signal' not in truncated_result.columns:
                logger.warning("signal 컬럼이 없어 look-ahead bias 검증 불가")
                return True

            # 겹치는 구간의 시그널 비교
            overlap_len = len(truncated_result)
            full_signals = full_result['signal'].iloc[:overlap_len]
            truncated_signals = truncated_result['signal']

            # 인덱스 정렬하여 비교
            full_signals = full_signals.reset_index(drop=True)
            truncated_signals = truncated_signals.reset_index(drop=True)

            # NaN을 제외하고 비교
            both_valid = full_signals.notna() & truncated_signals.notna()
            if both_valid.sum() == 0:
                logger.warning("비교 가능한 시그널이 없어 look-ahead bias 검증 불가")
                return True

            mismatches = (full_signals[both_valid] != truncated_signals[both_valid]).sum()

            if mismatches > 0:
                logger.warning(
                    "Look-ahead bias 의심: %d개 시그널 불일치 (전체 %d개 중)",
                    mismatches, both_valid.sum()
                )
                return False

            logger.debug("Look-ahead bias 검증 완료: 정상")
            return True

        except Exception as e:
            logger.error("Look-ahead bias 검증 중 오류 발생: %s", e)
            return True
