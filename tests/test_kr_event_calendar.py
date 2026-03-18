"""KREventCalendarCollector 테스트"""

import pytest
from datetime import datetime, date
from unittest.mock import patch

from trading_bot.kr_event_calendar import KREventCalendarCollector


class TestBOKRateSchedule:
    """금융통화위원회 일정 로직 테스트"""

    def test_bok_returns_next_date(self):
        """현재 날짜 기준 다음 금통위 일정을 올바르게 반환"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_bok_rate_schedule()

        assert result['next_date'] == '2026-02-27'
        assert result['days_until'] == 26  # 2026-02-01 -> 2026-02-27
        assert '2026-02-27' in result['remaining_2026']
        assert '2026-01-16' not in result['remaining_2026']

    def test_bok_all_past(self):
        """모든 금통위 일정이 지난 경우"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31)
            mock_dt.strptime = datetime.strptime

            result = collector._get_bok_rate_schedule()

        assert result['next_date'] is None
        assert result['days_until'] is None
        assert result['remaining_2026'] == []

    def test_bok_on_meeting_day(self):
        """금통위 당일"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10)
            mock_dt.strptime = datetime.strptime

            result = collector._get_bok_rate_schedule()

        assert result['next_date'] == '2026-04-10'
        assert result['days_until'] == 0

    def test_bok_remaining_count(self):
        """남은 금통위 일정 수"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_bok_rate_schedule()

        assert len(result['remaining_2026']) == 8  # 모두 미래

    def test_bok_dates_count(self):
        """금통위 연 8회"""
        assert len(KREventCalendarCollector.BOK_RATE_DATES_2026) == 8


class TestEconomicCalendar:
    """경제 지표 다음 일정 조회 테스트"""

    def test_next_cpi_date(self):
        """다음 CPI 일정 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['cpi']['next_date'] == '2026-03-04'
        assert result['cpi']['days_until'] == 2

    def test_next_gdp_date(self):
        """다음 GDP 일정 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['gdp']['next_date'] == '2026-04-23'
        assert result['gdp']['days_until'] == 81

    def test_next_trade_date(self):
        """다음 수출입 통계 일정 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        assert result['trade']['next_date'] == '2026-04-01'
        assert result['trade']['days_until'] == 17

    def test_all_economic_keys_present(self):
        """모든 경제 지표 키 존재"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        expected_keys = {'cpi', 'gdp', 'trade'}
        assert set(result.keys()) == expected_keys

    def test_economic_all_past(self):
        """2026년 지표 모두 지남"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2027, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_economic_calendar()

        for key, info in result.items():
            assert info['next_date'] is None
            assert info['days_until'] is None

    def test_next_date_from_list_on_exact_date(self):
        """정확히 해당 날짜에 조회하면 당일 반환"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 4)
            mock_dt.strptime = datetime.strptime

            result = collector._next_date_from_list(collector.KR_CPI_DATES_2026)

        assert result['next_date'] == '2026-03-04'
        assert result['days_until'] == 0


class TestOptionsExpiry:
    """옵션만기일 테스트"""

    def test_next_options_expiry(self):
        """다음 옵션 만기일 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['monthly_expiry']['next_date'] == '2026-03-12'
        assert result['monthly_expiry']['days_until'] == 11

    def test_options_expiry_on_day(self):
        """옵션만기 당일"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 12)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['monthly_expiry']['next_date'] == '2026-03-12'
        assert result['monthly_expiry']['days_until'] == 0

    def test_options_expiry_after_this_month(self):
        """이달 만기 이후 -> 다음달 만기"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 13)
            mock_dt.strptime = datetime.strptime

            result = collector._get_options_expiry()

        assert result['monthly_expiry']['next_date'] == '2026-04-09'

    def test_options_expiry_count(self):
        """옵션만기 연 12회"""
        assert len(KREventCalendarCollector.KR_OPTIONS_EXPIRY) == 12


class TestMarketStructure:
    """KOSPI200 정기변경 테스트"""

    def test_next_krx_rebalance(self):
        """다음 KOSPI200 정기변경 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        assert result['krx_rebalance']['next_date'] == '2026-06-12'

    def test_krx_rebalance_after_june(self):
        """6월 이후 -> 12월 리밸런싱"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        assert result['krx_rebalance']['next_date'] == '2026-12-11'

    def test_krx_rebalance_all_past(self):
        """모든 리밸런싱 지남"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31)
            mock_dt.strptime = datetime.strptime

            result = collector._get_market_structure_events()

        assert result['krx_rebalance']['next_date'] is None

    def test_krx_rebalance_count(self):
        """KOSPI200 정기변경 연 2회"""
        assert len(KREventCalendarCollector.KRX_REBALANCE_DATES) == 2


class TestHolidays:
    """KRX 공휴일 테스트"""

    def test_next_holiday(self):
        """다음 공휴일 조회"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] == '2026-05-05'
        assert result['next_holiday']['name'] == '어린이날'

    def test_holiday_on_day(self):
        """공휴일 당일"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] == '2026-01-01'
        assert result['next_holiday']['days_until'] == 0

    def test_all_holidays_past(self):
        """모든 공휴일 지남"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31)
            mock_dt.strptime = datetime.strptime

            result = collector._get_next_holiday()

        assert result['next_holiday']['date'] is None

    def test_holiday_count(self):
        """2026년 KRX 공휴일 15일"""
        assert len(KREventCalendarCollector.KRX_HOLIDAYS_2026) == 15

    def test_lunar_new_year_included(self):
        """설날 연휴 포함"""
        holidays = KREventCalendarCollector.KRX_HOLIDAYS_2026
        assert '2026-01-28' in holidays  # 설날
        assert holidays['2026-01-28'] == '설날'

    def test_chuseok_included(self):
        """추석 연휴 포함"""
        holidays = KREventCalendarCollector.KRX_HOLIDAYS_2026
        assert '2026-09-25' in holidays  # 추석
        assert holidays['2026-09-25'] == '추석'


class TestCollect:
    """collect() 메서드 통합 테스트"""

    def test_collect_returns_structure(self):
        """collect() 반환값 구조 확인"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect()

        assert result is not None
        expected_keys = {
            'collected_at', 'bok_rate', 'economic',
            'options', 'market_structure', 'holidays',
        }
        assert set(result.keys()) == expected_keys

    def test_collect_bok_rate_structure(self):
        """bok_rate 하위 키 구조"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect()

        bok = result['bok_rate']
        assert 'next_date' in bok
        assert 'days_until' in bok
        assert 'remaining_2026' in bok

    def test_collect_economic_structure(self):
        """economic 하위 키 구조"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect()

        economic = result['economic']
        assert 'cpi' in economic
        assert 'gdp' in economic
        assert 'trade' in economic

        for key, info in economic.items():
            assert 'next_date' in info
            assert 'days_until' in info

    def test_collect_options_structure(self):
        """options 구조 확인"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect()

        options = result['options']
        assert 'monthly_expiry' in options
        assert 'next_date' in options['monthly_expiry']
        assert 'days_until' in options['monthly_expiry']

    def test_collect_holidays_structure(self):
        """holidays 구조 확인"""
        collector = KREventCalendarCollector()

        with patch('trading_bot.kr_event_calendar.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1)
            mock_dt.strptime = datetime.strptime

            result = collector.collect()

        holidays = result['holidays']
        assert 'next_holiday' in holidays
        nh = holidays['next_holiday']
        assert 'date' in nh
        assert 'name' in nh
        assert 'days_until' in nh

    def test_collect_exception_returns_none(self):
        """collect() 내부 예외 시 None 반환"""
        collector = KREventCalendarCollector()

        with patch.object(collector, '_get_bok_rate_schedule', side_effect=Exception("Critical")):
            result = collector.collect()

        assert result is None


class TestSecondWeekday:
    """둘째 특정 요일 계산 정확성"""

    def test_second_thursday_january_2026(self):
        """2026년 1월 둘째 목요일"""
        result = KREventCalendarCollector._second_weekday_of_month(2026, 1, 3)
        assert result == date(2026, 1, 8)

    def test_second_thursday_march_2026(self):
        """2026년 3월 둘째 목요일"""
        result = KREventCalendarCollector._second_weekday_of_month(2026, 3, 3)
        assert result == date(2026, 3, 12)

    def test_second_friday_june_2026(self):
        """2026년 6월 둘째 금요일"""
        result = KREventCalendarCollector._second_weekday_of_month(2026, 6, 4)
        assert result == date(2026, 6, 12)

    def test_result_is_correct_weekday(self):
        """반환된 날짜가 정확한 요일인지"""
        for month in range(1, 13):
            thursday = KREventCalendarCollector._second_weekday_of_month(2026, month, 3)
            assert thursday.weekday() == 3  # 목요일
            friday = KREventCalendarCollector._second_weekday_of_month(2026, month, 4)
            assert friday.weekday() == 4  # 금요일

    def test_second_weekday_is_between_8_and_14(self):
        """둘째 요일은 항상 8~14일 사이"""
        for month in range(1, 13):
            for weekday in range(5):
                d = KREventCalendarCollector._second_weekday_of_month(2026, month, weekday)
                assert 8 <= d.day <= 14


class TestDateCounts:
    """날짜 리스트 개수 검증"""

    def test_cpi_dates_count(self):
        """CPI 발표일 연 12회"""
        assert len(KREventCalendarCollector.KR_CPI_DATES_2026) == 12

    def test_gdp_dates_count(self):
        """GDP 발표일 연 4회"""
        assert len(KREventCalendarCollector.KR_GDP_DATES_2026) == 4

    def test_trade_dates_count(self):
        """수출입 통계 발표일 연 12회"""
        assert len(KREventCalendarCollector.KR_TRADE_DATES_2026) == 12
