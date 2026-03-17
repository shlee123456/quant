"""
MarketAnalysisPrompt 단위 테스트

build_analysis_prompt 및 헬퍼 함수 테스트
"""

import json
import os
import tempfile
import pytest

from trading_bot.market_analysis_prompt import (
    build_analysis_prompt,
    get_notion_page_id,
    _load_session_reports,
    _build_session_data_block,
    _build_trend_data_block,
    _build_scorecard_data_block,
    DEFAULT_NOTION_PAGE_ID,
)


@pytest.fixture
def sample_market_data():
    """테스트용 시장 분석 JSON 데이터"""
    return {
        "date": "2026-02-22",
        "symbols": ["AAPL", "MSFT"],
        "stocks": {
            "AAPL": {
                "current_price": 150.0,
                "rsi": 45.0,
                "macd_signal": "bullish",
            },
            "MSFT": {
                "current_price": 400.0,
                "rsi": 65.0,
                "macd_signal": "bearish",
            },
        },
    }


@pytest.fixture
def sample_market_json(sample_market_data, tmp_path):
    """테스트용 JSON 파일 생성"""
    json_file = tmp_path / "market_data.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(sample_market_data, f, ensure_ascii=False)
    return str(json_file)


@pytest.fixture
def sample_market_json_with_news(tmp_path):
    """뉴스 데이터 포함 JSON 파일"""
    data = {
        "date": "2026-02-22",
        "symbols": ["AAPL"],
        "stocks": {"AAPL": {"current_price": 150.0}},
        "news": {
            "market_news": [
                {"title": "Fed holds rates steady", "source": "Reuters"},
            ],
            "stock_news": {
                "AAPL": [
                    {"title": "Apple launches new product", "source": "Bloomberg"},
                ]
            },
        },
        "fear_greed_index": {
            "current": {
                "value": 35,
                "classification": "Fear",
                "timestamp": "2026-02-22T10:00:00",
            },
            "history": [
                {"date": "2026-02-21", "value": 40, "classification": "Fear"},
                {"date": "2026-02-20", "value": 42, "classification": "Fear"},
            ],
            "chart_path": "/tmp/chart.png",
        },
    }
    json_file = tmp_path / "market_with_news.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return str(json_file)


class TestGetNotionPageId:
    """get_notion_page_id 테스트"""

    def test_returns_default(self):
        """기본값 반환"""
        with patch_env({}):
            result = get_notion_page_id()
        assert result == DEFAULT_NOTION_PAGE_ID

    def test_returns_env_override(self):
        """환경 변수 오버라이드"""
        with patch_env({"NOTION_MARKET_ANALYSIS_PAGE_ID": "custom-id-123"}):
            result = get_notion_page_id()
        assert result == "custom-id-123"


class TestLoadSessionReports:
    """_load_session_reports 테스트"""

    def test_empty_directory(self, tmp_path):
        """빈 디렉토리"""
        result = _load_session_reports(str(tmp_path))
        assert result == []

    def test_loads_valid_report(self, tmp_path):
        """유효한 리포트 로드"""
        report = {
            "session_id": "test_session_1",
            "summary": {
                "strategy_name": "RSI_14",
                "initial_capital": 10000,
                "final_capital": 10500,
                "total_return": 5.0,
                "sharpe_ratio": 1.5,
                "max_drawdown": -3.0,
                "win_rate": 60.0,
                "status": "completed",
            },
            "trades": [{"type": "BUY"}, {"type": "SELL"}],
            "start_time": "2026-02-22T10:00:00",
            "end_time": "2026-02-22T16:00:00",
        }
        report_file = tmp_path / "session1_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f)

        result = _load_session_reports(str(tmp_path))
        assert len(result) == 1
        assert result[0]["session_id"] == "test_session_1"
        assert result[0]["total_trades"] == 2

    def test_skips_invalid_json(self, tmp_path):
        """잘못된 JSON은 건너뜀"""
        bad_file = tmp_path / "bad_report.json"
        bad_file.write_text("not valid json {{{")

        result = _load_session_reports(str(tmp_path))
        assert result == []


class TestBuildSessionDataBlock:
    """_build_session_data_block 테스트"""

    def test_empty_sessions(self):
        """세션 없을 때 빈 문자열"""
        assert _build_session_data_block([]) == ""

    def test_with_sessions(self):
        """세션 데이터 블록 생성"""
        sessions = [
            {
                "session_id": "s1",
                "strategy_name": "RSI",
                "display_name": "RSI | AAPL",
                "initial_capital": 10000,
                "final_capital": 10500,
                "total_return": 5.0,
                "sharpe_ratio": 1.5,
                "max_drawdown": -3.0,
                "win_rate": 60.0,
                "total_trades": 10,
                "start_time": "2026-02-22T10:00:00",
                "end_time": "2026-02-22T16:00:00",
                "status": "completed",
            }
        ]
        result = _build_session_data_block(sessions)
        assert "트레이딩 세션 데이터" in result
        assert "RSI | AAPL" in result
        assert "+5.0%" in result

    def test_negative_return_format(self):
        """음수 수익률 포맷"""
        sessions = [
            {
                "session_id": "s1",
                "strategy_name": "RSI",
                "display_name": "RSI",
                "initial_capital": 10000,
                "final_capital": 9500,
                "total_return": -5.0,
                "sharpe_ratio": None,
                "max_drawdown": -10.0,
                "win_rate": None,
                "total_trades": 5,
                "start_time": "T1",
                "end_time": "T2",
                "status": "completed",
            }
        ]
        result = _build_session_data_block(sessions)
        assert "-5.0%" in result
        assert "N/A" in result  # None values


class TestBuildAnalysisPrompt:
    """build_analysis_prompt 테스트"""

    def test_basic_prompt_generation(self, sample_market_json):
        """기본 프롬프트 생성"""
        prompt = build_analysis_prompt(sample_market_json)

        assert "AAPL" in prompt
        assert "MSFT" in prompt
        assert "Notion" in prompt
        assert "notion-create-pages" in prompt

    def test_prompt_contains_json_data(self, sample_market_json):
        """프롬프트에 JSON 데이터 포함"""
        prompt = build_analysis_prompt(sample_market_json)
        assert "```json" in prompt
        assert "150.0" in prompt

    def test_prompt_with_news_data(self, sample_market_json_with_news):
        """뉴스 데이터 포함 프롬프트"""
        prompt = build_analysis_prompt(sample_market_json_with_news)
        assert "Fed holds rates steady" in prompt
        assert "Apple launches new product" in prompt

    def test_prompt_with_fear_greed(self, sample_market_json_with_news):
        """공포탐욕 지수 포함"""
        prompt = build_analysis_prompt(sample_market_json_with_news)
        assert "Fear & Greed" in prompt or "공포/탐욕" in prompt
        assert "35" in prompt

    def test_prompt_with_session_reports(self, sample_market_json, tmp_path):
        """세션 리포트 포함"""
        # 세션 리포트 생성
        session_dir = tmp_path / "sessions"
        session_dir.mkdir()
        report = {
            "session_id": "s1",
            "summary": {
                "strategy_name": "RSI",
                "initial_capital": 10000,
                "final_capital": 10500,
                "total_return": 5.0,
                "status": "completed",
            },
            "trades": [],
            "start_time": "T1",
            "end_time": "T2",
        }
        with open(session_dir / "s1_report.json", "w") as f:
            json.dump(report, f)

        prompt = build_analysis_prompt(sample_market_json, str(session_dir))
        assert "트레이딩 세션 데이터" in prompt

    def test_prompt_without_session_reports(self, sample_market_json):
        """세션 리포트 없을 때"""
        prompt = build_analysis_prompt(sample_market_json)
        # 세션 섹션 없으면 리스크가 7번
        assert "# 7" in prompt or "리스크" in prompt

    def test_nonexistent_json_raises(self):
        """존재하지 않는 파일"""
        with pytest.raises(FileNotFoundError):
            build_analysis_prompt("/nonexistent/file.json")

    def test_invalid_json_raises(self, tmp_path):
        """잘못된 JSON 파일"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            build_analysis_prompt(str(bad_file))

    def test_notion_format_template_in_prompt(self, sample_market_json):
        """Notion 포맷 템플릿 포함 확인"""
        prompt = build_analysis_prompt(sample_market_json)
        assert "NOTION ENHANCED MARKDOWN" in prompt
        assert "table_of_contents" in prompt


class TestBuildTrendDataBlock:
    """_build_trend_data_block 테스트"""

    def test_build_trend_data_block(self):
        """정상 트렌드 데이터로 블록 생성"""
        trend_data = {
            'period': {'start': '2026-03-11', 'end': '2026-03-17', 'days': 6},
            'fear_greed_trend': {
                'values': [
                    {'date': '2026-03-11', 'value': 20.0, 'classification': 'Extreme Fear'},
                    {'date': '2026-03-17', 'value': 27.2, 'classification': 'Fear'},
                ],
                'direction': 'improving',
                'change': 7.2,
            },
            'symbol_trends': {
                'AAPL': {
                    'prices': [
                        {'date': '2026-03-11', 'price': 150.0},
                        {'date': '2026-03-17', 'price': 155.0},
                    ],
                    'price_change_pct': 3.33,
                    'rsi_values': [
                        {'date': '2026-03-11', 'rsi': 40.0},
                        {'date': '2026-03-17', 'rsi': 50.0},
                    ],
                    'rsi_trend': 'rising',
                    'regime_transitions': [
                        {'date': '2026-03-14', 'from': 'VOLATILE', 'to': 'SIDEWAYS'},
                    ],
                    'current_regime': 'SIDEWAYS',
                },
            },
            'regime_summary': {
                'transitions_count': 1,
                'notable_transitions': ['AAPL: VOLATILE→SIDEWAYS (03-14)'],
            },
            'intelligence_trend': {
                'scores': [
                    {'date': '2026-03-11', 'score': -0.5, 'signal': 'neutral'},
                    {'date': '2026-03-17', 'score': -0.3, 'signal': 'neutral'},
                ],
                'direction': 'stable',
            },
            'summary_text': '분석 기간: 2026-03-11 ~ 2026-03-17 (6일간)',
        }

        result = _build_trend_data_block(trend_data)

        assert "멀티데이 트렌드 분석" in result
        assert "2026-03-11" in result
        assert "2026-03-17" in result
        assert "F&G 추세" in result
        assert "개선" in result
        assert "레짐 전환" in result
        assert "AAPL" in result
        assert "Intelligence 추세" in result

    def test_build_trend_data_block_empty(self):
        """빈 데이터에서 빈 문자열 반환"""
        assert _build_trend_data_block({}) == ""
        assert _build_trend_data_block(None) == ""

    def test_build_trend_data_block_no_period(self):
        """period가 비어있을 때 빈 문자열 반환"""
        trend_data = {
            'period': {'start': None, 'end': None, 'days': 0},
            'fear_greed_trend': {'values': [], 'direction': 'stable', 'change': 0.0},
            'symbol_trends': {},
            'regime_summary': {'transitions_count': 0, 'notable_transitions': []},
            'intelligence_trend': {'scores': [], 'direction': 'stable'},
            'summary_text': '분석 데이터가 없습니다.',
        }
        assert _build_trend_data_block(trend_data) == ""


class TestBuildScorecardDataBlock:
    """_build_scorecard_data_block 테스트"""

    def test_build_scorecard_data_block(self):
        """충분한 데이터가 있을 때 상세 성적표 반환"""
        scorecard = {
            'date': '2026-03-17',
            'lookback_days': 30,
            'data_coverage': {
                'total_signals': 95,
                'with_outcomes': 15,
                'coverage_pct': 15.8,
                'sufficient': True,
            },
            'overall_accuracy_pct': 60.0,
            'by_fear_greed_zone': {
                '0-25': {'total': 10, 'correct': 7, 'accuracy_pct': 70.0, 'avg_return_5d': 1.5},
                '25-50': {'total': 5, 'correct': 2, 'accuracy_pct': 40.0, 'avg_return_5d': -0.5},
                '50-75': {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None},
                '75-100': {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None},
            },
            'by_signal_type': {
                'strong_bullish': {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None},
                'bullish': {'total': 3, 'correct': 2, 'accuracy_pct': 66.7, 'avg_return_5d': 2.0},
                'neutral': {'total': 12, 'correct': 7, 'accuracy_pct': 58.3, 'avg_return_5d': 0.5},
                'bearish': {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None},
                'strong_bearish': {'total': 0, 'correct': 0, 'accuracy_pct': None, 'avg_return_5d': None},
            },
            'by_symbol': {
                'AAPL': {'total': 5, 'correct': 4, 'accuracy_pct': 80.0, 'avg_return_5d': 2.0},
                'MSFT': {'total': 5, 'correct': 2, 'accuracy_pct': 40.0, 'avg_return_5d': -1.0},
                'NVDA': {'total': 5, 'correct': 3, 'accuracy_pct': 60.0, 'avg_return_5d': 0.5},
            },
            'best_conditions': 'F&G 0-25구간 70.0% (10건)',
            'worst_conditions': 'F&G 25-50구간 40.0% (5건)',
        }

        result = _build_scorecard_data_block(scorecard)

        assert "시그널 성적표" in result
        assert "15/95건 채점 완료" in result
        assert "전체 적중률" in result
        assert "60.0%" in result
        assert "F&G 구간별 적중률" in result
        assert "시그널별 적중률" in result
        assert "적중률 상위" in result
        assert "AAPL" in result

    def test_build_scorecard_data_block_empty(self):
        """빈 데이터에서 빈 문자열 반환"""
        assert _build_scorecard_data_block({}) == ""
        assert _build_scorecard_data_block(None) == ""

    def test_build_scorecard_data_block_insufficient(self):
        """데이터 부족 시 간단 메시지 반환"""
        scorecard = {
            'date': '2026-03-17',
            'lookback_days': 30,
            'data_coverage': {
                'total_signals': 95,
                'with_outcomes': 3,
                'coverage_pct': 3.2,
                'sufficient': False,
            },
            'overall_accuracy_pct': None,
            'by_fear_greed_zone': {},
            'by_signal_type': {},
            'by_symbol': {},
            'best_conditions': None,
            'worst_conditions': None,
        }

        result = _build_scorecard_data_block(scorecard)

        assert "시그널 성적표" in result
        assert "데이터 축적 중" in result
        assert "3/최소10건" in result
        # 상세 정보는 없어야 함
        assert "F&G 구간별" not in result

    def test_build_scorecard_data_block_zero_total(self):
        """total_signals가 0이면 빈 문자열 반환"""
        scorecard = {
            'data_coverage': {
                'total_signals': 0,
                'with_outcomes': 0,
                'coverage_pct': 0.0,
                'sufficient': False,
            },
        }

        result = _build_scorecard_data_block(scorecard)
        assert result == ""


class TestBuildAnalysisPromptWithTrendScorecard:
    """build_analysis_prompt에 trend/scorecard 데이터 포함 테스트"""

    def test_build_analysis_prompt_with_trend(self, tmp_path):
        """trend 데이터가 있을 때 프롬프트에 포함"""
        data = {
            "date": "2026-03-17",
            "symbols": ["AAPL"],
            "stocks": {"AAPL": {"current_price": 150.0}},
            "trend": {
                "period": {"start": "2026-03-11", "end": "2026-03-17", "days": 6},
                "fear_greed_trend": {
                    "values": [
                        {"date": "2026-03-11", "value": 20.0, "classification": "Fear"},
                        {"date": "2026-03-17", "value": 27.0, "classification": "Fear"},
                    ],
                    "direction": "improving",
                    "change": 7.0,
                },
                "symbol_trends": {},
                "regime_summary": {"transitions_count": 0, "notable_transitions": []},
                "intelligence_trend": {"scores": [], "direction": "stable"},
                "summary_text": "테스트 요약",
            },
        }

        json_file = tmp_path / "trend_test.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        prompt = build_analysis_prompt(str(json_file))
        assert "멀티데이 트렌드 분석" in prompt
        assert "F&G 추세" in prompt

    def test_build_analysis_prompt_with_scorecard(self, tmp_path):
        """scorecard 데이터가 있을 때 프롬프트에 포함"""
        data = {
            "date": "2026-03-17",
            "symbols": ["AAPL"],
            "stocks": {"AAPL": {"current_price": 150.0}},
            "scorecard": {
                "date": "2026-03-17",
                "lookback_days": 30,
                "data_coverage": {
                    "total_signals": 50,
                    "with_outcomes": 3,
                    "coverage_pct": 6.0,
                    "sufficient": False,
                },
                "overall_accuracy_pct": None,
                "by_fear_greed_zone": {},
                "by_signal_type": {},
                "by_symbol": {},
                "best_conditions": None,
                "worst_conditions": None,
            },
        }

        json_file = tmp_path / "scorecard_test.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        prompt = build_analysis_prompt(str(json_file))
        assert "시그널 성적표" in prompt
        assert "데이터 축적 중" in prompt

    def test_build_analysis_prompt_without_trend_scorecard(self, tmp_path):
        """trend/scorecard 없을 때 기존 동작 유지"""
        data = {
            "date": "2026-03-17",
            "symbols": ["AAPL"],
            "stocks": {"AAPL": {"current_price": 150.0}},
        }

        json_file = tmp_path / "no_trend_test.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        prompt = build_analysis_prompt(str(json_file))
        # 기존 동작과 동일해야 함
        assert "AAPL" in prompt
        assert "멀티데이 트렌드 분석" not in prompt
        assert "시그널 성적표" not in prompt

    def test_trend_scorecard_excluded_from_json_dump(self, tmp_path):
        """trend/scorecard가 JSON 덤프에서 제외됨"""
        data = {
            "date": "2026-03-17",
            "symbols": ["AAPL"],
            "stocks": {"AAPL": {"current_price": 150.0}},
            "trend": {"period": {"start": "2026-03-11", "end": "2026-03-17", "days": 6}},
            "scorecard": {"data_coverage": {"total_signals": 0, "with_outcomes": 0, "coverage_pct": 0, "sufficient": False}},
        }

        json_file = tmp_path / "exclude_test.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        prompt = build_analysis_prompt(str(json_file))
        # JSON 블록 내부에는 trend/scorecard가 없어야 함
        json_block_start = prompt.find("```json")
        json_block_end = prompt.find("```", json_block_start + 7)
        json_block = prompt[json_block_start:json_block_end]
        assert '"trend"' not in json_block
        assert '"scorecard"' not in json_block


# --- Helper ---

class patch_env:
    """환경 변수 임시 패치 컨텍스트 매니저"""

    def __init__(self, env_vars):
        self.env_vars = env_vars
        self._original = {}

    def __enter__(self):
        for key in self.env_vars:
            self._original[key] = os.environ.get(key)
            os.environ[key] = self.env_vars[key]
        # Clear vars not in env_vars if they exist
        if "NOTION_MARKET_ANALYSIS_PAGE_ID" not in self.env_vars:
            self._original.setdefault("NOTION_MARKET_ANALYSIS_PAGE_ID",
                                       os.environ.get("NOTION_MARKET_ANALYSIS_PAGE_ID"))
            os.environ.pop("NOTION_MARKET_ANALYSIS_PAGE_ID", None)
        return self

    def __exit__(self, *args):
        for key, val in self._original.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
