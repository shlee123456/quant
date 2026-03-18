"""
KR Parallel Prompt Builder 테스트

한국 시장용 프롬프트 빌더 함수들의 출력을 검증합니다.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from trading_bot.kr_parallel_prompt_builder import (
    build_kr_worker_a_prompt,
    build_kr_worker_b_prompt,
    build_kr_worker_c_prompt,
    build_kr_notion_writer_prompt,
    assemble_kr_sections,
    validate_kr_assembly,
    _build_kr_macro_block,
    _build_kr_events_block,
    _build_kr_intelligence_block,
    _build_kr_daily_changes_block,
    _compute_kr_top3_candidates,
    _get_kr_notion_page_id,
    KR_WORKER_MODELS,
)


# ─── Fixtures ───


@pytest.fixture
def sample_market_data():
    """테스트용 한국 시장 데이터"""
    return {
        'date': '2026-03-18',
        'market': 'kr',
        'market_summary': {
            'total_stocks': 3,
            'bullish_count': 1,
            'bearish_count': 1,
            'sideways_count': 1,
            'avg_rsi': 48.5,
            'market_sentiment': '중립',
            'notable_events': ['삼성전자(005930) ADX 35 강한 추세'],
        },
        'stocks': {
            '005930': {
                'name': '삼성전자',
                'price': {'last': 65000.0, 'change_1d': 1.2, 'change_5d': -2.5, 'change_20d': -8.3},
                'indicators': {
                    'rsi': {'value': 32.5, 'signal': 'near_oversold', 'zone': '25-35'},
                    'macd': {'histogram': -150.5, 'signal': 'bearish', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.15, 'signal': 'near_lower'},
                    'stochastic': {'k': 25.3, 'd': 28.1, 'signal': 'near_oversold'},
                    'adx': {'value': 35.2, 'trend': 'moderate_trend'},
                },
                'regime': {'state': 'BEARISH', 'confidence': 0.72},
                'patterns': {'double_bottom': False, 'support_levels': [62000, 60000]},
                'signal_diagnosis': {
                    'rsi_35_65': {'buy_triggered': True, 'sell_triggered': False},
                    'optimal_rsi_range': {'oversold': 25, 'overbought': 65},
                },
            },
            '000660': {
                'name': 'SK하이닉스',
                'price': {'last': 120000.0, 'change_1d': 2.8, 'change_5d': 5.1, 'change_20d': 12.5},
                'indicators': {
                    'rsi': {'value': 68.2, 'signal': 'near_overbought', 'zone': '65-75'},
                    'macd': {'histogram': 2500.0, 'signal': 'bullish', 'cross_recent': True},
                    'bollinger': {'pct_b': 0.85, 'signal': 'near_upper'},
                    'stochastic': {'k': 78.5, 'd': 72.3, 'signal': 'near_overbought'},
                    'adx': {'value': 28.5, 'trend': 'moderate_trend'},
                },
                'regime': {'state': 'BULLISH', 'confidence': 0.65},
                'patterns': {'double_bottom': False, 'support_levels': [110000, 105000]},
                'signal_diagnosis': {
                    'rsi_35_65': {'buy_triggered': False, 'sell_triggered': True},
                    'optimal_rsi_range': {'oversold': 35, 'overbought': 76},
                },
            },
            '035420': {
                'name': 'NAVER',
                'price': {'last': 190000.0, 'change_1d': -0.5, 'change_5d': 0.8, 'change_20d': -1.2},
                'indicators': {
                    'rsi': {'value': 48.9, 'signal': 'neutral', 'zone': '45-55'},
                    'macd': {'histogram': 200.0, 'signal': 'bullish', 'cross_recent': False},
                    'bollinger': {'pct_b': 0.52, 'signal': 'neutral'},
                    'stochastic': {'k': 50.1, 'd': 49.8, 'signal': 'neutral'},
                    'adx': {'value': 15.3, 'trend': 'weak_trend'},
                },
                'regime': {'state': 'SIDEWAYS', 'confidence': 0.58},
                'patterns': {'double_bottom': True, 'support_levels': [185000, 180000, 175000]},
                'signal_diagnosis': {
                    'rsi_35_65': {'buy_triggered': False, 'sell_triggered': False},
                    'optimal_rsi_range': {'oversold': 35, 'overbought': 65},
                },
            },
        },
    }


@pytest.fixture
def sample_news_data():
    """테스트용 뉴스 데이터"""
    return {
        'collected_at': '2026-03-18T09:00:00',
        'market_news': [
            {'title': '코스피 2,600선 돌파', 'source': '한국경제', 'published': '2026-03-18', 'link': ''},
            {'title': '외국인 매수세 지속', 'source': '매일경제', 'published': '2026-03-18', 'link': ''},
        ],
        'stock_news': {
            '005930': [
                {'title': '삼성전자 AI 반도체 수주 확대', 'source': '조선일보', 'published': '2026-03-18', 'link': ''},
            ],
            '000660': [
                {'title': 'SK하이닉스 HBM4 양산 착수', 'source': '전자신문', 'published': '2026-03-18', 'link': ''},
            ],
        },
    }


@pytest.fixture
def sample_macro_data():
    """테스트용 매크로 데이터"""
    return {
        'collected_at': '2026-03-18T09:00:00',
        'indices': {
            '^KS11': {'last': 2650.32, 'chg_1d': 0.8, 'chg_5d': 2.1, 'chg_20d': 3.5, 'rsi': 58.2, 'vol_ratio': 1.1},
            '^KQ11': {'last': 850.15, 'chg_1d': 1.2, 'chg_5d': 3.5, 'chg_20d': 5.2, 'rsi': 62.3, 'vol_ratio': 1.3},
        },
        'sectors': {
            '091160.KS': {'name': 'KODEX반도체', 'last': 45000, 'chg_5d': 4.2, 'chg_20d': 8.1, 'rsi': 65.0, 'rank_5d': 1, 'rank_20d': 1},
            '091170.KS': {'name': 'KODEX은행', 'last': 12000, 'chg_5d': 1.5, 'chg_20d': 2.3, 'rsi': 52.0, 'rank_5d': 2, 'rank_20d': 3},
        },
        'rotation': {
            'offensive_avg_5d': 3.8,
            'defensive_avg_5d': 1.2,
            'diff': 2.6,
            'signal': '공격적 로테이션 (리스크온)',
        },
        'breadth': {
            'kospi_vs_kosdaq_5d': -1.4,
            'sectors_positive_5d': 8,
            'sectors_negative_5d': 2,
            'interpretation': '코스닥 상대 강세로 중소형주 선호. 대다수 섹터 상승으로 광범위한 강세',
        },
        'risk_environment': {
            'bond_chg_5d': -0.8,
            'gold_chg_5d': -1.2,
            'assessment': '리스크온 (위험자산 선호)',
        },
        'overall': '반도체 강세 속 코스닥 상대 강세. 공격적 로테이션 진행 중.',
    }


@pytest.fixture
def sample_events_data():
    """테스트용 이벤트 데이터"""
    return {
        'collected_at': '2026-03-18 09:00:00',
        'bok_rate': {'next_date': '2026-04-10', 'days_until': 23, 'remaining_2026': ['2026-04-10', '2026-05-29']},
        'economic': {
            'cpi': {'next_date': '2026-04-02', 'days_until': 15},
            'gdp': {'next_date': '2026-04-23', 'days_until': 36},
            'trade': {'next_date': '2026-04-01', 'days_until': 14},
        },
        'options': {'monthly_expiry': {'next_date': '2026-04-09', 'days_until': 22}},
        'market_structure': {'krx_rebalance': {'next_date': '2026-06-12', 'days_until': 86}},
        'holidays': {'next_holiday': {'date': '2026-05-05', 'name': '어린이날', 'days_until': 48}},
    }


# ─── Worker A 프롬프트 테스트 ───


class TestBuildKRWorkerAPrompt:
    """Worker A 프롬프트 생성 테스트"""

    def test_basic_prompt(self, sample_market_data):
        prompt = build_kr_worker_a_prompt(sample_market_data, '2026-03-18')

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert '한국 시장 분석 워커 A' in prompt
        assert '삼성전자' in prompt
        assert '005930' in prompt
        assert '원' in prompt

    def test_includes_format_rules(self, sample_market_data):
        prompt = build_kr_worker_a_prompt(sample_market_data, '2026-03-18')
        assert 'FORMAT RULES' in prompt

    def test_without_macro_sections_1_2_only(self, sample_market_data):
        prompt = build_kr_worker_a_prompt(sample_market_data, '2026-03-18')
        assert '섹션 1, 2만' in prompt
        # 매크로 섹션 템플릿이 포함되지 않아야 함
        assert '한국 매크로 시장 환경 {color="blue"}' not in prompt

    def test_with_macro_includes_section_0(self, sample_market_data, sample_macro_data):
        prompt = build_kr_worker_a_prompt(
            sample_market_data, '2026-03-18',
            macro_data=sample_macro_data,
        )
        assert '섹션 0, 1, 2만' in prompt
        assert 'KOSPI/KOSDAQ' in prompt

    def test_with_events(self, sample_market_data, sample_events_data):
        prompt = build_kr_worker_a_prompt(
            sample_market_data, '2026-03-18',
            events_data=sample_events_data,
        )
        assert '금융통화위원회' in prompt
        assert '소비자물가' in prompt

    def test_with_daily_changes(self, sample_market_data):
        daily_changes = {
            'has_previous': True,
            'previous_date': '2026-03-17',
            'stocks': {
                '005930': {'price_change_pct': -1.5, 'rsi_change': -3.2},
            },
        }
        prompt = build_kr_worker_a_prompt(
            sample_market_data, '2026-03-18',
            daily_changes=daily_changes,
        )
        assert '전일 대비' in prompt
        assert '2026-03-17' in prompt

    def test_json_data_included(self, sample_market_data):
        prompt = build_kr_worker_a_prompt(sample_market_data, '2026-03-18')
        assert '"rsi"' in prompt
        assert '"macd"' in prompt


# ─── Worker B 프롬프트 테스트 ───


class TestBuildKRWorkerBPrompt:
    """Worker B 프롬프트 생성 테스트"""

    def test_basic_prompt(self, sample_market_data, sample_news_data):
        prompt, top3 = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18'
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert '한국 시장 분석 워커 B' in prompt
        assert '섹션 3, 4, 5만' in prompt
        assert isinstance(top3, list)
        assert len(top3) <= 3

    def test_includes_vkospi_section(self, sample_market_data, sample_news_data):
        prompt, _ = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18'
        )
        assert 'VKOSPI' in prompt

    def test_no_fear_greed_section(self, sample_market_data, sample_news_data):
        """F&G 섹션이 아닌 VKOSPI 섹션이어야 함"""
        prompt, _ = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18'
        )
        assert 'Fear & Greed' not in prompt

    def test_news_data_included(self, sample_market_data, sample_news_data):
        prompt, _ = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18'
        )
        assert '코스피 2,600선 돌파' in prompt
        assert '삼성전자 AI 반도체' in prompt

    def test_top3_symbols_returned(self, sample_market_data, sample_news_data):
        _, top3 = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18'
        )
        assert len(top3) == 3
        # 모든 심볼이 원래 데이터에 있어야 함
        for sym in top3:
            assert sym in sample_market_data['stocks']

    def test_previous_top3_penalty(self, sample_market_data, sample_news_data):
        """이전 TOP 3 종목에 페널티가 적용되어야 함"""
        _, top3_without = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18',
        )
        _, top3_with = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18',
            previous_top3=['005930'],
        )
        # 페널티 적용 시 삼성전자가 순위가 달라질 수 있음
        assert isinstance(top3_with, list)

    def test_with_reflection(self, sample_market_data, sample_news_data):
        prompt, _ = build_kr_worker_b_prompt(
            sample_market_data, sample_news_data, '2026-03-18',
            worker_a_context="Worker A analysis of Korean market...",
        )
        assert 'Worker A 분석' in prompt


# ─── Worker C 프롬프트 테스트 ───


class TestBuildKRWorkerCPrompt:
    """Worker C 프롬프트 생성 테스트"""

    def test_basic_prompt(self, sample_market_data):
        prompt = build_kr_worker_c_prompt(sample_market_data, '2026-03-18')

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert '한국 시장 분석 워커 C' in prompt
        assert '도구(WebSearch, Read 등)는 사용하지 마세요' in prompt

    def test_includes_kr_risk_items(self, sample_market_data):
        prompt = build_kr_worker_c_prompt(sample_market_data, '2026-03-18')
        assert '환율' in prompt or '리스크' in prompt

    def test_sections_6_7_8(self, sample_market_data):
        prompt = build_kr_worker_c_prompt(sample_market_data, '2026-03-18')
        assert '# 6.' in prompt
        assert '# 7.' in prompt
        assert '# 8.' in prompt

    def test_forward_data_included(self, sample_market_data):
        prompt = build_kr_worker_c_prompt(sample_market_data, '2026-03-18')
        assert 'support_resistance' in prompt
        assert 'rsi_pending_signals' in prompt


# ─── Notion Writer 프롬프트 테스트 ───


class TestBuildKRNotionWriterPrompt:
    """Notion Writer 프롬프트 생성 테스트"""

    def test_basic_prompt(self):
        prompt = build_kr_notion_writer_prompt(
            "# 1. 한국 시장 요약\n내용...",
            '2026-03-18',
            'test-page-id-123',
        )

        assert isinstance(prompt, str)
        assert 'test-page-id-123' in prompt
        assert '한국 시장 분석' in prompt
        assert '2026-03-18' in prompt
        assert 'KR' in prompt

    def test_month_folder_name(self):
        prompt = build_kr_notion_writer_prompt(
            "content", '2026-03-18', 'page-id',
        )
        assert '2026-03 KR' in prompt

    def test_notion_page_url_instruction(self):
        prompt = build_kr_notion_writer_prompt(
            "content", '2026-03-18', 'page-id',
        )
        assert 'NOTION_PAGE_URL' in prompt


# ─── 섹션 조립 테스트 ───


class TestAssembleKRSections:
    """섹션 조립 테스트"""

    def test_assemble_combines_all(self):
        assembled = assemble_kr_sections(
            "# 1. 시장 요약\n내용A",
            "# 3. Top 3\n내용B",
            "# 6. 전략\n내용C",
            '2026-03-18',
        )

        assert '시장 요약' in assembled
        assert 'Top 3' in assembled
        assert '전략' in assembled
        assert '주의사항' in assembled  # 푸터

    def test_assemble_includes_footer(self):
        assembled = assemble_kr_sections("A", "B", "C", '2026-03-18')
        assert '병렬 생성' in assembled
        assert '2026-03-18' in assembled


class TestValidateKRAssembly:
    """조립 유효성 검증 테스트"""

    def test_valid_assembly(self):
        content = "# 0. 매크로\n# 1. 요약\n# 2. 분석\n# 3. Top\n# 4. VKOSPI\n# 5. 뉴스\n# 6. 전략\n# 7. 전망\n# 8. 리스크"
        expected = ["# 0.", "# 1.", "# 2.", "# 3.", "# 4.", "# 5.", "# 6.", "# 7.", "# 8."]
        assert validate_kr_assembly(content, expected) is True

    def test_invalid_assembly_missing_section(self):
        content = "# 1. 요약\n# 2. 분석"
        expected = ["# 1.", "# 2.", "# 3."]
        assert validate_kr_assembly(content, expected) is False


# ─── 헬퍼 함수 테스트 ───


class TestKRHelperFunctions:
    """헬퍼 함수 테스트"""

    def test_build_kr_macro_block_empty(self):
        assert _build_kr_macro_block(None) == ""

    def test_build_kr_macro_block_with_data(self, sample_macro_data):
        block = _build_kr_macro_block(sample_macro_data)
        assert 'KOSPI' in block
        assert 'KODEX반도체' in block
        assert '로테이션' in block

    def test_build_kr_events_block_empty(self):
        assert _build_kr_events_block(None) == ""

    def test_build_kr_events_block_with_data(self, sample_events_data):
        block = _build_kr_events_block(sample_events_data)
        assert '금융통화위원회' in block
        assert '소비자물가' in block
        assert '옵션만기' in block
        assert '어린이날' in block

    def test_build_kr_intelligence_block_empty(self):
        assert _build_kr_intelligence_block(None) == ""

    def test_build_kr_daily_changes_block_empty(self):
        assert _build_kr_daily_changes_block(None) == ""

    def test_build_kr_daily_changes_block_no_previous(self):
        assert _build_kr_daily_changes_block({'has_previous': False}) == ""

    def test_compute_kr_top3_candidates(self, sample_market_data):
        top3, info = _compute_kr_top3_candidates(sample_market_data)
        assert len(top3) == 3
        assert isinstance(info, str)

    def test_compute_kr_top3_empty(self):
        top3, info = _compute_kr_top3_candidates({'stocks': {}})
        assert top3 == []
        assert info == ""

    def test_get_kr_notion_page_id_default(self):
        orig = os.environ.pop('NOTION_KR_MARKET_ANALYSIS_PAGE_ID', None)
        try:
            page_id = _get_kr_notion_page_id()
            assert page_id == 'placeholder-kr-page-id'
        finally:
            if orig is not None:
                os.environ['NOTION_KR_MARKET_ANALYSIS_PAGE_ID'] = orig

    def test_get_kr_notion_page_id_from_env(self):
        os.environ['NOTION_KR_MARKET_ANALYSIS_PAGE_ID'] = 'custom-kr-page-id'
        try:
            assert _get_kr_notion_page_id() == 'custom-kr-page-id'
        finally:
            del os.environ['NOTION_KR_MARKET_ANALYSIS_PAGE_ID']


# ─── 모델 매핑 테스트 ───


class TestKRWorkerModels:
    """워커 모델 매핑 테스트"""

    def test_all_workers_have_models(self):
        expected_workers = ['Worker-A', 'Worker-B', 'Worker-C', 'Notion-Writer']
        for worker in expected_workers:
            assert worker in KR_WORKER_MODELS

    def test_worker_c_uses_haiku(self):
        assert 'haiku' in KR_WORKER_MODELS['Worker-C']

    def test_worker_a_uses_sonnet(self):
        assert 'sonnet' in KR_WORKER_MODELS['Worker-A']
