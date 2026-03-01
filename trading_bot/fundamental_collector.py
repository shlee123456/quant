"""기업 펀더멘탈 데이터 수집기 - yfinance Ticker.info 기반"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FundamentalCollector:
    """yfinance Ticker.info 기반 기업 기본 데이터 수집"""

    FIELDS = {
        'trailingPE': 'pe_ratio',
        'forwardPE': 'forward_pe',
        'trailingEps': 'eps',
        'dividendYield': 'dividend_yield',
        'sector': 'sector',
        'industry': 'industry',
        'beta': 'beta',
        'fiftyTwoWeekHigh': 'fifty_two_week_high',
        'fiftyTwoWeekLow': 'fifty_two_week_low',
        'marketCap': 'market_cap',
    }

    def __init__(self, api_delay: float = 0.3):
        self.api_delay = api_delay

    def collect(self, symbols: List[str]) -> Optional[Dict]:
        """각 심볼의 펀더멘탈 데이터 수집"""
        if not symbols:
            return None

        import yfinance as yf

        fundamentals = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info

                if not info:
                    continue

                data = {}
                for yf_key, out_key in self.FIELDS.items():
                    val = info.get(yf_key)
                    if val is not None:
                        # Convert numeric types safely
                        if out_key in ('sector', 'industry'):
                            data[out_key] = str(val)
                        elif isinstance(val, (int, float)):
                            data[out_key] = float(val)
                        else:
                            data[out_key] = val

                if data:
                    fundamentals[symbol] = data

                time.sleep(self.api_delay)
            except Exception as e:
                logger.debug(f"펀더멘탈 조회 실패 ({symbol}): {e}")
                continue

        if not fundamentals:
            return None

        return {
            'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'fundamentals': fundamentals,
        }
