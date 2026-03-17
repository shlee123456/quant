"""
Base layer for the 5-Layer Market Intelligence system.

모든 인텔리전스 레이어의 추상 기본 클래스와 표준 출력 데이터 클래스를 정의합니다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import logging


@dataclass
class LayerResult:
    """Standard output for every intelligence layer.

    Attributes:
        layer_name: 레이어 이름 (예: "macro_regime", "market_structure")
        score: -100 ~ +100 합성 점수
        signal: "bullish", "bearish", "neutral"
        confidence: 0.0 ~ 1.0 신뢰도
        metrics: 개별 서브 메트릭 점수 딕셔너리
        interpretation: 한국어 1줄 해석
        details: 추가 상세 정보 딕셔너리
    """
    layer_name: str
    score: float              # -100 to +100 composite score
    signal: str               # "bullish", "bearish", "neutral"
    confidence: float         # 0.0 to 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""   # One-line Korean summary
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 직렬화."""
        return {
            'layer': self.layer_name,
            'score': round(self.score, 1),
            'signal': self.signal,
            'confidence': round(self.confidence, 2),
            'metrics': self.metrics,
            'interpretation': self.interpretation,
            'details': self.details,
        }


class BaseIntelligenceLayer(ABC):
    """Abstract base for all 5 intelligence layers.

    모든 레이어는 이 클래스를 상속하고 ``analyze()`` 메서드를 구현해야 합니다.
    공통 유틸리티로 ``normalize_score()``, ``classify_score()``를 제공합니다.
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """레이어 분석 실행.

        Args:
            data: 분석에 필요한 데이터 딕셔너리 (레이어마다 상이)

        Returns:
            LayerResult 표준 결과 객체
        """
        pass

    @staticmethod
    def normalize_score(
        value: float,
        min_val: float,
        max_val: float,
        invert: bool = False,
    ) -> float:
        """Normalize any metric to -100..+100 scale.

        Args:
            value: 정규화할 원본 값
            min_val: 예상 최솟값 (이 값이 -100에 매핑)
            max_val: 예상 최댓값 (이 값이 +100에 매핑)
            invert: True면 스코어를 반전 (예: 달러 강세 = 주식 약세)

        Returns:
            -100.0 ~ +100.0 범위의 정규화 점수
        """
        if max_val == min_val:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val) * 200 - 100
        if invert:
            normalized = -normalized
        return max(-100.0, min(100.0, normalized))

    @staticmethod
    def classify_score(score: float) -> str:
        """점수를 시그널 문자열로 분류.

        Args:
            score: -100 ~ +100 점수

        Returns:
            "bullish" (>20), "bearish" (<-20), "neutral" (그 외)
        """
        if score > 20:
            return "bullish"
        elif score < -20:
            return "bearish"
        return "neutral"

    @staticmethod
    def _get_close(cache: Any, symbol: str) -> Optional["pd.Series"]:
        """캐시에서 종가 시리즈를 추출. 없으면 None."""
        if cache is None:
            return None
        df = cache.get(symbol)
        if df is None or (hasattr(df, 'empty') and df.empty):
            return None
        for col in ('close', 'Close', 'Adj Close'):
            if col in df.columns:
                series = df[col].dropna()
                return series if len(series) > 0 else None
        return None
