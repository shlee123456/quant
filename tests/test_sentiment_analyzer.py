"""FinBERT SentimentAnalyzer 테스트 (모든 테스트는 mock 사용, 실제 모델 로드 없음)"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from trading_bot.sentiment_analyzer import SentimentAnalyzer


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singleton():
    """매 테스트마다 싱글턴 리셋"""
    SentimentAnalyzer.reset_instance()
    yield
    SentimentAnalyzer.reset_instance()


def _make_analyzer_with_mock_pipeline(pipeline_return_value):
    """Mock pipeline이 설정된 SentimentAnalyzer 인스턴스 생성"""
    sa = SentimentAnalyzer()
    sa._pipeline = MagicMock()
    sa._pipeline.return_value = pipeline_return_value
    return sa


# ──────────────────────────────────────────────────────────────────────
# SentimentAnalyzer 단위 테스트
# ──────────────────────────────────────────────────────────────────────

class TestAnalyzeHeadlines:
    """analyze_headlines 메서드 테스트"""

    def test_empty_news_data(self):
        """빈 뉴스 데이터 처리"""
        sa = SentimentAnalyzer()
        score, details = sa.analyze_headlines([])
        assert score == 0.0
        assert details['method'] == 'finbert'
        assert details['total_headlines'] == 0
        assert details['tone'] == 'no_data'

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_news_data_without_titles(self, mock_load):
        """title이 없는 뉴스 데이터 처리 (title 없으면 빈 headlines -> no_data)"""
        sa = SentimentAnalyzer()
        sa._pipeline = MagicMock()  # pipeline 세팅해도 headlines가 비어 있어 호출 안 됨
        score, details = sa.analyze_headlines([{'source': 'test'}, {'url': 'http://x'}])
        assert score == 0.0
        assert details['tone'] == 'no_data'

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_all_positive(self, mock_load):
        """모든 헤드라인이 긍정일 때"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'positive', 'score': 0.95},
            {'label': 'positive', 'score': 0.88},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'Stock surges on earnings'},
            {'title': 'Market rally continues'},
        ])
        assert score > 0
        assert details['positive_count'] == 2
        assert details['negative_count'] == 0
        assert details['neutral_count'] == 0
        assert details['total_headlines'] == 2
        assert details['method'] == 'finbert'
        assert len(details['headline_scores']) == 2

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_all_negative(self, mock_load):
        """모든 헤드라인이 부정일 때"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'negative', 'score': 0.92},
            {'label': 'negative', 'score': 0.85},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'Market crashes on fears'},
            {'title': 'Stocks plunge after report'},
        ])
        assert score < 0
        assert details['positive_count'] == 0
        assert details['negative_count'] == 2
        assert details['tone'] == 'negative'

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_mixed_sentiment(self, mock_load):
        """혼합 감성 결과"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'positive', 'score': 0.90},
            {'label': 'negative', 'score': 0.80},
            {'label': 'neutral', 'score': 0.75},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'Good earnings'},
            {'title': 'Bad outlook'},
            {'title': 'Market update'},
        ])
        assert details['positive_count'] == 1
        assert details['negative_count'] == 1
        assert details['neutral_count'] == 1
        assert details['total_headlines'] == 3
        assert details['tone'] == 'mixed'

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_all_neutral(self, mock_load):
        """모든 헤드라인이 중립일 때"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'neutral', 'score': 0.70},
            {'label': 'neutral', 'score': 0.65},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'Company releases report'},
            {'title': 'Quarterly update'},
        ])
        assert score == 0.0
        assert details['positive_count'] == 0
        assert details['negative_count'] == 0
        assert details['neutral_count'] == 2
        assert details['tone'] == 'neutral'

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_score_clamped_to_range(self, mock_load):
        """점수가 -100 ~ +100 범위 내에 있는지 확인"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'positive', 'score': 0.99},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'Incredible surge'},
        ])
        assert -100 <= score <= 100

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_strongly_positive_tone(self, mock_load):
        """강한 긍정 톤 분류 (score > 30)"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'positive', 'score': 0.95},
            {'label': 'positive', 'score': 0.90},
            {'label': 'positive', 'score': 0.88},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'a'}, {'title': 'b'}, {'title': 'c'},
        ])
        assert details['tone'] == 'positive'
        assert score > 30

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_strongly_negative_tone(self, mock_load):
        """강한 부정 톤 분류 (score < -30)"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'negative', 'score': 0.95},
            {'label': 'negative', 'score': 0.90},
            {'label': 'negative', 'score': 0.88},
        ])
        score, details = sa.analyze_headlines([
            {'title': 'x'}, {'title': 'y'}, {'title': 'z'},
        ])
        assert details['tone'] == 'negative'
        assert score < -30

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_headline_title_truncated(self, mock_load):
        """헤드라인 제목이 100자로 잘리는지 확인"""
        long_title = 'A' * 200
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'neutral', 'score': 0.60},
        ])
        score, details = sa.analyze_headlines([{'title': long_title}])
        assert len(details['headline_scores'][0]['title']) == 100

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_empty_title_filtered(self, mock_load):
        """빈 title은 필터링됨"""
        sa = _make_analyzer_with_mock_pipeline([
            {'label': 'positive', 'score': 0.90},
        ])
        score, details = sa.analyze_headlines([
            {'title': ''},
            {'title': 'Real headline'},
        ])
        assert details['total_headlines'] == 1


class TestSingleton:
    """싱글턴 패턴 테스트"""

    def test_get_instance_returns_same(self):
        """get_instance()가 동일 인스턴스를 반환"""
        a = SentimentAnalyzer.get_instance()
        b = SentimentAnalyzer.get_instance()
        assert a is b

    def test_reset_instance(self):
        """reset_instance() 후 새 인스턴스 생성"""
        a = SentimentAnalyzer.get_instance()
        SentimentAnalyzer.reset_instance()
        b = SentimentAnalyzer.get_instance()
        assert a is not b

    def test_get_instance_with_kwargs(self):
        """kwargs를 전달하여 인스턴스 생성"""
        sa = SentimentAnalyzer.get_instance(model_name="custom/model", device="cuda")
        assert sa.model_name == "custom/model"
        assert sa.device == "cuda"


class TestEnsureLoaded:
    """_ensure_loaded 메서드 테스트"""

    def test_loads_pipeline_once(self):
        """pipeline이 한 번만 로드되는지 확인"""
        import sys
        mock_transformers = MagicMock()
        mock_pipeline_fn = mock_transformers.pipeline
        mock_pipeline_fn.return_value = MagicMock()

        with patch.dict(sys.modules, {'transformers': mock_transformers}):
            sa = SentimentAnalyzer()
            sa._ensure_loaded()
            sa._ensure_loaded()  # 두 번째 호출은 무시
            mock_pipeline_fn.assert_called_once()

    def test_pipeline_called_with_correct_args(self):
        """pipeline이 올바른 인수로 호출되는지 확인"""
        import sys
        mock_transformers = MagicMock()
        mock_pipeline_fn = mock_transformers.pipeline
        mock_pipeline_fn.return_value = MagicMock()

        with patch.dict(sys.modules, {'transformers': mock_transformers}):
            sa = SentimentAnalyzer(model_name="ProsusAI/finbert", device="cpu")
            sa._ensure_loaded()
            mock_pipeline_fn.assert_called_once_with(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                device="cpu",
                truncation=True,
                max_length=512,
            )


# ──────────────────────────────────────────────────────────────────────
# Layer5 SentimentLayer FinBERT 통합 테스트
# ──────────────────────────────────────────────────────────────────────

class TestLayer5FinBERTIntegration:
    """layer5_sentiment.py의 _calc_news_sentiment FinBERT 분기 테스트"""

    def test_finbert_disabled_uses_keywords(self):
        """FINBERT_ENABLED=false일 때 키워드 분석 사용"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'false'}):
            score, details = SentimentLayer._calc_news_sentiment([
                {'title': 'Market rally continues with strong gains'},
            ])
            # 키워드 분석 결과 (method 키가 없음)
            assert 'method' not in details
            assert 'positive_count' in details

    def test_finbert_not_set_uses_keywords(self):
        """FINBERT_ENABLED 미설정 시 키워드 분석 사용"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        env = os.environ.copy()
        env.pop('FINBERT_ENABLED', None)
        with patch.dict(os.environ, env, clear=True):
            score, details = SentimentLayer._calc_news_sentiment([
                {'title': 'Stock surge bullish rally'},
            ])
            assert 'method' not in details

    @patch('trading_bot.sentiment_analyzer.SentimentAnalyzer._ensure_loaded')
    def test_finbert_enabled_uses_finbert(self, mock_load):
        """FINBERT_ENABLED=true일 때 FinBERT 분석 사용"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        mock_analyzer = SentimentAnalyzer()
        mock_analyzer._pipeline = MagicMock()
        mock_analyzer._pipeline.return_value = [
            {'label': 'positive', 'score': 0.90},
        ]

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'true'}):
            with patch(
                'trading_bot.sentiment_analyzer.SentimentAnalyzer.get_instance',
                return_value=mock_analyzer,
            ):
                score, details = SentimentLayer._calc_news_sentiment([
                    {'title': 'Great earnings beat expectations'},
                ])
                assert details['method'] == 'finbert'
                assert details['positive_count'] == 1

    def test_finbert_import_error_falls_back(self):
        """transformers 미설치 시 키워드 폴백"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'true'}):
            # Simulate ImportError by making the sentiment_analyzer module raise ImportError
            with patch.dict('sys.modules', {'trading_bot.sentiment_analyzer': None}):
                score, details = SentimentLayer._calc_news_sentiment([
                    {'title': 'Market rally strong gains'},
                ])
                # 키워드 폴백
                assert 'method' not in details
                assert 'positive_count' in details

    def test_finbert_runtime_error_falls_back(self):
        """FinBERT 런타임 에러 시 키워드 폴백"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_headlines.side_effect = RuntimeError("GPU OOM")

        mock_sa_class = MagicMock()
        mock_sa_class.get_instance.return_value = mock_analyzer

        mock_module = MagicMock()
        mock_module.SentimentAnalyzer = mock_sa_class

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'true'}):
            with patch.dict('sys.modules', {'trading_bot.sentiment_analyzer': mock_module}):
                score, details = SentimentLayer._calc_news_sentiment([
                    {'title': 'Market crash plunge fear'},
                ])
                # 키워드 폴백
                assert 'method' not in details
                assert details['negative_count'] > 0

    def test_finbert_empty_news_still_returns(self):
        """빈 뉴스 데이터는 FinBERT 분기 전에 처리됨"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'true'}):
            score, details = SentimentLayer._calc_news_sentiment([])
            assert score == 0.0
            assert details['tone'] == 'no_data'

    def test_finbert_none_news(self):
        """None 뉴스 데이터 처리"""
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        with patch.dict(os.environ, {'FINBERT_ENABLED': 'true'}):
            score, details = SentimentLayer._calc_news_sentiment(None)
            assert score == 0.0
            assert details['tone'] == 'no_data'
