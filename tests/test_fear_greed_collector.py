"""
FearGreedCollector 단위 테스트

CNN Fear & Greed Index API를 Mock하여
데이터 수집 및 차트 생성을 검증합니다.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trading_bot.fear_greed_collector import FearGreedCollector, _classify_value


# ─── Fixtures ───


@pytest.fixture
def collector():
    return FearGreedCollector(timeout=5.0)


@pytest.fixture
def sample_api_response():
    """CNN API 응답 모의 데이터"""
    now_ts = int(datetime.now().timestamp() * 1000)
    day_ms = 86400 * 1000

    history_data = []
    for i in range(30):
        history_data.append({
            "x": now_ts - (i * day_ms),
            "y": 45.0 + (i % 10) - 5,
            "rating": "Fear" if (45.0 + (i % 10) - 5) < 45 else "Neutral",
        })

    return {
        "fear_and_greed": {
            "score": 42.5,
            "rating": "Fear",
            "timestamp": "2026-02-20T10:30:00+00:00",
        },
        "fear_and_greed_historical": {
            "data": history_data,
        },
    }


# ─── _classify_value 테스트 ───


class TestClassifyValue:
    def test_extreme_fear(self):
        assert _classify_value(10) == "Extreme Fear"
        assert _classify_value(0) == "Extreme Fear"
        assert _classify_value(24) == "Extreme Fear"

    def test_fear(self):
        assert _classify_value(25) == "Fear"
        assert _classify_value(35) == "Fear"
        assert _classify_value(44) == "Fear"

    def test_neutral(self):
        assert _classify_value(45) == "Neutral"
        assert _classify_value(50) == "Neutral"
        assert _classify_value(54) == "Neutral"

    def test_greed(self):
        assert _classify_value(55) == "Greed"
        assert _classify_value(65) == "Greed"
        assert _classify_value(74) == "Greed"

    def test_extreme_greed(self):
        assert _classify_value(75) == "Extreme Greed"
        assert _classify_value(90) == "Extreme Greed"
        assert _classify_value(100) == "Extreme Greed"


# ─── collect() 테스트 ───


class TestFearGreedCollect:
    @patch("trading_bot.fear_greed_collector.requests.get")
    def test_collect_success(self, mock_get, collector, sample_api_response):
        """정상 수집 시 올바른 데이터 구조 반환"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = collector.collect(limit=30)

        assert result is not None
        assert "current" in result
        assert "history" in result
        assert result["current"]["value"] == 42.5
        assert result["current"]["classification"] == "Fear"
        assert len(result["history"]) <= 30

    @patch("trading_bot.fear_greed_collector.requests.get")
    def test_collect_api_failure_returns_none(self, mock_get, collector):
        """API 호출 실패 시 None 반환"""
        import requests
        mock_get.side_effect = requests.RequestException("Connection timeout")

        result = collector.collect()

        assert result is None

    @patch("trading_bot.fear_greed_collector.requests.get")
    def test_collect_invalid_json_returns_none(self, mock_get, collector):
        """잘못된 JSON 응답 시 None 반환"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        result = collector.collect()

        assert result is None

    @patch("trading_bot.fear_greed_collector.requests.get")
    def test_collect_http_error_returns_none(self, mock_get, collector):
        """HTTP 에러 시 None 반환"""
        import requests
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        result = collector.collect()

        assert result is None

    @patch("trading_bot.fear_greed_collector.requests.get")
    def test_collect_respects_limit(self, mock_get, collector, sample_api_response):
        """limit 파라미터가 히스토리 수를 제한"""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_api_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = collector.collect(limit=5)

        assert result is not None
        assert len(result["history"]) <= 5


# ─── _parse_response() 테스트 ───


class TestParseResponse:
    def test_parse_current_value(self, collector, sample_api_response):
        """현재 값 파싱"""
        result = collector._parse_response(sample_api_response, limit=30)

        assert result is not None
        assert result["current"]["value"] == 42.5
        assert result["current"]["classification"] == "Fear"

    def test_parse_history(self, collector, sample_api_response):
        """히스토리 파싱"""
        result = collector._parse_response(sample_api_response, limit=30)

        assert result is not None
        assert isinstance(result["history"], list)
        assert len(result["history"]) > 0
        # 히스토리 항목 구조 확인
        item = result["history"][0]
        assert "date" in item
        assert "value" in item
        assert "classification" in item

    def test_parse_empty_response(self, collector):
        """빈 응답 파싱"""
        result = collector._parse_response({}, limit=30)

        assert result is not None
        assert result["current"]["value"] == 0.0
        assert result["history"] == []

    def test_parse_missing_historical(self, collector):
        """히스토리 없는 응답"""
        raw = {
            "fear_and_greed": {
                "score": 55.0,
                "rating": "Greed",
                "timestamp": "2026-02-20T10:00:00",
            }
        }
        result = collector._parse_response(raw, limit=30)

        assert result is not None
        assert result["current"]["value"] == 55.0
        assert result["history"] == []

    def test_parse_history_sorted_recent_first(self, collector, sample_api_response):
        """히스토리가 최신순 정렬인지 확인"""
        result = collector._parse_response(sample_api_response, limit=30)

        if len(result["history"]) >= 2:
            dates = [h["date"] for h in result["history"]]
            assert dates == sorted(dates, reverse=True)


# ─── generate_chart() 테스트 ───


class TestGenerateChart:
    def test_generate_chart_creates_png(self, collector):
        """차트 PNG 파일 생성 확인"""
        data = {
            "current": {"value": 42.5, "classification": "Fear", "timestamp": "2026-02-20T10:30:00"},
            "history": [
                {"date": f"2026-02-{20 - i:02d}", "value": 40 + i, "classification": "Fear"}
                for i in range(15)
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            chart_path = collector.generate_chart(data, output_dir=tmpdir)

            assert chart_path is not None
            assert Path(chart_path).exists()
            assert chart_path.endswith(".png")

    def test_generate_chart_with_empty_history(self, collector):
        """히스토리 없이도 차트 생성"""
        data = {
            "current": {"value": 50.0, "classification": "Neutral", "timestamp": "2026-02-20T10:00:00"},
            "history": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            chart_path = collector.generate_chart(data, output_dir=tmpdir)

            assert chart_path is not None
            assert Path(chart_path).exists()

    def test_generate_chart_creates_output_directory(self, collector):
        """출력 디렉토리 자동 생성 확인"""
        data = {
            "current": {"value": 60.0, "classification": "Greed", "timestamp": "2026-02-20T10:00:00"},
            "history": [
                {"date": "2026-02-20", "value": 60.0, "classification": "Greed"},
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "sub", "charts")
            chart_path = collector.generate_chart(data, output_dir=nested_dir)

            assert chart_path is not None
            assert Path(nested_dir).exists()

    def test_generate_chart_various_values(self, collector):
        """다양한 F&G 값에서 차트 생성"""
        for value, classification in [(5, "Extreme Fear"), (35, "Fear"), (50, "Neutral"),
                                       (65, "Greed"), (90, "Extreme Greed")]:
            data = {
                "current": {"value": value, "classification": classification, "timestamp": "2026-02-20T10:00:00"},
                "history": [
                    {"date": f"2026-02-{20 - i:02d}", "value": value + i - 5, "classification": classification}
                    for i in range(10)
                ],
            }

            with tempfile.TemporaryDirectory() as tmpdir:
                chart_path = collector.generate_chart(data, output_dir=tmpdir)
                assert chart_path is not None
