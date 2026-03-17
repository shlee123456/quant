"""
TrendReader 단위 테스트

tmp_path fixture를 사용하여 임시 JSON 파일을 생성하고
멀티데이 트렌드 분석 기능을 검증한다.
"""

import json
import os

import pytest

from trading_bot.trend_reader import TrendReader


def _make_analysis_json(
    date: str,
    fear_greed_value: float = 30.0,
    fear_greed_classification: str = "fear",
    stocks: dict = None,
    intelligence_score: float = -5.0,
    intelligence_signal: str = "neutral",
) -> dict:
    """테스트용 분석 JSON 딕셔너리를 생성한다."""
    if stocks is None:
        stocks = {
            'AAPL': {
                'price': {'last': 250.0, 'change_1d': 1.0, 'change_5d': -2.0, 'change_20d': 0.5},
                'indicators': {
                    'rsi': {'value': 45.0, 'signal': 'neutral'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
            },
        }

    return {
        'date': date,
        'stocks': stocks,
        'fear_greed_index': {
            'current': {
                'value': fear_greed_value,
                'classification': fear_greed_classification,
            },
        },
        'intelligence': {
            'overall': {
                'score': intelligence_score,
                'signal': intelligence_signal,
                'interpretation': f'종합 점수: {intelligence_score}',
            },
        },
    }


def _write_json(directory, date: str, data: dict) -> str:
    """JSON 데이터를 파일로 저장한다."""
    filepath = os.path.join(str(directory), f'{date}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return filepath


class TestReadRecent:
    """read_recent() 테스트"""

    def test_read_recent_finds_json_files(self, tmp_path):
        """JSON 파일을 찾아 로드한다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json('2026-03-15'))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json('2026-03-16'))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json('2026-03-17'))

        reader = TrendReader(analysis_dir=str(tmp_path))
        results = reader.read_recent(n_days=5)

        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)
        assert results[0]['date'] == '2026-03-15'
        assert results[-1]['date'] == '2026-03-17'

    def test_read_recent_sorted_by_date(self, tmp_path):
        """날짜순으로 정렬하여 반환한다 (오래된 것이 먼저)."""
        # 파일을 역순으로 생성
        _write_json(tmp_path, '2026-03-17', _make_analysis_json('2026-03-17'))
        _write_json(tmp_path, '2026-03-11', _make_analysis_json('2026-03-11'))
        _write_json(tmp_path, '2026-03-14', _make_analysis_json('2026-03-14'))
        _write_json(tmp_path, '2026-03-13', _make_analysis_json('2026-03-13'))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json('2026-03-16'))

        reader = TrendReader(analysis_dir=str(tmp_path))
        results = reader.read_recent(n_days=10)

        dates = [r['date'] for r in results]
        assert dates == sorted(dates)

    def test_read_recent_limits_to_n_days(self, tmp_path):
        """n_days 개수만큼만 반환한다 (가장 최근 것부터)."""
        for day in range(10, 18):
            date_str = f'2026-03-{day}'
            _write_json(tmp_path, date_str, _make_analysis_json(date_str))

        reader = TrendReader(analysis_dir=str(tmp_path))
        results = reader.read_recent(n_days=3)

        assert len(results) == 3
        # 가장 최근 3일
        assert results[0]['date'] == '2026-03-15'
        assert results[-1]['date'] == '2026-03-17'

    def test_read_recent_empty_directory(self, tmp_path):
        """빈 디렉토리에서는 빈 리스트를 반환한다."""
        reader = TrendReader(analysis_dir=str(tmp_path))
        results = reader.read_recent(n_days=5)

        assert results == []

    def test_read_recent_ignores_non_date_files(self, tmp_path):
        """날짜 형식이 아닌 파일은 무시한다."""
        _write_json(tmp_path, '2026-03-17', _make_analysis_json('2026-03-17'))
        # 비-날짜 파일
        _write_json(tmp_path, 'readme', {'note': 'not analysis data'})
        _write_json(tmp_path, 'config', {'setting': 'value'})

        reader = TrendReader(analysis_dir=str(tmp_path))
        results = reader.read_recent(n_days=10)

        assert len(results) == 1
        assert results[0]['date'] == '2026-03-17'


class TestAnalyzeTrends:
    """analyze_trends() 테스트"""

    def test_analyze_trends_no_files(self, tmp_path):
        """빈 디렉토리에서도 에러 없이 빈 결과를 반환한다."""
        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['period']['days'] == 0
        assert result['fear_greed_trend']['direction'] == 'stable'
        assert result['symbol_trends'] == {}
        assert result['regime_summary']['transitions_count'] == 0
        assert result['intelligence_trend']['direction'] == 'stable'
        assert '데이터가 없습니다' in result['summary_text']

    def test_analyze_trends_single_file(self, tmp_path):
        """파일 1개만 있을 때도 정상 동작한다."""
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', fear_greed_value=25.0, intelligence_score=-3.0,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['period']['days'] == 1
        assert result['period']['start'] == '2026-03-17'
        assert result['period']['end'] == '2026-03-17'
        assert result['fear_greed_trend']['direction'] == 'stable'
        assert len(result['fear_greed_trend']['values']) == 1
        assert 'AAPL' in result['symbol_trends']

    def test_analyze_trends_fear_greed_improving(self, tmp_path):
        """F&G 값이 상승하면 'improving'으로 감지한다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', fear_greed_value=20.0, fear_greed_classification='extreme fear',
        ))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json(
            '2026-03-16', fear_greed_value=25.0, fear_greed_classification='fear',
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', fear_greed_value=35.0, fear_greed_classification='fear',
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        fg = result['fear_greed_trend']
        assert fg['direction'] == 'improving'
        assert fg['change'] == 15.0  # 35.0 - 20.0

    def test_analyze_trends_fear_greed_worsening(self, tmp_path):
        """F&G 값이 하락하면 'worsening'으로 감지한다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', fear_greed_value=40.0, fear_greed_classification='fear',
        ))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json(
            '2026-03-16', fear_greed_value=30.0, fear_greed_classification='fear',
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', fear_greed_value=22.0, fear_greed_classification='extreme fear',
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        fg = result['fear_greed_trend']
        assert fg['direction'] == 'worsening'
        assert fg['change'] == -18.0  # 22.0 - 40.0

    def test_analyze_trends_fear_greed_stable(self, tmp_path):
        """F&G 변화가 ±2% 이내이면 'stable'로 감지한다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', fear_greed_value=30.0,
        ))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json(
            '2026-03-16', fear_greed_value=30.2,
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', fear_greed_value=30.4,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['fear_greed_trend']['direction'] == 'stable'

    def test_analyze_trends_regime_transitions(self, tmp_path):
        """레짐 전환을 감지한다."""
        stocks_day1 = {
            'AAPL': {
                'price': {'last': 260.0},
                'indicators': {'rsi': {'value': 42.0}},
                'regime': {'state': 'VOLATILE', 'confidence': 0.7},
            },
        }
        stocks_day2 = {
            'AAPL': {
                'price': {'last': 255.0},
                'indicators': {'rsi': {'value': 35.0}},
                'regime': {'state': 'VOLATILE', 'confidence': 0.65},
            },
        }
        stocks_day3 = {
            'AAPL': {
                'price': {'last': 250.0},
                'indicators': {'rsi': {'value': 30.0}},
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
            },
        }

        _write_json(tmp_path, '2026-03-13', _make_analysis_json(
            '2026-03-13', stocks=stocks_day1,
        ))
        _write_json(tmp_path, '2026-03-14', _make_analysis_json(
            '2026-03-14', stocks=stocks_day2,
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', stocks=stocks_day3,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        regime = result['regime_summary']
        assert regime['transitions_count'] == 1
        assert any('VOLATILE' in t and 'SIDEWAYS' in t for t in regime['notable_transitions'])

        aapl = result['symbol_trends']['AAPL']
        assert len(aapl['regime_transitions']) == 1
        assert aapl['regime_transitions'][0]['from'] == 'VOLATILE'
        assert aapl['regime_transitions'][0]['to'] == 'SIDEWAYS'
        assert aapl['current_regime'] == 'SIDEWAYS'

    def test_analyze_trends_no_regime_transitions(self, tmp_path):
        """레짐이 변하지 않으면 전환 건수 0."""
        for i, date in enumerate(['2026-03-15', '2026-03-16', '2026-03-17']):
            _write_json(tmp_path, date, _make_analysis_json(date))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['regime_summary']['transitions_count'] == 0
        assert result['regime_summary']['notable_transitions'] == []

    def test_analyze_trends_price_change(self, tmp_path):
        """가격 변화율을 올바르게 계산한다."""
        stocks_day1 = {
            'AAPL': {
                'price': {'last': 200.0},
                'indicators': {'rsi': {'value': 50.0}},
                'regime': {'state': 'BULLISH', 'confidence': 0.8},
            },
        }
        stocks_day2 = {
            'AAPL': {
                'price': {'last': 210.0},
                'indicators': {'rsi': {'value': 55.0}},
                'regime': {'state': 'BULLISH', 'confidence': 0.82},
            },
        }

        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', stocks=stocks_day1,
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', stocks=stocks_day2,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        aapl = result['symbol_trends']['AAPL']
        assert abs(aapl['price_change_pct'] - 5.0) < 0.01  # (210-200)/200*100 = 5%

    def test_analyze_trends_intelligence_direction(self, tmp_path):
        """Intelligence 스코어 트렌드 방향을 감지한다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', intelligence_score=-10.0, intelligence_signal='neutral',
        ))
        _write_json(tmp_path, '2026-03-16', _make_analysis_json(
            '2026-03-16', intelligence_score=-5.0, intelligence_signal='neutral',
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', intelligence_score=5.0, intelligence_signal='bullish',
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        intel = result['intelligence_trend']
        assert len(intel['scores']) == 3
        # -10 → 5: 변화율 = (5 - (-10)) / |-10| * 100 = 150% → rising
        assert intel['direction'] == 'rising'

    def test_analyze_trends_multiple_symbols(self, tmp_path):
        """여러 종목이 있을 때 모두 분석한다."""
        stocks = {
            'AAPL': {
                'price': {'last': 250.0},
                'indicators': {'rsi': {'value': 40.0}},
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
            },
            'MSFT': {
                'price': {'last': 400.0},
                'indicators': {'rsi': {'value': 55.0}},
                'regime': {'state': 'BULLISH', 'confidence': 0.8},
            },
        }

        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', stocks=stocks,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert 'AAPL' in result['symbol_trends']
        assert 'MSFT' in result['symbol_trends']


class TestDetectTrendDirection:
    """_detect_trend_direction() 테스트"""

    def test_rising(self):
        """상승 트렌드를 감지한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([100.0, 102.0, 105.0]) == 'rising'

    def test_falling(self):
        """하락 트렌드를 감지한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([100.0, 98.0, 95.0]) == 'falling'

    def test_stable(self):
        """안정적 트렌드를 감지한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([100.0, 100.5, 101.0]) == 'stable'

    def test_single_value(self):
        """값이 1개면 stable을 반환한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([50.0]) == 'stable'

    def test_empty_list(self):
        """빈 리스트면 stable을 반환한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([]) == 'stable'

    def test_exactly_two_percent_boundary(self):
        """정확히 2% 경계값 테스트."""
        reader = TrendReader()
        # 정확히 +2%: 100 -> 102, (102-100)/100*100 = 2.0 → rising
        assert reader._detect_trend_direction([100.0, 102.0]) == 'rising'
        # 정확히 -2%: 100 -> 98, (98-100)/100*100 = -2.0 → falling
        assert reader._detect_trend_direction([100.0, 98.0]) == 'falling'

    def test_zero_start(self):
        """첫값이 0일 때 절대 변화로 판단한다."""
        reader = TrendReader()
        assert reader._detect_trend_direction([0.0, 5.0]) == 'rising'
        assert reader._detect_trend_direction([0.0, -5.0]) == 'falling'
        assert reader._detect_trend_direction([0.0, 1.0]) == 'stable'

    def test_negative_values(self):
        """음수값 리스트도 올바르게 처리한다."""
        reader = TrendReader()
        # -10 → -5: change_pct = (-5 - (-10)) / |-10| * 100 = 50% → rising
        assert reader._detect_trend_direction([-10.0, -7.0, -5.0]) == 'rising'
        # -5 → -10: change_pct = (-10 - (-5)) / |-5| * 100 = -100% → falling
        assert reader._detect_trend_direction([-5.0, -7.0, -10.0]) == 'falling'


class TestSummaryText:
    """summary_text 생성 확인"""

    def test_summary_text_generated(self, tmp_path):
        """한글 요약 텍스트가 생성된다."""
        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', fear_greed_value=20.0, fear_greed_classification='extreme fear',
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', fear_greed_value=35.0, fear_greed_classification='fear',
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        text = result['summary_text']
        assert isinstance(text, str)
        assert len(text) > 0
        # 핵심 요소가 포함되어 있는지 확인
        assert '분석 기간' in text
        assert '공포' in text or '탐욕' in text
        assert '2026-03-15' in text
        assert '2026-03-17' in text

    def test_summary_text_includes_big_movers(self, tmp_path):
        """가격 변동 3% 이상 종목이 요약에 포함된다."""
        stocks_day1 = {
            'AAPL': {
                'price': {'last': 100.0},
                'indicators': {'rsi': {'value': 50.0}},
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            },
        }
        stocks_day2 = {
            'AAPL': {
                'price': {'last': 105.0},  # +5%
                'indicators': {'rsi': {'value': 55.0}},
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.5},
            },
        }

        _write_json(tmp_path, '2026-03-15', _make_analysis_json(
            '2026-03-15', stocks=stocks_day1,
        ))
        _write_json(tmp_path, '2026-03-17', _make_analysis_json(
            '2026-03-17', stocks=stocks_day2,
        ))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert '주요 변동' in result['summary_text']
        assert 'AAPL' in result['summary_text']

    def test_summary_text_empty_data(self, tmp_path):
        """데이터 없을 때 요약 텍스트 확인."""
        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert '데이터가 없습니다' in result['summary_text']


class TestRSITrend:
    """RSI 트렌드 분석 테스트"""

    def test_rsi_trend_rising(self, tmp_path):
        """RSI 상승 트렌드를 감지한다."""
        for i, (date, rsi) in enumerate([
            ('2026-03-13', 25.0),
            ('2026-03-14', 30.0),
            ('2026-03-17', 45.0),
        ]):
            stocks = {
                'AAPL': {
                    'price': {'last': 250.0 + i},
                    'indicators': {'rsi': {'value': rsi}},
                    'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
                },
            }
            _write_json(tmp_path, date, _make_analysis_json(date, stocks=stocks))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['symbol_trends']['AAPL']['rsi_trend'] == 'rising'

    def test_rsi_trend_falling(self, tmp_path):
        """RSI 하락 트렌드를 감지한다."""
        for i, (date, rsi) in enumerate([
            ('2026-03-13', 70.0),
            ('2026-03-14', 55.0),
            ('2026-03-17', 40.0),
        ]):
            stocks = {
                'AAPL': {
                    'price': {'last': 250.0 - i},
                    'indicators': {'rsi': {'value': rsi}},
                    'regime': {'state': 'SIDEWAYS', 'confidence': 0.6},
                },
            }
            _write_json(tmp_path, date, _make_analysis_json(date, stocks=stocks))

        reader = TrendReader(analysis_dir=str(tmp_path))
        result = reader.analyze_trends(n_days=5)

        assert result['symbol_trends']['AAPL']['rsi_trend'] == 'falling'


class TestImport:
    """import 테스트"""

    def test_import_from_package(self):
        """trading_bot 패키지에서 TrendReader를 임포트할 수 있다."""
        from trading_bot import TrendReader as TR
        assert TR is not None
        assert TR is TrendReader
