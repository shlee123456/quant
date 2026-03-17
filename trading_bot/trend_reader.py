"""
멀티데이 트렌드 분석 모듈

data/market_analysis/YYYY-MM-DD.json 파일들을 날짜순으로 읽어
Fear & Greed 트렌드, 종목별 가격/RSI/레짐 변화, Intelligence 트렌드를 분석한다.

외부 의존성 없음 (json, glob, os, logging만 사용).
"""

import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TrendReader:
    """data/market_analysis/ 디렉토리의 JSON 파일들을 읽어 멀티데이 트렌드를 분석한다.

    Args:
        analysis_dir: 분석 JSON 파일이 저장된 디렉토리 경로.
    """

    def __init__(self, analysis_dir: str = 'data/market_analysis') -> None:
        self.analysis_dir = analysis_dir

    def read_recent(self, n_days: int = 5) -> List[Dict]:
        """최근 n_days개의 분석 JSON 파일을 날짜순으로 로드한다.

        Args:
            n_days: 로드할 최근 파일 수.

        Returns:
            날짜순 정렬된 분석 결과 딕셔너리 리스트 (오래된 날짜가 먼저).
        """
        pattern = os.path.join(self.analysis_dir, '*.json')
        files = glob.glob(pattern)

        # 파일명에서 날짜 추출하여 정렬 (YYYY-MM-DD.json)
        dated_files: List[tuple] = []
        for filepath in files:
            basename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(basename)[0]
            # YYYY-MM-DD 형식 검증
            parts = name_without_ext.split('-')
            if len(parts) == 3 and len(parts[0]) == 4:
                try:
                    int(parts[0])
                    int(parts[1])
                    int(parts[2])
                    dated_files.append((name_without_ext, filepath))
                except ValueError:
                    continue

        # 날짜순 정렬 (오래된 것부터)
        dated_files.sort(key=lambda x: x[0])

        # 최근 n_days개만 선택
        recent_files = dated_files[-n_days:]

        results: List[Dict] = []
        for date_str, filepath in recent_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                results.append(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"JSON 파일 로드 실패 ({filepath}): {e}")
                continue

        return results

    def analyze_trends(self, n_days: int = 5) -> Dict[str, Any]:
        """최근 n_days의 분석 데이터에서 멀티데이 트렌드를 추출한다.

        Args:
            n_days: 분석할 최근 일수.

        Returns:
            트렌드 분석 결과 딕셔너리. 구조:
            - period: 분석 기간 정보
            - fear_greed_trend: F&G 지수 트렌드
            - symbol_trends: 종목별 가격/RSI/레짐 트렌드
            - regime_summary: 레짐 전환 요약
            - intelligence_trend: 5-Layer Intelligence 트렌드
            - summary_text: 한글 요약 텍스트
        """
        data_list = self.read_recent(n_days)

        if not data_list:
            return {
                'period': {'start': None, 'end': None, 'days': 0},
                'fear_greed_trend': {
                    'values': [],
                    'direction': 'stable',
                    'change': 0.0,
                },
                'symbol_trends': {},
                'regime_summary': {
                    'transitions_count': 0,
                    'notable_transitions': [],
                },
                'intelligence_trend': {
                    'scores': [],
                    'direction': 'stable',
                },
                'summary_text': '분석 데이터가 없습니다.',
            }

        # 기간 정보
        dates = [d.get('date', '') for d in data_list]
        period = {
            'start': dates[0] if dates else None,
            'end': dates[-1] if dates else None,
            'days': len(dates),
        }

        # Fear & Greed 트렌드
        fear_greed_trend = self._analyze_fear_greed(data_list)

        # 종목별 트렌드
        symbol_trends, regime_summary = self._analyze_symbols(data_list)

        # Intelligence 트렌드
        intelligence_trend = self._analyze_intelligence(data_list)

        # 한글 요약 생성
        summary_text = self._generate_summary(
            period, fear_greed_trend, symbol_trends, regime_summary, intelligence_trend
        )

        return {
            'period': period,
            'fear_greed_trend': fear_greed_trend,
            'symbol_trends': symbol_trends,
            'regime_summary': regime_summary,
            'intelligence_trend': intelligence_trend,
            'summary_text': summary_text,
        }

    def _detect_trend_direction(self, values: List[float]) -> str:
        """값 리스트의 트렌드 방향을 판별한다.

        첫값에서 마지막값으로의 변화율 기준:
        - +2% 이상: rising (또는 improving)
        - -2% 이하: falling (또는 worsening)
        - 그 외: stable

        Args:
            values: 시계열 값 리스트.

        Returns:
            'rising', 'falling', 또는 'stable'.
        """
        if len(values) < 2:
            return 'stable'

        first = values[0]
        last = values[-1]

        if first == 0:
            # 0에서 시작하면 절대 변화로 판단
            if last > 2:
                return 'rising'
            elif last < -2:
                return 'falling'
            return 'stable'

        change_pct = (last - first) / abs(first) * 100
        if change_pct >= 2:
            return 'rising'
        elif change_pct <= -2:
            return 'falling'
        else:
            return 'stable'

    def _analyze_fear_greed(self, data_list: List[Dict]) -> Dict[str, Any]:
        """Fear & Greed 지수의 트렌드를 분석한다."""
        values_list: List[Dict] = []
        raw_values: List[float] = []

        for data in data_list:
            date = data.get('date', '')
            fg = data.get('fear_greed_index', {}).get('current', {})
            value = fg.get('value')
            classification = fg.get('classification', '')

            if value is not None:
                values_list.append({
                    'date': date,
                    'value': value,
                    'classification': classification,
                })
                raw_values.append(value)

        direction_raw = self._detect_trend_direction(raw_values)
        # F&G에서는 값이 올라가면 improving, 내려가면 worsening
        direction_map = {'rising': 'improving', 'falling': 'worsening', 'stable': 'stable'}
        direction = direction_map[direction_raw]

        change = (raw_values[-1] - raw_values[0]) if len(raw_values) >= 2 else 0.0

        return {
            'values': values_list,
            'direction': direction,
            'change': change,
        }

    def _analyze_symbols(self, data_list: List[Dict]) -> tuple:
        """종목별 가격, RSI, 레짐 트렌드를 분석한다.

        Returns:
            (symbol_trends, regime_summary) 튜플.
        """
        # 모든 종목 수집
        all_symbols: set = set()
        for data in data_list:
            stocks = data.get('stocks', {})
            all_symbols.update(stocks.keys())

        symbol_trends: Dict[str, Dict] = {}
        all_transitions: List[str] = []

        for symbol in sorted(all_symbols):
            prices: List[Dict] = []
            raw_prices: List[float] = []
            rsi_values: List[Dict] = []
            raw_rsi: List[float] = []
            regime_transitions: List[Dict] = []
            prev_regime: Optional[str] = None
            current_regime: str = 'UNKNOWN'

            for data in data_list:
                date = data.get('date', '')
                stock = data.get('stocks', {}).get(symbol, {})

                # 가격
                price_data = stock.get('price', {})
                price = price_data.get('last')
                if price is not None:
                    prices.append({'date': date, 'price': price})
                    raw_prices.append(price)

                # RSI
                indicators = stock.get('indicators', {})
                rsi = indicators.get('rsi', {}).get('value')
                if rsi is not None:
                    rsi_values.append({'date': date, 'rsi': rsi})
                    raw_rsi.append(rsi)

                # 레짐
                regime = stock.get('regime', {}).get('state')
                if regime is not None:
                    current_regime = regime
                    if prev_regime is not None and regime != prev_regime:
                        transition = {
                            'date': date,
                            'from': prev_regime,
                            'to': regime,
                        }
                        regime_transitions.append(transition)
                        # 날짜에서 월/일 추출
                        date_short = date[5:] if len(date) >= 10 else date
                        notable = f"{symbol}: {prev_regime}\u2192{regime} ({date_short})"
                        all_transitions.append(notable)
                    prev_regime = regime

            # 가격 변화율 계산
            if len(raw_prices) >= 2:
                price_change_pct = (raw_prices[-1] - raw_prices[0]) / raw_prices[0] * 100
            else:
                price_change_pct = 0.0

            symbol_trends[symbol] = {
                'prices': prices,
                'price_change_pct': round(price_change_pct, 2),
                'rsi_values': rsi_values,
                'rsi_trend': self._detect_trend_direction(raw_rsi),
                'regime_transitions': regime_transitions,
                'current_regime': current_regime,
            }

        regime_summary = {
            'transitions_count': len(all_transitions),
            'notable_transitions': all_transitions,
        }

        return symbol_trends, regime_summary

    def _analyze_intelligence(self, data_list: List[Dict]) -> Dict[str, Any]:
        """5-Layer Intelligence 스코어의 트렌드를 분석한다."""
        scores_list: List[Dict] = []
        raw_scores: List[float] = []

        for data in data_list:
            date = data.get('date', '')
            intel = data.get('intelligence', {}).get('overall', {})
            score = intel.get('score')
            signal = intel.get('signal', '')

            if score is not None:
                scores_list.append({
                    'date': date,
                    'score': score,
                    'signal': signal,
                })
                raw_scores.append(score)

        direction = self._detect_trend_direction(raw_scores)

        return {
            'scores': scores_list,
            'direction': direction,
        }

    def _generate_summary(
        self,
        period: Dict,
        fear_greed_trend: Dict,
        symbol_trends: Dict,
        regime_summary: Dict,
        intelligence_trend: Dict,
    ) -> str:
        """트렌드 분석 결과를 한글 요약 텍스트로 변환한다."""
        parts: List[str] = []

        # 기간
        parts.append(
            f"분석 기간: {period['start']} ~ {period['end']} ({period['days']}일간)"
        )

        # F&G 트렌드
        fg = fear_greed_trend
        fg_dir_kr = {
            'improving': '개선',
            'worsening': '악화',
            'stable': '유지',
        }
        if fg['values']:
            first_val = fg['values'][0]['value']
            last_val = fg['values'][-1]['value']
            last_cls = fg['values'][-1].get('classification', '')
            parts.append(
                f"공포·탐욕 지수: {first_val:.1f} → {last_val:.1f} "
                f"({fg_dir_kr.get(fg['direction'], fg['direction'])}, "
                f"현재 {last_cls})"
            )

        # 레짐 전환
        if regime_summary['transitions_count'] > 0:
            parts.append(
                f"레짐 전환: {regime_summary['transitions_count']}건 "
                f"({', '.join(regime_summary['notable_transitions'][:3])})"
            )
        else:
            parts.append("레짐 전환: 없음")

        # Intelligence 트렌드
        intel = intelligence_trend
        intel_dir_kr = {
            'rising': '상승',
            'falling': '하락',
            'stable': '유지',
        }
        if intel['scores']:
            first_score = intel['scores'][0]['score']
            last_score = intel['scores'][-1]['score']
            last_signal = intel['scores'][-1].get('signal', '')
            parts.append(
                f"종합 인텔리전스: {first_score:.1f} → {last_score:.1f} "
                f"({intel_dir_kr.get(intel['direction'], intel['direction'])}, "
                f"현재 {last_signal})"
            )

        # 주요 가격 변동 종목 (|변화율| > 3%)
        big_movers = []
        for sym, trend in symbol_trends.items():
            pct = trend['price_change_pct']
            if abs(pct) > 3:
                direction = '상승' if pct > 0 else '하락'
                big_movers.append(f"{sym} {pct:+.1f}%({direction})")

        if big_movers:
            parts.append(f"주요 변동: {', '.join(big_movers[:5])}")

        return ' | '.join(parts)
