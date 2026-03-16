"""비결정성 검증 스크립트 단위 테스트."""

import json
from pathlib import Path

import pytest


class TestDeterminismVerifier:
    """DeterminismVerifier 단위 테스트"""

    @pytest.fixture
    def sample_json(self, tmp_path):
        """최소 구조의 시장 분석 JSON"""
        data = {
            "stocks": {
                "AAPL": {
                    "price": {
                        "last": 250.12,
                        "change_1d": -2.2,
                        "change_5d": -2.9,
                        "change_20d": -4.4,
                    },
                    "indicators": {
                        "rsi": {"value": 23.9, "signal": "oversold"},
                        "macd": {
                            "histogram": -1.5,
                            "signal": "bearish",
                            "cross_recent": False,
                        },
                        "bollinger": {"pct_b": 0.05},
                        "stochastic": {"k": 15.2, "d": 18.5},
                        "adx": {"value": 17.8, "trend": "down"},
                    },
                    "regime": {"state": "SIDEWAYS", "confidence": 0.64},
                },
                "MSFT": {
                    "price": {
                        "last": 395.55,
                        "change_1d": -1.1,
                        "change_5d": -3.3,
                        "change_20d": -1.6,
                    },
                    "indicators": {
                        "rsi": {"value": 35.2, "signal": "neutral"},
                        "macd": {
                            "histogram": 0.5,
                            "signal": "bullish",
                            "cross_recent": False,
                        },
                        "bollinger": {"pct_b": 0.3},
                        "stochastic": {"k": 25.0, "d": 30.0},
                        "adx": {"value": 22.9, "trend": "down"},
                    },
                    "regime": {"state": "SIDEWAYS", "confidence": 0.54},
                },
            },
            "market_summary": {
                "total_stocks": 2,
                "bullish_count": 0,
                "bearish_count": 0,
                "sideways_count": 2,
                "avg_rsi": 29.5,
                "market_sentiment": "Bearish",
                "notable_events": [],
            },
            "news": {"market_news": [], "stock_news": {}},
            "fear_greed_index": {
                "current": {"value": 20, "value_classification": "Extreme Fear"}
            },
        }
        json_path = tmp_path / "2026-03-16.json"
        json_path.write_text(json.dumps(data, ensure_ascii=False))
        return str(json_path)

    def test_verifier_basic(self, sample_json):
        """기본 검증 실행"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        result = verifier.run_comparison(sample_json, n_runs=3)

        assert result['n_runs'] == 3
        assert len(result['runs']) == 3
        assert 'top3_consistent' in result
        assert 'prompt_hashes_consistent' in result
        assert 'fact_sheet_consistent' in result

    def test_verifier_top3_consistent(self, sample_json):
        """TOP 3이 3회 모두 동일"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        result = verifier.run_comparison(sample_json, n_runs=3)

        assert result['top3_consistent'] is True
        # All runs should have same TOP 3
        first_top3 = result['runs'][0]['top3']
        for run in result['runs'][1:]:
            assert run['top3'] == first_top3

    def test_verifier_prompt_hash_consistent(self, sample_json):
        """프롬프트 해시가 3회 모두 동일"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        result = verifier.run_comparison(sample_json, n_runs=3)

        assert result['prompt_hashes_consistent'] is True

    def test_verifier_fact_sheet_consistent(self, sample_json):
        """팩트시트 해시가 3회 모두 동일"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        result = verifier.run_comparison(sample_json, n_runs=3)

        assert result['fact_sheet_consistent'] is True

    def test_verifier_summary_contains_pass(self, sample_json):
        """결과 요약에 PASS 포함"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        result = verifier.run_comparison(sample_json, n_runs=2)

        assert 'PASS' in result['summary']
        assert '결정론적' in result['summary']

    def test_find_latest_json(self):
        """최신 JSON 파일 찾기"""
        from scripts.verify_determinism import DeterminismVerifier

        verifier = DeterminismVerifier()
        # This depends on actual data/market_analysis/ directory
        result = verifier.find_latest_json()
        if result:
            assert result.endswith('.json')
