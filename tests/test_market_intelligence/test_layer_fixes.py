"""
Phase 1 데이터 정확성 수정 테스트.

Fix 1-1: Credit Spread Duration Matching (HYG vs IEI)
Fix 1-2: Yield Curve — ^TNX/^FVX 직접 사용 + TLT/SHY 폴백
Fix 1-3: Smart Money — GLD/SPY 비율 (HYG 이중 카운팅 제거)
Fix 1-4: Fear & Greed 일관된 역발상 스코어링
Fix 1-5: 실패 레이어 score=NaN 처리
"""

import math

import numpy as np
import pandas as pd
import pytest

from tests.test_market_intelligence.conftest import MockCache, make_ohlcv
from trading_bot.market_intelligence.layer1_macro_regime import MacroRegimeLayer
from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer
from trading_bot.market_intelligence.base_layer import LayerResult


# ─── Helpers ───

def _make_yield_series(n: int = 200, start: float = 4.0, trend: float = 0.001,
                       seed: int = 42) -> pd.DataFrame:
    """^TNX/^FVX 같은 yield 데이터 생성 (Close 컬럼, 값은 %단위 수치)."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq='B')
    values = start + np.cumsum(rng.normal(trend, 0.02, n))
    return pd.DataFrame({'Close': values}, index=dates)


# ─── Fix 1-1: Credit Spread uses IEI ───

class TestCreditSpreadUsesIEI:
    """_score_credit_spread가 IEI를 사용하는지 검증."""

    def test_credit_spread_uses_iei(self):
        """IEI 데이터가 있으면 IEI를 읽어 스프레드를 계산한다."""
        hyg_df = make_ohlcv(n=60, start_price=75.0, trend=0.002, seed=10)
        iei_df = make_ohlcv(n=60, start_price=100.0, trend=0.0005, seed=11)

        cache = MockCache({'HYG': hyg_df, 'IEI': iei_df})
        layer = MacroRegimeLayer()

        score, details = layer._score_credit_spread(cache)

        # 정상 스코어 반환 (NaN 아님)
        assert not math.isnan(score), "IEI 데이터 있으면 유효한 스코어 반환"
        # details에 iei_ret_5d 키가 있어야 함
        assert 'iei_ret_5d' in details, "details에 iei_ret_5d 키 존재"
        # lqd_ret_5d 키는 없어야 함
        assert 'lqd_ret_5d' not in details, "LQD 키가 없어야 함"

    def test_credit_spread_no_iei_returns_nan(self):
        """IEI 데이터가 없으면 NaN을 반환한다."""
        hyg_df = make_ohlcv(n=60, start_price=75.0, seed=10)
        # LQD는 있지만 IEI가 없음
        lqd_df = make_ohlcv(n=60, start_price=110.0, seed=12)

        cache = MockCache({'HYG': hyg_df, 'LQD': lqd_df})
        layer = MacroRegimeLayer()

        score, details = layer._score_credit_spread(cache)

        assert math.isnan(score), "IEI 없으면 NaN"
        assert 'error' in details


# ─── Fix 1-2: Yield Curve uses ^TNX/^FVX ───

class TestYieldCurveUseTNXFVX:
    """_score_yield_curve가 ^TNX/^FVX를 우선 사용하는지 검증."""

    def test_yield_curve_uses_tnx_fvx(self):
        """^TNX와 ^FVX 데이터가 있으면 직접 스프레드를 계산한다."""
        tnx_df = _make_yield_series(n=60, start=4.3, trend=0.001, seed=20)
        fvx_df = _make_yield_series(n=60, start=4.0, trend=0.0005, seed=21)

        cache = MockCache({'^TNX': tnx_df, '^FVX': fvx_df})
        layer = MacroRegimeLayer()

        score, details = layer._score_yield_curve(cache)

        assert not math.isnan(score), "TNX/FVX 있으면 유효한 스코어"
        assert details.get('source') == 'TNX_FVX', "소스가 TNX_FVX"
        assert 'current_spread' in details

    def test_yield_curve_fallback_to_tlt_shy(self):
        """^TNX/^FVX가 없으면 TLT/SHY 비율로 폴백한다."""
        tlt_df = make_ohlcv(n=60, start_price=90.0, trend=0.001, seed=30)
        shy_df = make_ohlcv(n=60, start_price=82.0, trend=0.0002, seed=31)

        # TNX, FVX 없음
        cache = MockCache({'TLT': tlt_df, 'SHY': shy_df})
        layer = MacroRegimeLayer()

        score, details = layer._score_yield_curve(cache)

        assert not math.isnan(score), "TLT/SHY 폴백 시 유효한 스코어"
        assert details.get('source') == 'TLT_SHY', "소스가 TLT_SHY"
        assert 'current_ratio' in details

    def test_yield_curve_tnx_short_data_falls_back(self):
        """^TNX 데이터가 짧으면 (< 25) TLT/SHY로 폴백한다."""
        tnx_df = _make_yield_series(n=10, start=4.3, seed=20)  # 짧은 데이터
        fvx_df = _make_yield_series(n=60, start=4.0, seed=21)
        tlt_df = make_ohlcv(n=60, start_price=90.0, seed=30)
        shy_df = make_ohlcv(n=60, start_price=82.0, seed=31)

        cache = MockCache({
            '^TNX': tnx_df, '^FVX': fvx_df,
            'TLT': tlt_df, 'SHY': shy_df,
        })
        layer = MacroRegimeLayer()

        score, details = layer._score_yield_curve(cache)

        assert not math.isnan(score)
        assert details.get('source') == 'TLT_SHY'


# ─── Fix 1-3: Smart Money uses GLD/SPY, not HYG ───

class TestSmartMoneyGLDSPY:
    """_calc_smart_money가 GLD/SPY 비율을 사용하는지 검증."""

    def test_smart_money_uses_gld_spy(self):
        """GLD/SPY 비율 모멘텀으로 스코어를 계산한다."""
        gld_df = make_ohlcv(n=60, start_price=180.0, trend=0.001, seed=40)
        spy_df = make_ohlcv(n=60, start_price=450.0, trend=0.002, seed=41)

        cache = MockCache({'GLD': gld_df, 'SPY': spy_df})
        layer = SentimentLayer()

        score, details = layer._calc_smart_money(cache)

        # 유효한 스코어
        assert score != 0.0 or 'error' not in details
        # GLD/SPY 관련 키 존재
        assert 'gld_spy_momentum' in details
        assert 'gld_spy_ret_5d_pct' in details
        assert 'direction' in details

    def test_smart_money_hyg_not_used(self):
        """HYG만 있고 GLD/SPY가 없으면 에러를 반환한다 (HYG 미사용 확인)."""
        hyg_df = make_ohlcv(n=60, start_price=75.0, seed=42)

        cache = MockCache({'HYG': hyg_df})
        layer = SentimentLayer()

        score, details = layer._calc_smart_money(cache)

        # GLD/SPY 없으므로 에러
        assert score == 0.0
        assert 'error' in details

    def test_smart_money_gld_strong_is_bearish(self):
        """GLD가 SPY 대비 강하면 (risk-off) 음수 스코어."""
        # GLD 강한 상승, SPY 약한 상승
        gld_df = make_ohlcv(n=60, start_price=180.0, trend=0.005, seed=50)
        spy_df = make_ohlcv(n=60, start_price=450.0, trend=-0.001, seed=51)

        cache = MockCache({'GLD': gld_df, 'SPY': spy_df})
        layer = SentimentLayer()

        score, details = layer._calc_smart_money(cache)

        # GLD outperforming = negate = negative score
        assert score < 0, f"GLD 강세 시 음수 스코어 기대, 실제: {score}"


# ─── Fix 1-4: Fear & Greed Consistent Contrarian ───

class TestFearGreedContrarian:
    """Fear & Greed Index가 일관된 역발상 매핑을 따르는지 검증."""

    def test_fear_greed_value_30_is_positive(self):
        """F&G=30은 공포 구간이므로 양수 (역발상 매수)."""
        score, details = SentimentLayer._calc_fear_greed({'value': 30})
        assert score > 0, f"F&G=30은 양수여야 함, 실제: {score}"
        assert details['zone'] == 'fear'

    def test_fear_greed_value_60_is_negative(self):
        """F&G=60은 약한 탐욕이므로 음수 (역발상 매도)."""
        score, details = SentimentLayer._calc_fear_greed({'value': 60})
        assert score < 0, f"F&G=60은 음수여야 함, 실제: {score}"
        assert details['zone'] == 'mild_greed'

    def test_fear_greed_all_zones(self):
        """7개 구간 모두 올바른 zone과 score 방향을 반환한다."""
        test_cases = [
            # (value, expected_zone, score_positive)
            (10, 'extreme_fear', True),     # +80
            (30, 'fear', True),             # +40
            (40, 'mild_fear', True),        # +10
            (52, 'neutral', None),          # 0
            (60, 'mild_greed', False),      # -10
            (70, 'greed', False),           # -40
            (90, 'extreme_greed', False),   # -80
        ]

        for value, expected_zone, score_positive in test_cases:
            score, details = SentimentLayer._calc_fear_greed({'value': value})
            assert details['zone'] == expected_zone, (
                f"value={value}: zone={details['zone']}, expected={expected_zone}"
            )

            if score_positive is True:
                assert score > 0, f"value={value}: score={score} should be positive"
            elif score_positive is False:
                assert score < 0, f"value={value}: score={score} should be negative"
            else:
                assert score == 0.0, f"value={value}: score={score} should be 0"

    def test_fear_greed_extreme_scores(self):
        """극단값에서 정확한 스코어 확인."""
        score_ef, _ = SentimentLayer._calc_fear_greed({'value': 10})
        assert score_ef == 80.0

        score_eg, _ = SentimentLayer._calc_fear_greed({'value': 90})
        assert score_eg == -80.0

    def test_fear_greed_monotonic_decrease(self):
        """F&G 값이 증가하면 스코어가 단조 감소한다."""
        representative_values = [10, 30, 40, 52, 60, 70, 90]
        scores = []
        for v in representative_values:
            s, _ = SentimentLayer._calc_fear_greed({'value': v})
            scores.append(s)

        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"score at F&G={representative_values[i]} ({scores[i]}) "
                f"should be >= score at F&G={representative_values[i+1]} ({scores[i+1]})"
            )


# ─── Fix 1-5: Failed Layer NaN ───

class TestFailedLayerNaN:
    """실패한 레이어가 NaN 스코어를 받고 composite에서 제외되는지 검증."""

    def test_failed_layer_nan_excluded(self):
        """실패 레이어의 NaN 스코어가 weighted_composite에서 제외된다."""
        from trading_bot.market_intelligence.scoring import weighted_composite

        scores = {
            'macro_regime': 50.0,
            'market_structure': float('nan'),  # 실패
            'sector_rotation': 30.0,
            'enhanced_technicals': -10.0,
            'sentiment': 20.0,
        }
        weights = {
            'macro_regime': 0.20,
            'market_structure': 0.20,
            'sector_rotation': 0.15,
            'enhanced_technicals': 0.25,
            'sentiment': 0.20,
        }

        composite = weighted_composite(scores, weights)

        # NaN이 포함되지 않아야 함
        assert not math.isnan(composite), "composite에 NaN이 없어야 함"

        # market_structure를 제외한 가중 평균
        # (50*0.20 + 30*0.15 + (-10)*0.25 + 20*0.20) / (0.20 + 0.15 + 0.25 + 0.20)
        expected_num = 50 * 0.20 + 30 * 0.15 + (-10) * 0.25 + 20 * 0.20
        expected_den = 0.20 + 0.15 + 0.25 + 0.20
        expected = expected_num / expected_den

        assert abs(composite - expected) < 0.01, (
            f"composite={composite}, expected={expected}"
        )

    def test_build_interpretation_with_nan(self):
        """일부 레이어가 NaN이어도 _build_overall_interpretation이 크래시하지 않는다."""
        from trading_bot.market_intelligence import MarketIntelligence

        layer_results = {
            'macro_regime': LayerResult(
                layer_name='macro_regime',
                score=float('nan'),
                signal='neutral',
                confidence=0.0,
                metrics={},
                interpretation='실패',
            ),
            'market_structure': LayerResult(
                layer_name='market_structure',
                score=30.0,
                signal='bullish',
                confidence=0.8,
                metrics={},
                interpretation='긍정적',
            ),
            'sentiment': LayerResult(
                layer_name='sentiment',
                score=-25.0,
                signal='bearish',
                confidence=0.7,
                metrics={},
                interpretation='부정적',
            ),
        }

        # 크래시 없이 해석 생성
        interpretation = MarketIntelligence._build_overall_interpretation(
            composite=10.0,
            signal='neutral',
            layer_results=layer_results,
        )

        assert isinstance(interpretation, str)
        assert len(interpretation) > 0

    def test_build_interpretation_all_nan(self):
        """모든 레이어가 NaN이면 '레이어 데이터 부족' 메시지를 포함한다."""
        from trading_bot.market_intelligence import MarketIntelligence

        layer_results = {
            'macro_regime': LayerResult(
                layer_name='macro_regime',
                score=float('nan'),
                signal='neutral',
                confidence=0.0,
            ),
            'market_structure': LayerResult(
                layer_name='market_structure',
                score=float('nan'),
                signal='neutral',
                confidence=0.0,
            ),
        }

        interpretation = MarketIntelligence._build_overall_interpretation(
            composite=0.0,
            signal='neutral',
            layer_results=layer_results,
        )

        assert '레이어 데이터 부족' in interpretation
