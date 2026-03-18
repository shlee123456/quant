"""가중치 저장/로드 테스트."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from trading_bot.weight_optimizer import (
    OptimizationResult,
    save_weights,
    load_weights,
    WEIGHTS_PATH,
)


@pytest.fixture
def tmp_weights_path(tmp_path):
    """임시 경로로 WEIGHTS_PATH를 교체."""
    fake_path = tmp_path / "optimized_weights.json"
    with patch("trading_bot.weight_optimizer.WEIGHTS_PATH", fake_path):
        yield fake_path


class TestWeightPersistence:
    def test_save_and_load(self, tmp_weights_path):
        """저장 후 로드 시 동일한 가중치."""
        result = OptimizationResult(
            optimal_weights={"macro_regime": 0.25, "sentiment": 0.75},
            is_improvement=True,
            oos_ic=0.15,
            current_ic=0.10,
            improvement_pct=50.0,
            stability_score=0.8,
            recommendation="적용 권장",
        )
        save_weights(result)
        loaded = load_weights()
        assert loaded == {"macro_regime": 0.25, "sentiment": 0.75}

    def test_load_nonexistent(self, tmp_weights_path):
        """파일 없으면 None."""
        assert load_weights() is None

    def test_load_not_improvement(self, tmp_weights_path):
        """is_improvement=False면 None."""
        result = OptimizationResult(
            optimal_weights={"macro_regime": 0.5, "sentiment": 0.5},
            is_improvement=False,
        )
        save_weights(result)
        assert load_weights() is None

    def test_load_corrupted_json(self, tmp_weights_path):
        """손상된 JSON이면 None."""
        tmp_weights_path.write_text("not valid json{{{")
        assert load_weights() is None
