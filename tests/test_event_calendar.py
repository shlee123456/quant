"""EventCalendarCollector 및 _build_events_data_block 테스트"""

import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
import pandas as pd

from trading_bot.event_calendar import EventCalendarCollector
from trading_bot.market_analysis_prompt import _build_events_data_block


class TestFOMCSchedule:
    """FOMC 일정 로직 테스트"""

    def test_fomc_returns_next_date(self):
        """현재 날짜 기준 다음 FOMC 일정을 올바르게 반환"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_schedule()

        assert result['next_date'] == '2026-03-18'
        assert result['days_until'] == 45  # 2026-02-01 -> 2026-03-18
        assert '2026-03-18' in result['remaining_2026']
        assert '2026-01-28' not in result['remaining_2026']

    def test_fomc_all_past(self):
        """모든 FOMC 일정이 지난 경우"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_schedule()

        assert result['next_date'] is None
        assert result['days_until'] is None
        assert result['remaining_2026'] == []

    def test_fomc_on_meeting_day(self):
        """FOMC 당일"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 18)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_schedule()

        assert result['next_date'] == '2026-03-18'
        assert result['days_until'] == 0

    def test_fomc_remaining_count(self):
        """남은 FOMC 일정 수"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_schedule()

        assert len(result['remaining_2026']) == 8  # 모두 미래


class TestEarningsCollection:
    """실적 발표 일정 수집 테스트 (yfinance 모킹)"""

    def test_earnings_dict_format(self):
        """yfinance calendar가 dict 형태일 때"""
        collector = EventCalendarCollector(api_delay=0)

        mock_ticker = MagicMock()
        mock_ticker.calendar = {
            'Earnings Date': [datetime(2026, 4, 25)],
            'Earnings Average': 1.52,
            'Revenue Average': 95000000000,
        }

        with patch('trading_bot.event_calendar.yf') as mock_yf, \
             patch('trading_bot.event_calendar.datetime') as mock_dt, \
             patch('trading_bot.event_calendar.time'):
            mock_yf.Ticker.return_value = mock_ticker
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._fetch_earnings(['AAPL'])

        assert 'AAPL' in result
        assert result['AAPL']['date'] == '2026-04-25'
        assert result['AAPL']['days_until'] == 55
        assert result['AAPL']['estimate_eps'] == 1.52
        assert result['AAPL']['estimate_revenue'] == 95000000000

    def test_earnings_dataframe_format(self):
        """yfinance calendar가 DataFrame 형태일 때"""
        collector = EventCalendarCollector(api_delay=0)

        cal_df = pd.DataFrame(
            {'0': [datetime(2026, 5, 10), 2.15, 50000000000]},
            index=['Earnings Date', 'Earnings Average', 'Revenue Average']
        )
        mock_ticker = MagicMock()
        mock_ticker.calendar = cal_df

        with patch('trading_bot.event_calendar.yf') as mock_yf, \
             patch('trading_bot.event_calendar.datetime') as mock_dt, \
             patch('trading_bot.event_calendar.time'):
            mock_yf.Ticker.return_value = mock_ticker
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._fetch_earnings(['MSFT'])

        assert 'MSFT' in result
        assert result['MSFT']['date'] == '2026-05-10'
        assert result['MSFT']['estimate_eps'] == 2.15

    def test_earnings_none_calendar(self):
        """calendar가 None일 때"""
        collector = EventCalendarCollector(api_delay=0)

        mock_ticker = MagicMock()
        mock_ticker.calendar = None

        with patch('trading_bot.event_calendar.yf') as mock_yf, \
             patch('trading_bot.event_calendar.time'):
            mock_yf.Ticker.return_value = mock_ticker

            result = collector._fetch_earnings(['AAPL'])

        assert result == {}

    def test_earnings_empty_dataframe(self):
        """calendar가 빈 DataFrame일 때"""
        collector = EventCalendarCollector(api_delay=0)

        mock_ticker = MagicMock()
        mock_ticker.calendar = pd.DataFrame()

        with patch('trading_bot.event_calendar.yf') as mock_yf, \
             patch('trading_bot.event_calendar.time'):
            mock_yf.Ticker.return_value = mock_ticker

            result = collector._fetch_earnings(['AAPL'])

        assert result == {}

    def test_earnings_exception_handling(self):
        """개별 종목 조회 실패 시 다른 종목은 계속 처리"""
        collector = EventCalendarCollector(api_delay=0)

        mock_ticker_ok = MagicMock()
        mock_ticker_ok.calendar = {
            'Earnings Date': [datetime(2026, 4, 25)],
            'Earnings Average': 1.52,
            'Revenue Average': None,
        }

        mock_ticker_fail = MagicMock()
        mock_ticker_fail.calendar = property(lambda self: (_ for _ in ()).throw(Exception("API Error")))

        def side_effect(symbol):
            if symbol == 'AAPL':
                return mock_ticker_ok
            else:
                raise Exception("API Error")

        with patch('trading_bot.event_calendar.yf') as mock_yf, \
             patch('trading_bot.event_calendar.datetime') as mock_dt, \
             patch('trading_bot.event_calendar.time'):
            mock_yf.Ticker.side_effect = side_effect
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._fetch_earnings(['AAPL', 'FAIL_STOCK'])

        assert 'AAPL' in result
        assert 'FAIL_STOCK' not in result


class TestCollect:
    """collect() 메서드 통합 테스트"""

    def test_collect_empty_symbols(self):
        """빈 심볼 리스트 시 None 반환"""
        collector = EventCalendarCollector()
        result = collector.collect([])
        assert result is None

    def test_collect_returns_structure(self):
        """collect() 반환값 구조 확인"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={
            'AAPL': {
                'date': '2026-04-25',
                'days_until': 55,
                'estimate_eps': 1.52,
                'estimate_revenue': 95000000000,
            }
        }), patch.object(collector, '_get_fomc_schedule', return_value={
            'next_date': '2026-03-18',
            'days_until': 17,
            'remaining_2026': ['2026-03-18', '2026-05-06'],
        }):
            result = collector.collect(['AAPL'])

        assert result is not None
        assert 'collected_at' in result
        assert 'earnings' in result
        assert 'fomc' in result
        assert result['earnings']['AAPL']['date'] == '2026-04-25'
        assert result['fomc']['next_date'] == '2026-03-18'

    def test_collect_exception_returns_none(self):
        """collect() 내부 예외 시 None 반환"""
        collector = EventCalendarCollector()

        with patch.object(collector, '_fetch_earnings', side_effect=Exception("Critical error")):
            result = collector.collect(['AAPL'])

        assert result is None


class TestBuildEventsDataBlock:
    """_build_events_data_block() 포맷 테스트"""

    def test_empty_data_returns_empty(self):
        """빈 데이터 시 빈 문자열 반환"""
        assert _build_events_data_block(None) == ""
        assert _build_events_data_block({}) == ""

    def test_fomc_formatting(self):
        """FOMC 일정 포맷팅 확인"""
        data = {
            'fomc': {
                'next_date': '2026-03-18',
                'days_until': 17,
                'remaining_2026': ['2026-03-18', '2026-05-06', '2026-06-17'],
            },
            'earnings': {},
        }

        result = _build_events_data_block(data)

        assert '## 이벤트 캘린더' in result
        assert '다음 FOMC: 2026-03-18 (17일 후)' in result
        assert '2026년 남은 FOMC: 2회' in result

    def test_earnings_formatting(self):
        """실적발표 일정 포맷팅 확인"""
        data = {
            'fomc': {
                'next_date': None,
                'days_until': None,
                'remaining_2026': [],
            },
            'earnings': {
                'AAPL': {
                    'date': '2026-04-25',
                    'days_until': 55,
                    'estimate_eps': 1.52,
                    'estimate_revenue': 95000000000,
                },
                'MSFT': {
                    'date': '2026-05-10',
                    'days_until': 70,
                    'estimate_eps': None,
                    'estimate_revenue': None,
                },
            },
        }

        result = _build_events_data_block(data)

        assert 'AAPL 실적발표: 2026-04-25 (55일 후)' in result
        assert '컨센서스 EPS $1.52' in result
        assert 'MSFT 실적발표: 2026-05-10 (70일 후)' in result
        # MSFT has no EPS estimate
        assert '컨센서스 EPS' not in result.split('MSFT')[1] if 'MSFT' in result else True

    def test_earnings_sorted_by_days_until(self):
        """실적발표 일정이 days_until 순서로 정렬"""
        data = {
            'fomc': {'next_date': None, 'days_until': None, 'remaining_2026': []},
            'earnings': {
                'MSFT': {'date': '2026-05-10', 'days_until': 70, 'estimate_eps': None, 'estimate_revenue': None},
                'AAPL': {'date': '2026-04-25', 'days_until': 55, 'estimate_eps': None, 'estimate_revenue': None},
            },
        }

        result = _build_events_data_block(data)

        # AAPL (55일) should come before MSFT (70일)
        aapl_pos = result.find('AAPL')
        msft_pos = result.find('MSFT')
        assert aapl_pos < msft_pos

    def test_full_formatting(self):
        """전체 포맷팅 통합 확인"""
        data = {
            'fomc': {
                'next_date': '2026-03-18',
                'days_until': 17,
                'remaining_2026': ['2026-03-18', '2026-05-06'],
            },
            'earnings': {
                'AAPL': {
                    'date': '2026-04-25',
                    'days_until': 55,
                    'estimate_eps': 1.52,
                    'estimate_revenue': 95000000000,
                },
            },
        }

        result = _build_events_data_block(data)

        assert '## 이벤트 캘린더' in result
        assert '다음 FOMC' in result
        assert 'AAPL 실적발표' in result
        assert '예상 매출 $95,000,000,000' in result
