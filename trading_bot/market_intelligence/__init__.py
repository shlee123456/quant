"""
Market Intelligence - 5-Layer 시장 분석 엔진

Layer 1: Macro Regime (경제 사이클 + 금리 + 유동성)
Layer 2: Market Structure (VIX + 시장 폭 + 옵션 프록시)
Layer 3: Sector/Factor Rotation (섹터 로테이션 + 팩터 레짐)
Layer 4: Enhanced Technicals (개별 종목 기술적 분석)
Layer 5: Sentiment & Positioning (심리 + 포지셔닝)

Usage:
    from trading_bot.market_intelligence import MarketIntelligence

    mi = MarketIntelligence()
    report = mi.analyze(
        stock_symbols=['AAPL', 'MSFT'],
        stocks_data=result.get('stocks', {}),
        news_data=result.get('news'),
        fear_greed_data=result.get('fear_greed_index'),
    )
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import (
    percentile_rank,
    rolling_z_score,
    momentum_score,
    weighted_composite,
    calc_rsi,
    pct_change,
)
from .data_fetcher import MarketDataCache, LAYER_SYMBOLS
from .fred_fetcher import FREDDataFetcher
from .layer1_macro_regime import MacroRegimeLayer
from .layer2_market_structure import MarketStructureLayer
from .layer3_sector_rotation import SectorRotationLayer
from .layer4_technicals import TechnicalsLayer
from .layer5_sentiment import SentimentLayer

logger = logging.getLogger(__name__)

# 레이어별 가중치
LAYER_WEIGHTS: Dict[str, float] = {
    'macro_regime': 0.20,
    'market_structure': 0.20,
    'sector_rotation': 0.15,
    'enhanced_technicals': 0.25,
    'sentiment': 0.20,
}


class MarketIntelligence:
    """5-Layer 시장 인텔리전스 오케스트레이터.

    모든 레이어를 초기화하고 ``analyze()`` 메서드로 전체 분석을 수행합니다.
    MarketDataCache를 통해 단일 yf.download() 호출로 데이터를 가져오고,
    5개 레이어를 순차적으로 실행하여 종합 리포트를 생성합니다.

    Args:
        period: yfinance 조회 기간 (기본 '6mo')
        interval: yfinance 조회 간격 (기본 '1d')
        layer_weights: 레이어별 가중치 (기본: LAYER_WEIGHTS)
    """

    def __init__(
        self,
        period: str = '6mo',
        interval: str = '1d',
        layer_weights: Optional[Dict[str, float]] = None,
        fred_api_key: Optional[str] = None,
    ):
        # FRED 초기화
        from .fred_fetcher import FREDDataFetcher
        self._fred_fetcher = FREDDataFetcher(api_key=fred_api_key)

        # 데이터 캐시에 FRED 연결
        self.cache = MarketDataCache(
            period=period, interval=interval,
            fred_fetcher=self._fred_fetcher,
        )
        self.weights = layer_weights or LAYER_WEIGHTS.copy()

        # 5개 레이어 초기화
        self.layers: Dict[str, BaseIntelligenceLayer] = {
            'macro_regime': MacroRegimeLayer(),
            'market_structure': MarketStructureLayer(),
            'sector_rotation': SectorRotationLayer(),
            'enhanced_technicals': TechnicalsLayer(),
            'sentiment': SentimentLayer(),
        }

    def analyze(
        self,
        stock_symbols: Optional[List[str]] = None,
        stocks_data: Optional[Dict[str, Any]] = None,
        news_data: Optional[Any] = None,
        fear_greed_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """전체 5-Layer 분석을 실행합니다.

        1. MarketDataCache로 yfinance 데이터 다운로드
        2. 공유 컨텍스트 구성
        3. 각 레이어 분석 (실패 시 중립 점수)
        4. 종합 점수 산출
        5. 구조화된 리포트 반환

        Args:
            stock_symbols: 분석 대상 종목 심볼 리스트
            stocks_data: 기존 MarketAnalyzer 분석 결과 {symbol: {...}}
            news_data: 뉴스 데이터 (리스트 또는 딕셔너리)
            fear_greed_data: Fear & Greed 지수 데이터

        Returns:
            구조화된 인텔리전스 리포트 딕셔너리
        """
        stock_symbols = stock_symbols or []

        # Step 1: yfinance 데이터 다운로드
        fetch_success = self.cache.fetch(stock_symbols=stock_symbols)
        if not fetch_success:
            logger.warning("MarketDataCache 다운로드 실패 - 가용 데이터로 분석 진행")

        # Step 2: 공유 컨텍스트 구성
        # news_data를 리스트로 정규화 (뉴스 수집 결과가 dict일 수 있음)
        news_list = self._normalize_news(news_data)

        # fear_greed_data에서 current 값 추출
        fg_for_layer = self._normalize_fear_greed(fear_greed_data)

        context: Dict[str, Any] = {
            'cache': self.cache,
            'stocks': stocks_data or {},
            'news': news_list,
            'fear_greed': fg_for_layer,
            'stock_symbols': stock_symbols,
        }

        # Step 3: 각 레이어 분석
        layer_results: Dict[str, LayerResult] = {}

        for layer_key, layer in self.layers.items():
            try:
                result = layer.analyze(context)
                layer_results[layer_key] = result
                logger.info(
                    f"Layer [{layer_key}] 완료: "
                    f"score={result.score:+.1f}, signal={result.signal}, "
                    f"confidence={result.confidence:.0%}"
                )
            except Exception as e:
                logger.warning(f"Layer [{layer_key}] 실패 (NaN 점수 할당): {e}")
                layer_results[layer_key] = LayerResult(
                    layer_name=layer_key,
                    score=float('nan'),
                    signal="neutral",
                    confidence=0.0,
                    metrics={},
                    interpretation=f"레이어 분석 실패: {e}",
                    details={'error': str(e)},
                )

        # Step 4: 동적 가중치 계산
        dynamic_weights = self._compute_dynamic_weights(layer_results)

        # Step 5: 종합 점수 계산
        layer_scores = {
            layer_key: result.score
            for layer_key, result in layer_results.items()
        }
        composite = weighted_composite(layer_scores, dynamic_weights)
        overall_signal = BaseIntelligenceLayer.classify_score(composite)
        interpretation = self._build_overall_interpretation(
            composite, overall_signal, layer_results
        )

        # Step 6: 리포트 구성
        report: Dict[str, Any] = {
            'generated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'overall': {
                'score': round(composite, 1),
                'signal': overall_signal,
                'interpretation': interpretation,
                'weights_mode': 'dynamic',
            },
            'layers': {
                layer_key: result.to_dict()
                for layer_key, result in layer_results.items()
            },
            'layer_weights': dynamic_weights,
        }

        # Meta-confidence 계산
        report['overall']['meta_confidence'] = self._compute_meta_confidence(layer_results)

        logger.info(
            f"5-Layer Intelligence 분석 완료: "
            f"score={composite:+.1f}, signal={overall_signal}"
        )

        return report

    def _compute_dynamic_weights(self, layer_results: Dict[str, LayerResult]) -> Dict[str, float]:
        """레짐에 따라 레이어 가중치를 동적으로 조절.

        Layer 1의 cycle_phase와 Layer 2의 VIX 점수를 기반으로
        시장 상황에 맞게 가중치를 재조정합니다.
        """
        import math
        weights = dict(self.weights)  # copy

        # Layer 1에서 cycle_phase 추출
        l1 = layer_results.get('macro_regime')
        cycle = 'unknown'
        if l1 and l1.details and not math.isnan(l1.score):
            cycle = l1.details.get('cycle_phase', 'unknown')

        # Layer 2에서 VIX 점수 추출
        l2 = layer_results.get('market_structure')
        vix_score = 0
        if l2 and l2.metrics and not math.isnan(l2.score):
            vix_score = l2.metrics.get('vix_level', 0)

        if cycle == 'contraction' or vix_score < -30:
            # 위기/고변동성: 매크로 + 센티먼트 중시
            weights['macro_regime'] = 0.30
            weights['sentiment'] = 0.25
            weights['enhanced_technicals'] = 0.15
            weights['market_structure'] = 0.15
            weights['sector_rotation'] = 0.15
        elif cycle == 'expansion' and vix_score > 20:
            # 안정적 확장: 기술적 + 섹터 중시
            weights['enhanced_technicals'] = 0.30
            weights['sector_rotation'] = 0.20
            weights['macro_regime'] = 0.15
            weights['market_structure'] = 0.20
            weights['sentiment'] = 0.15
        # else: 기본 가중치 유지

        return weights

    def _compute_meta_confidence(self, layer_results: Dict[str, LayerResult]) -> float:
        """레이어 간 의견 일치도를 측정.

        Returns:
            0.0 (완전 불일치) ~ 1.0 (완전 합의)
        """
        import math
        import numpy as np

        scores = [r.score for r in layer_results.values()
                  if not math.isnan(r.score)]
        if len(scores) < 2:
            return 0.5

        score_std = float(np.std(scores))
        agreement = max(0.0, 1.0 - (score_std / 80.0))

        confidences = [r.confidence for r in layer_results.values()
                       if not math.isnan(r.score)]
        avg_confidence = float(np.mean(confidences)) if confidences else 0.5

        return round(min(1.0, agreement * avg_confidence), 2)

    @staticmethod
    def _normalize_news(news_data: Optional[Any]) -> Optional[List[Dict]]:
        """뉴스 데이터를 레이어에서 사용할 리스트 형태로 정규화.

        Args:
            news_data: 원본 뉴스 데이터 (dict 또는 list)

        Returns:
            뉴스 헤드라인 리스트 또는 None
        """
        if news_data is None:
            return None

        if isinstance(news_data, list):
            return news_data

        # dict인 경우 (NewsCollector 형식)
        if isinstance(news_data, dict):
            result = []
            # market_news
            market_news = news_data.get('market_news', [])
            if isinstance(market_news, list):
                result.extend(market_news)
            # stock_news
            stock_news = news_data.get('stock_news', {})
            if isinstance(stock_news, dict):
                for items in stock_news.values():
                    if isinstance(items, list):
                        result.extend(items)
            return result if result else None

        return None

    @staticmethod
    def _normalize_fear_greed(
        fear_greed_data: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Fear & Greed 데이터에서 current 값을 추출하여 레이어 형식으로 변환.

        Args:
            fear_greed_data: FearGreedCollector 형식 데이터

        Returns:
            {'value': int} 형태 또는 None
        """
        if fear_greed_data is None:
            return None

        # 이미 {'value': ...} 형태인 경우
        if 'value' in fear_greed_data:
            return fear_greed_data

        # FearGreedCollector 형식: {'current': {'value': ...}, 'history': [...]}
        current = fear_greed_data.get('current', {})
        if isinstance(current, dict) and 'value' in current:
            return {'value': current['value']}

        return None

    @staticmethod
    def _build_overall_interpretation(
        composite: float,
        signal: str,
        layer_results: Dict[str, LayerResult],
    ) -> str:
        """종합 해석 문자열을 생성합니다.

        Args:
            composite: 종합 점수
            signal: 종합 시그널
            layer_results: 레이어별 결과

        Returns:
            한국어 종합 해석 문자열
        """
        signal_kr = {
            'bullish': '긍정적',
            'bearish': '부정적',
            'neutral': '중립',
        }

        parts = [
            f"종합 시장 환경 {signal_kr.get(signal, '중립')} "
            f"(점수: {composite:+.1f})"
        ]

        # 가장 강/약한 레이어 언급 (NaN 제외)
        valid_scores = {
            k: r.score for k, r in layer_results.items()
            if not math.isnan(r.score)
        }

        if valid_scores:
            strongest = max(valid_scores, key=valid_scores.get)  # type: ignore
            weakest = min(valid_scores, key=valid_scores.get)  # type: ignore

            layer_names_kr = {
                'macro_regime': '매크로',
                'market_structure': '시장 구조',
                'sector_rotation': '섹터 로테이션',
                'enhanced_technicals': '기술적 분석',
                'sentiment': '센티먼트',
            }

            strongest_name = layer_names_kr.get(strongest, strongest)
            weakest_name = layer_names_kr.get(weakest, weakest)

            if valid_scores[strongest] > 20:
                parts.append(
                    f"{strongest_name} 긍정적({valid_scores[strongest]:+.0f})"
                )
            if valid_scores[weakest] < -20:
                parts.append(
                    f"{weakest_name} 부정적({valid_scores[weakest]:+.0f})"
                )
        else:
            parts.append("레이어 데이터 부족")

        return ". ".join(parts)

    @staticmethod
    def get_position_size_recommendation(
        report: Dict[str, Any],
        fear_greed_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """5-Layer 점수 + Fear & Greed 기반 포지션 크기 추천.

        Args:
            report: analyze() 반환값 (overall.score, overall.signal 포함)
            fear_greed_value: F&G 지수 값 (0-100). None이면 report에서 추출 시도 안 함.

        Returns:
            {
                'multiplier': float (0.5 ~ 1.5),
                'reason': str,
                'adjustments': list[str],
            }
        """
        multiplier = 1.0
        adjustments: List[str] = []

        # F&G 기반 조정
        if fear_greed_value is not None:
            if fear_greed_value < 25:
                multiplier += 0.25
                adjustments.append(f"극단적 공포({fear_greed_value:.0f}): +25%")
            elif fear_greed_value > 75:
                multiplier -= 0.25
                adjustments.append(f"극단적 탐욕({fear_greed_value:.0f}): -25%")

        # Overall score 기반 조정
        overall = report.get('overall', {})
        score = overall.get('score', 0.0)

        if score > 30:
            multiplier += 0.15
            adjustments.append(f"강세 시그널({score:+.1f}): +15%")
        elif score < -30:
            multiplier += 0.10
            adjustments.append(f"역발상 매수({score:+.1f}): +10%")

        # Meta-confidence 기반 조정
        meta_conf = overall.get('meta_confidence', 1.0)
        if meta_conf < 0.4:
            multiplier *= 0.7
            adjustments.append(f'레이어 불일치(meta_confidence={meta_conf:.2f}): -30%')

        # Clamp to [0.5, 1.5]
        multiplier = max(0.5, min(1.5, multiplier))

        reason = ", ".join(adjustments) if adjustments else "중립 (조정 없음)"

        return {
            'multiplier': round(multiplier, 2),
            'reason': reason,
            'adjustments': adjustments,
        }


__all__ = [
    # Orchestrator
    'MarketIntelligence',
    'LAYER_WEIGHTS',
    # Base
    'BaseIntelligenceLayer',
    'LayerResult',
    # Scoring
    'percentile_rank',
    'rolling_z_score',
    'momentum_score',
    'weighted_composite',
    'calc_rsi',
    'pct_change',
    # Data
    'MarketDataCache',
    'LAYER_SYMBOLS',
    # FRED
    'FREDDataFetcher',
    # Layers
    'MacroRegimeLayer',
    'MarketStructureLayer',
    'SectorRotationLayer',
    'TechnicalsLayer',
    'SentimentLayer',
]
