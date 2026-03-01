"""FinBERT 기반 금융 뉴스 감성 분석 (Lazy loading + Singleton)"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """FinBERT 기반 금융 뉴스 감성 분석"""

    _instance = None

    def __init__(self, model_name: str = "ProsusAI/finbert", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._pipeline = None

    @classmethod
    def get_instance(cls, **kwargs) -> 'SentimentAnalyzer':
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """테스트용 싱글턴 리셋"""
        cls._instance = None

    def _ensure_loaded(self):
        if self._pipeline is None:
            from transformers import pipeline
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=self.device,
                truncation=True,
                max_length=512,
            )

    def analyze_headlines(self, news_data: List[Dict]) -> Tuple[float, Dict]:
        """뉴스 헤드라인 감성 분석.

        Returns:
            (score: -100~+100, details: dict)
        """
        if not news_data:
            return 0.0, {
                'method': 'finbert',
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'total_headlines': 0,
                'headline_scores': [],
                'net_sentiment': 0.0,
                'tone': 'no_data',
            }

        self._ensure_loaded()

        headlines = []
        for item in news_data:
            title = item.get('title', '')
            if title:
                headlines.append(title)

        if not headlines:
            return 0.0, {
                'method': 'finbert',
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'total_headlines': 0,
                'headline_scores': [],
                'net_sentiment': 0.0,
                'tone': 'no_data',
            }

        # FinBERT inference
        results = self._pipeline(headlines)

        positive_count = 0
        negative_count = 0
        neutral_count = 0
        headline_scores = []
        weighted_sum = 0.0

        for headline, result in zip(headlines, results):
            label = result['label'].lower()
            confidence = result['score']

            if label == 'positive':
                positive_count += 1
                weighted_sum += confidence
            elif label == 'negative':
                negative_count += 1
                weighted_sum -= confidence
            else:
                neutral_count += 1

            headline_scores.append({
                'title': headline[:100],
                'label': label,
                'score': round(confidence, 4),
            })

        total = len(headlines)
        net_sentiment = weighted_sum / total if total > 0 else 0.0

        # Scale to -100 ~ +100
        score = max(-100, min(100, net_sentiment * 100))

        # Classify tone
        if score > 30:
            tone = 'positive'
        elif score < -30:
            tone = 'negative'
        elif positive_count > 0 or negative_count > 0:
            tone = 'mixed'
        else:
            tone = 'neutral'

        return round(score, 2), {
            'method': 'finbert',
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'total_headlines': total,
            'headline_scores': headline_scores,
            'net_sentiment': round(net_sentiment, 4),
            'tone': tone,
        }
