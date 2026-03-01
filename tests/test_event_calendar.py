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

    def test_fomc_dates_corrected(self):
        """FOMC 날짜 수정 확인 (Fed 공식 캘린더)"""
        dates = EventCalendarCollector.FOMC_DATES_2026
        assert '2026-04-29' in dates  # 기존 05-06에서 수정
        assert '2026-10-28' in dates  # 기존 11-04에서 수정
        assert '2026-12-09' in dates  # 기존 12-16에서 수정
        assert '2026-05-06' not in dates
        assert '2026-11-04' not in dates
        assert '2026-12-16' not in dates


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
            'remaining_2026': ['2026-03-18', '2026-04-29'],
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
                'remaining_2026': ['2026-03-18', '2026-04-29', '2026-06-17'],
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

        assert 'AAPL: 2026-04-25 (55일 후)' in result
        assert '컨센서스 EPS $1.52' in result
        assert 'MSFT: 2026-05-10 (70일 후)' in result

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
                'remaining_2026': ['2026-03-18', '2026-04-29'],
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
        assert 'AAPL' in result
        assert '예상 매출 $95,000,000,000' in result

    def test_warning_for_7day_proximity(self):
        """7일 이내 이벤트에 ⚠️ 표시"""
        data = {
            'economic': {
                'nfp': {'next_date': '2026-03-06', 'days_until': 4},
                'cpi': {'next_date': '2026-03-11', 'days_until': 9},
            },
        }

        result = _build_events_data_block(data)

        assert 'NFP (고용): 2026-03-06 (4일 후) ⚠️' in result
        assert '⚠️' not in result.split('CPI')[1] if 'CPI' in result else True

    def test_options_section(self):
        """옵션/파생 섹션 포맷팅"""
        data = {
            'options': {
                'monthly_expiry': {'next_date': '2026-03-20', 'days_until': 18},
                'is_quad_witching': True,
            },
            'vix_expiry': {'next_date': '2026-03-18', 'days_until': 16},
        }

        result = _build_events_data_block(data)

        assert '### 옵션/파생' in result
        assert '[Quad Witching]' in result
        assert 'VIX 만기' in result

    def test_market_structure_section(self):
        """시장 구조 섹션 포맷팅"""
        data = {
            'market_structure': {
                'sp500_rebalance': {'next_date': '2026-03-20', 'days_until': 18},
                'russell_rebalance': {'next_date': '2026-06-26', 'days_until': 116},
            },
            'holidays': {
                'next_holiday': {'date': '2026-04-03', 'name': 'Good Friday', 'days_until': 32},
            },
        }

        result = _build_events_data_block(data)

        assert '### 시장 구조' in result
        assert 'S&P 500 리밸런싱' in result
        assert 'Russell 리밸런싱' in result
        assert 'Good Friday' in result

    def test_backward_compat_old_data(self):
        """기존 데이터 (FOMC + 실적만) 하위호환"""
        data = {
            'fomc': {
                'next_date': '2026-03-18',
                'days_until': 17,
                'remaining_2026': ['2026-03-18'],
            },
            'earnings': {
                'AAPL': {
                    'date': '2026-04-25',
                    'days_until': 55,
                    'estimate_eps': 1.52,
                    'estimate_revenue': None,
                },
            },
        }

        result = _build_events_data_block(data)

        assert '## 이벤트 캘린더' in result
        assert '다음 FOMC' in result
        assert 'AAPL' in result
        # 새 섹션은 키가 없으므로 나타나지 않아야 함
        assert '### 매크로 경제 지표' not in result
        assert '### 옵션/파생' not in result


class TestThirdWeekday:
    """셋째 특정 요일 계산 정확성"""

    def test_third_friday_march_2026(self):
        """2026년 3월 셋째 금요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 3, 4)
        assert result == date(2026, 3, 20)

    def test_third_friday_june_2026(self):
        """2026년 6월 셋째 금요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 6, 4)
        assert result == date(2026, 6, 19)

    def test_third_wednesday_march_2026(self):
        """2026년 3월 셋째 수요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 3, 2)
        assert result == date(2026, 3, 18)

    def test_third_friday_january_2026(self):
        """2026년 1월 셋째 금요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 1, 4)
        assert result == date(2026, 1, 16)

    def test_third_friday_september_2026(self):
        """2026년 9월 셋째 금요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 9, 4)
        assert result == date(2026, 9, 18)

    def test_third_friday_december_2026(self):
        """2026년 12월 셋째 금요일"""
        result = EventCalendarCollector._third_weekday_of_month(2026, 12, 4)
        assert result == date(2026, 12, 18)

    def test_result_is_correct_weekday(self):
        """반환된 날짜가 정확한 요일인지"""
        for month in range(1, 13):
            friday = EventCalendarCollector._third_weekday_of_month(2026, month, 4)
            assert friday.weekday() == 4  # 금요일
            wednesday = EventCalendarCollector._third_weekday_of_month(2026, month, 2)
            assert wednesday.weekday() == 2  # 수요일

    def test_third_weekday_is_between_15_and_21(self):
        """셋째 요일은 항상 15~21일 사이"""
        for month in range(1, 13):
            for weekday in range(5):
                d = EventCalendarCollector._third_weekday_of_month(2026, month, weekday)
                assert 15 <= d.day <= 21


class TestOptionsExpiry:
    """옵션 만기 + Quad Witching 테스트"""

    def test_next_options_expiry(self):
        """다음 옵션 만기일 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['monthly_expiry']['next_date'] == '2026-03-20'
        assert result['monthly_expiry']['days_until'] == 19

    def test_quad_witching_true_in_march(self):
        """3월은 Quad Witching"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['is_quad_witching'] is True

    def test_quad_witching_false_in_february(self):
        """2월은 Quad Witching 아님"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['is_quad_witching'] is False

    def test_quad_witching_months(self):
        """3/6/9/12월만 Quad Witching"""
        collector = EventCalendarCollector()

        for month, expected_quad in [(3, True), (4, False), (6, True),
                                      (7, False), (9, True), (10, False), (12, True)]:
            with patch('trading_bot.event_calendar.datetime') as mock_dt:
                mock_dt.now.return_value = datetime(2026, month, 1)
                mock_dt.strptime = datetime.strptime

                result = collector._get_options_expiry()

            assert result['is_quad_witching'] is expected_quad, f"Month {month}: expected {expected_quad}"

    def test_options_expiry_on_expiry_day(self):
        """만기일 당일"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 20)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['monthly_expiry']['next_date'] == '2026-03-20'
        assert result['monthly_expiry']['days_until'] == 0

    def test_options_expiry_after_this_month(self):
        """이달 만기 이후 → 다음달 만기"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 21)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        # 4월 셋째 금요일
        assert result['monthly_expiry']['next_date'] == '2026-04-17'


class TestVIXExpiry:
    """VIX 만기 (셋째 수요일) 테스트"""

    def test_next_vix_expiry(self):
        """다음 VIX 만기일 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_vix_expiry()

        assert result['next_date'] == '2026-03-18'
        assert result['days_until'] == 17

    def test_vix_expiry_after_this_month(self):
        """이달 VIX 만기 이후 → 다음달"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 19)
            mock_dt.strptime = datetime.strptime

            result = collector._get_vix_expiry()

        # 4월 셋째 수요일
        assert result['next_date'] == '2026-04-15'

    def test_vix_expiry_on_day(self):
        """VIX 만기 당일"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 18)
            mock_dt.strptime = datetime.strptime

            result = collector._get_vix_expiry()

        assert result['next_date'] == '2026-03-18'
        assert result['days_until'] == 0


class TestFOMCMinutes:
    """FOMC 의사록 (21일 후) 테스트"""

    def test_fomc_minutes_after_meeting(self):
        """FOMC 회의 후 21일 뒤 의사록 날짜"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            # 2026-01-28 FOMC 직후
            mock_dt.now.return_value = datetime(2026, 1, 29)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_minutes()

        # 2026-01-28 + 21일 = 2026-02-18
        assert result['next_date'] == '2026-02-18'
        assert result['days_until'] == 20  # 01-29 → 02-18

    def test_fomc_minutes_before_first_meeting(self):
        """첫 FOMC 전 → 첫 회의 + 21일"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_minutes()

        # 2026-01-28 + 21 = 2026-02-18
        assert result['next_date'] == '2026-02-18'
        assert result['days_until'] == 48  # 01-01 → 02-18

    def test_fomc_minutes_all_past(self):
        """모든 FOMC 의사록 일정 지남"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2027, 2, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_fomc_minutes()

        assert result['next_date'] is None
        assert result['days_until'] is None

    def test_fomc_minutes_21_day_gap(self):
        """각 FOMC의 의사록은 정확히 21일 후"""
        collector = EventCalendarCollector()

        for fomc_date_str in collector.FOMC_DATES_2026:
            fomc_date = datetime.strptime(fomc_date_str, '%Y-%m-%d')
            expected_minutes = fomc_date.date() + __import__('datetime').timedelta(days=21)

            with patch('trading_bot.event_calendar.datetime') as mock_dt:
                # FOMC 당일에 조회
                mock_dt.now.return_value = fomc_date
                mock_dt.strptime = datetime.strptime

                result = collector._get_fomc_minutes()

            assert result['next_date'] == expected_minutes.strftime('%Y-%m-%d')


class TestEconomicCalendar:
    """경제 지표 다음 일정 조회 테스트"""

    def test_next_cpi_date(self):
        """다음 CPI 일정 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['cpi']['next_date'] == '2026-03-11'
        assert result['cpi']['days_until'] == 9

    def test_next_nfp_date(self):
        """다음 NFP 일정 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['nfp']['next_date'] == '2026-03-06'
        assert result['nfp']['days_until'] == 4

    def test_all_economic_keys_present(self):
        """모든 경제 지표 키 존재"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        expected_keys = {'cpi', 'nfp', 'ppi', 'pce', 'gdp',
                         'ism_manufacturing', 'ism_services', 'jackson_hole'}
        assert set(result.keys()) == expected_keys

    def test_economic_all_past(self):
        """2026년 지표 모두 지남"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2027, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        for key, info in result.items():
            assert info['next_date'] is None
            assert info['days_until'] is None

    def test_jackson_hole(self):
        """잭슨홀 일정 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['jackson_hole']['next_date'] == '2026-08-20'

    def test_next_date_from_list_on_exact_date(self):
        """정확히 해당 날짜에 조회하면 당일 반환"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 6)
            mock_dt.strptime = datetime.strptime

            result = collector._next_date_from_list(collector.NFP_DATES_2026)

        assert result['next_date'] == '2026-03-06'
        assert result['days_until'] == 0


class TestMarketStructure:
    """S&P 500/Russell 리밸런싱 테스트"""

    def test_sp500_rebalance_next(self):
        """다음 S&P 500 리밸런싱 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        # 3월 셋째 금요일 = 2026-03-20
        assert result['sp500_rebalance']['next_date'] == '2026-03-20'

    def test_sp500_rebalance_quad_months_only(self):
        """S&P 리밸런싱은 3/6/9/12월만"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        # 4월 이후 다음 분기 리밸런싱 = 6월 셋째 금요일
        assert result['sp500_rebalance']['next_date'] == '2026-06-19'

    def test_russell_rebalance(self):
        """Russell 리밸런싱 (6월 마지막 금요일)"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        # 2026년 6월 마지막 금요일 = 2026-06-26
        assert result['russell_rebalance']['next_date'] == '2026-06-26'

    def test_russell_rebalance_after_june(self):
        """6월 이후 → 다음해 6월"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        # 다음해 6월 마지막 금요일
        assert result['russell_rebalance']['next_date'].startswith('2027-06')


class TestHolidays:
    """NYSE 공휴일 테스트"""

    def test_next_holiday(self):
        """다음 공휴일 조회"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] == '2026-04-03'
        assert result['next_holiday']['name'] == 'Good Friday'

    def test_holiday_on_day(self):
        """공휴일 당일"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] == '2026-01-01'
        assert result['next_holiday']['days_until'] == 0

    def test_all_holidays_past(self):
        """모든 공휴일 지남"""
        collector = EventCalendarCollector()

        with patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] is None

    def test_holiday_count(self):
        """2026년 NYSE 공휴일 10일"""
        assert len(EventCalendarCollector.NYSE_HOLIDAYS_2026) == 10


class TestCollectExtended:
    """확장된 collect() 전체 구조 검증"""

    def test_collect_has_all_new_keys(self):
        """collect() 반환값에 모든 새 키 포함"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={}), \
             patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect(['AAPL'])

        assert result is not None
        expected_keys = {
            'collected_at', 'earnings', 'fomc', 'fomc_minutes',
            'economic', 'options', 'vix_expiry', 'market_structure', 'holidays',
        }
        assert set(result.keys()) == expected_keys

    def test_collect_economic_structure(self):
        """economic 하위 키 구조"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={}), \
             patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect(['AAPL'])

        economic = result['economic']
        assert 'cpi' in economic
        assert 'nfp' in economic
        assert 'ppi' in economic
        assert 'pce' in economic
        assert 'gdp' in economic
        assert 'ism_manufacturing' in economic
        assert 'ism_services' in economic
        assert 'jackson_hole' in economic

        # 각 항목에 next_date, days_until 존재
        for key, info in economic.items():
            assert 'next_date' in info
            assert 'days_until' in info

    def test_collect_options_structure(self):
        """options 구조 확인"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={}), \
             patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect(['AAPL'])

        options = result['options']
        assert 'monthly_expiry' in options
        assert 'is_quad_witching' in options
        assert 'next_date' in options['monthly_expiry']
        assert 'days_until' in options['monthly_expiry']
        assert isinstance(options['is_quad_witching'], bool)

    def test_collect_holidays_structure(self):
        """holidays 구조 확인"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={}), \
             patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect(['AAPL'])

        holidays = result['holidays']
        assert 'next_holiday' in holidays
        nh = holidays['next_holiday']
        assert 'date' in nh
        assert 'name' in nh
        assert 'days_until' in nh

    def test_collect_fomc_minutes_structure(self):
        """fomc_minutes 구조 확인"""
        collector = EventCalendarCollector(api_delay=0)

        with patch.object(collector, '_fetch_earnings', return_value={}), \
             patch('trading_bot.event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect(['AAPL'])

        fm = result['fomc_minutes']
        assert 'next_date' in fm
        assert 'days_until' in fm
