"""
Tests for base_layer.py - LayerResult, normalize_score, classify_score.
"""

import pytest

from trading_bot.market_intelligence.base_layer import (
    BaseIntelligenceLayer,
    LayerResult,
)


# ─── LayerResult tests ───


class TestLayerResult:
    """LayerResult 데이터 클래스 테스트."""

    def test_basic_creation(self):
        """기본 생성 테스트."""
        result = LayerResult(
            layer_name="test_layer",
            score=42.5,
            signal="bullish",
            confidence=0.85,
        )
        assert result.layer_name == "test_layer"
        assert result.score == 42.5
        assert result.signal == "bullish"
        assert result.confidence == 0.85
        assert result.metrics == {}
        assert result.interpretation == ""
        assert result.details == {}

    def test_full_creation(self):
        """모든 필드 지정 생성 테스트."""
        result = LayerResult(
            layer_name="macro",
            score=-30.0,
            signal="bearish",
            confidence=0.7,
            metrics={"vix": 25.0},
            interpretation="시장 약세",
            details={"phase": "contraction"},
        )
        assert result.metrics == {"vix": 25.0}
        assert result.interpretation == "시장 약세"
        assert result.details == {"phase": "contraction"}

    def test_to_dict(self):
        """to_dict() 직렬화 테스트."""
        result = LayerResult(
            layer_name="test",
            score=55.555,
            signal="bullish",
            confidence=0.8888,
            metrics={"a": 1},
            interpretation="강세",
            details={"b": 2},
        )
        d = result.to_dict()

        assert d['layer'] == "test"
        assert d['score'] == 55.6  # round(55.555, 1)
        assert d['signal'] == "bullish"
        assert d['confidence'] == 0.89  # round(0.8888, 2)
        assert d['metrics'] == {"a": 1}
        assert d['interpretation'] == "강세"
        assert d['details'] == {"b": 2}

    def test_to_dict_keys(self):
        """to_dict() 반환 키 확인."""
        result = LayerResult(
            layer_name="x",
            score=0.0,
            signal="neutral",
            confidence=0.0,
        )
        d = result.to_dict()
        expected_keys = {'layer', 'score', 'signal', 'confidence',
                         'metrics', 'interpretation', 'details'}
        assert set(d.keys()) == expected_keys


# ─── normalize_score tests ───


class TestNormalizeScore:
    """normalize_score() 정적 메서드 테스트."""

    def test_min_value_returns_minus_100(self):
        """최솟값 입력 시 -100 반환."""
        score = BaseIntelligenceLayer.normalize_score(0, 0, 100)
        assert score == -100.0

    def test_max_value_returns_plus_100(self):
        """최댓값 입력 시 +100 반환."""
        score = BaseIntelligenceLayer.normalize_score(100, 0, 100)
        assert score == 100.0

    def test_midpoint_returns_zero(self):
        """중간값 입력 시 0 반환."""
        score = BaseIntelligenceLayer.normalize_score(50, 0, 100)
        assert score == 0.0

    def test_equal_min_max_returns_zero(self):
        """min == max일 때 0 반환."""
        score = BaseIntelligenceLayer.normalize_score(50, 50, 50)
        assert score == 0.0

    def test_invert(self):
        """invert=True일 때 부호 반전."""
        normal = BaseIntelligenceLayer.normalize_score(75, 0, 100)
        inverted = BaseIntelligenceLayer.normalize_score(75, 0, 100, invert=True)
        assert inverted == -normal

    def test_clamp_above_100(self):
        """값이 범위를 초과해도 100으로 클램프."""
        score = BaseIntelligenceLayer.normalize_score(200, 0, 100)
        assert score == 100.0

    def test_clamp_below_minus_100(self):
        """값이 범위 미만이어도 -100으로 클램프."""
        score = BaseIntelligenceLayer.normalize_score(-50, 0, 100)
        assert score == -100.0

    def test_negative_range(self):
        """음수 범위에서도 정상 작동."""
        score = BaseIntelligenceLayer.normalize_score(-50, -100, 0)
        assert score == 0.0

    def test_quarter_point(self):
        """1/4 지점 테스트."""
        score = BaseIntelligenceLayer.normalize_score(25, 0, 100)
        assert score == -50.0


# ─── classify_score tests ───


class TestClassifyScore:
    """classify_score() 정적 메서드 테스트."""

    def test_bullish(self):
        """점수 > 20이면 bullish."""
        assert BaseIntelligenceLayer.classify_score(21) == "bullish"
        assert BaseIntelligenceLayer.classify_score(100) == "bullish"

    def test_bearish(self):
        """점수 < -20이면 bearish."""
        assert BaseIntelligenceLayer.classify_score(-21) == "bearish"
        assert BaseIntelligenceLayer.classify_score(-100) == "bearish"

    def test_neutral(self):
        """점수가 -20 ~ 20이면 neutral."""
        assert BaseIntelligenceLayer.classify_score(0) == "neutral"
        assert BaseIntelligenceLayer.classify_score(20) == "neutral"
        assert BaseIntelligenceLayer.classify_score(-20) == "neutral"
        assert BaseIntelligenceLayer.classify_score(15) == "neutral"
        assert BaseIntelligenceLayer.classify_score(-15) == "neutral"

    def test_boundary_values(self):
        """경계값 테스트."""
        assert BaseIntelligenceLayer.classify_score(20.0) == "neutral"
        assert BaseIntelligenceLayer.classify_score(20.001) == "bullish"
        assert BaseIntelligenceLayer.classify_score(-20.0) == "neutral"
        assert BaseIntelligenceLayer.classify_score(-20.001) == "bearish"


# ─── Abstract class tests ───


class TestBaseIntelligenceLayerAbstract:
    """BaseIntelligenceLayer 추상 클래스 테스트."""

    def test_cannot_instantiate_directly(self):
        """직접 인스턴스화 불가."""
        with pytest.raises(TypeError):
            BaseIntelligenceLayer("test")

    def test_concrete_subclass(self):
        """구체 서브클래스 인스턴스화 가능."""
        class ConcreteLayer(BaseIntelligenceLayer):
            def analyze(self, data):
                return LayerResult(
                    layer_name=self.name,
                    score=0.0,
                    signal="neutral",
                    confidence=0.5,
                )

        layer = ConcreteLayer("test_concrete")
        assert layer.name == "test_concrete"
        assert layer.logger is not None

    def test_subclass_analyze_returns_result(self):
        """서브클래스 analyze()가 LayerResult 반환."""
        class ConcreteLayer(BaseIntelligenceLayer):
            def analyze(self, data):
                return LayerResult(
                    layer_name=self.name,
                    score=50.0,
                    signal="bullish",
                    confidence=0.9,
                )

        layer = ConcreteLayer("test")
        result = layer.analyze({})
        assert isinstance(result, LayerResult)
        assert result.score == 50.0
