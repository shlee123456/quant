"""
Stock Symbol Database and Search Utilities
"""

from typing import List, Dict, Optional
import pandas as pd

# Import yfinance helper (optional - fallback if not available)
try:
    from dashboard.yfinance_helper import get_company_info
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class StockSymbolDB:
    """Database of popular US stock symbols with sector/industry info"""

    def __init__(self):
        """Initialize stock symbol database"""
        self.stocks = [
            # Technology - FAANG + Mega Caps
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology', 'industry': 'Consumer Electronics', 'exchange': 'NASDAQ'},
            {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'sector': 'Technology', 'industry': 'Software', 'exchange': 'NASDAQ'},
            {'symbol': 'GOOGL', 'name': 'Alphabet Inc. Class A', 'sector': 'Technology', 'industry': 'Internet', 'exchange': 'NASDAQ'},
            {'symbol': 'GOOG', 'name': 'Alphabet Inc. Class C', 'sector': 'Technology', 'industry': 'Internet', 'exchange': 'NASDAQ'},
            {'symbol': 'META', 'name': 'Meta Platforms Inc.', 'sector': 'Technology', 'industry': 'Social Media', 'exchange': 'NASDAQ'},
            {'symbol': 'NVDA', 'name': 'NVIDIA Corporation', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'sector': 'Technology', 'industry': 'Electric Vehicles', 'exchange': 'NASDAQ'},
            {'symbol': 'AMZN', 'name': 'Amazon.com Inc.', 'sector': 'Consumer Cyclical', 'industry': 'E-commerce', 'exchange': 'NASDAQ'},
            {'symbol': 'NFLX', 'name': 'Netflix Inc.', 'sector': 'Communication Services', 'industry': 'Streaming', 'exchange': 'NASDAQ'},

            # Technology - Semiconductors
            {'symbol': 'AMD', 'name': 'Advanced Micro Devices', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'INTC', 'name': 'Intel Corporation', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'QCOM', 'name': 'Qualcomm Inc.', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'AVGO', 'name': 'Broadcom Inc.', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'TXN', 'name': 'Texas Instruments', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'MU', 'name': 'Micron Technology', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'AMAT', 'name': 'Applied Materials', 'sector': 'Technology', 'industry': 'Semiconductor Equipment', 'exchange': 'NASDAQ'},
            {'symbol': 'LRCX', 'name': 'Lam Research', 'sector': 'Technology', 'industry': 'Semiconductor Equipment', 'exchange': 'NASDAQ'},
            {'symbol': 'KLAC', 'name': 'KLA Corporation', 'sector': 'Technology', 'industry': 'Semiconductor Equipment', 'exchange': 'NASDAQ'},
            {'symbol': 'ADI', 'name': 'Analog Devices', 'sector': 'Technology', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},

            # Technology - Software & Cloud
            {'symbol': 'CRM', 'name': 'Salesforce Inc.', 'sector': 'Technology', 'industry': 'Cloud Computing', 'exchange': 'NYSE'},
            {'symbol': 'ORCL', 'name': 'Oracle Corporation', 'sector': 'Technology', 'industry': 'Database Software', 'exchange': 'NYSE'},
            {'symbol': 'ADBE', 'name': 'Adobe Inc.', 'sector': 'Technology', 'industry': 'Software', 'exchange': 'NASDAQ'},
            {'symbol': 'CSCO', 'name': 'Cisco Systems', 'sector': 'Technology', 'industry': 'Networking', 'exchange': 'NASDAQ'},
            {'symbol': 'SNOW', 'name': 'Snowflake Inc.', 'sector': 'Technology', 'industry': 'Cloud Computing', 'exchange': 'NYSE'},
            {'symbol': 'NOW', 'name': 'ServiceNow Inc.', 'sector': 'Technology', 'industry': 'Cloud Computing', 'exchange': 'NYSE'},
            {'symbol': 'INTU', 'name': 'Intuit Inc.', 'sector': 'Technology', 'industry': 'Software', 'exchange': 'NASDAQ'},
            {'symbol': 'IBM', 'name': 'IBM', 'sector': 'Technology', 'industry': 'IT Services', 'exchange': 'NYSE'},
            {'symbol': 'PANW', 'name': 'Palo Alto Networks', 'sector': 'Technology', 'industry': 'Cybersecurity', 'exchange': 'NASDAQ'},
            {'symbol': 'CRWD', 'name': 'CrowdStrike Holdings', 'sector': 'Technology', 'industry': 'Cybersecurity', 'exchange': 'NASDAQ'},
            {'symbol': 'PLTR', 'name': 'Palantir Technologies', 'sector': 'Technology', 'industry': 'Software', 'exchange': 'NYSE'},
            {'symbol': 'SHOP', 'name': 'Shopify Inc.', 'sector': 'Technology', 'industry': 'E-commerce', 'exchange': 'NYSE'},
            {'symbol': 'SQ', 'name': 'Block Inc. (Square)', 'sector': 'Technology', 'industry': 'Fintech', 'exchange': 'NYSE'},
            {'symbol': 'UBER', 'name': 'Uber Technologies', 'sector': 'Technology', 'industry': 'Ride Sharing', 'exchange': 'NYSE'},
            {'symbol': 'ABNB', 'name': 'Airbnb Inc.', 'sector': 'Technology', 'industry': 'Travel Tech', 'exchange': 'NASDAQ'},
            {'symbol': 'RBLX', 'name': 'Roblox Corporation', 'sector': 'Technology', 'industry': 'Gaming', 'exchange': 'NYSE'},
            {'symbol': 'U', 'name': 'Unity Software', 'sector': 'Technology', 'industry': 'Gaming Software', 'exchange': 'NYSE'},
            {'symbol': 'DDOG', 'name': 'Datadog Inc.', 'sector': 'Technology', 'industry': 'Cloud Monitoring', 'exchange': 'NASDAQ'},
            {'symbol': 'ZS', 'name': 'Zscaler Inc.', 'sector': 'Technology', 'industry': 'Cybersecurity', 'exchange': 'NASDAQ'},
            {'symbol': 'OKTA', 'name': 'Okta Inc.', 'sector': 'Technology', 'industry': 'Identity Management', 'exchange': 'NASDAQ'},

            # E-commerce & Retail
            {'symbol': 'WMT', 'name': 'Walmart Inc.', 'sector': 'Consumer Defensive', 'industry': 'Retail', 'exchange': 'NYSE'},
            {'symbol': 'COST', 'name': 'Costco Wholesale', 'sector': 'Consumer Defensive', 'industry': 'Retail', 'exchange': 'NASDAQ'},
            {'symbol': 'TGT', 'name': 'Target Corporation', 'sector': 'Consumer Cyclical', 'industry': 'Retail', 'exchange': 'NYSE'},
            {'symbol': 'HD', 'name': 'Home Depot Inc.', 'sector': 'Consumer Cyclical', 'industry': 'Home Improvement', 'exchange': 'NYSE'},
            {'symbol': 'LOW', 'name': 'Lowe\'s Companies', 'sector': 'Consumer Cyclical', 'industry': 'Home Improvement', 'exchange': 'NYSE'},
            {'symbol': 'SBUX', 'name': 'Starbucks Corporation', 'sector': 'Consumer Cyclical', 'industry': 'Restaurants', 'exchange': 'NASDAQ'},
            {'symbol': 'MCD', 'name': 'McDonald\'s Corporation', 'sector': 'Consumer Cyclical', 'industry': 'Restaurants', 'exchange': 'NYSE'},
            {'symbol': 'NKE', 'name': 'Nike Inc.', 'sector': 'Consumer Cyclical', 'industry': 'Apparel', 'exchange': 'NYSE'},

            # Finance - Banks
            {'symbol': 'JPM', 'name': 'JPMorgan Chase & Co.', 'sector': 'Financial', 'industry': 'Banking', 'exchange': 'NYSE'},
            {'symbol': 'BAC', 'name': 'Bank of America Corp.', 'sector': 'Financial', 'industry': 'Banking', 'exchange': 'NYSE'},
            {'symbol': 'WFC', 'name': 'Wells Fargo & Co.', 'sector': 'Financial', 'industry': 'Banking', 'exchange': 'NYSE'},
            {'symbol': 'C', 'name': 'Citigroup Inc.', 'sector': 'Financial', 'industry': 'Banking', 'exchange': 'NYSE'},
            {'symbol': 'GS', 'name': 'Goldman Sachs Group', 'sector': 'Financial', 'industry': 'Investment Banking', 'exchange': 'NYSE'},
            {'symbol': 'MS', 'name': 'Morgan Stanley', 'sector': 'Financial', 'industry': 'Investment Banking', 'exchange': 'NYSE'},
            {'symbol': 'BLK', 'name': 'BlackRock Inc.', 'sector': 'Financial', 'industry': 'Asset Management', 'exchange': 'NYSE'},
            {'symbol': 'SCHW', 'name': 'Charles Schwab Corp.', 'sector': 'Financial', 'industry': 'Brokerage', 'exchange': 'NYSE'},

            # Finance - Payment & Fintech
            {'symbol': 'V', 'name': 'Visa Inc.', 'sector': 'Financial', 'industry': 'Payment Processing', 'exchange': 'NYSE'},
            {'symbol': 'MA', 'name': 'Mastercard Inc.', 'sector': 'Financial', 'industry': 'Payment Processing', 'exchange': 'NYSE'},
            {'symbol': 'PYPL', 'name': 'PayPal Holdings', 'sector': 'Financial', 'industry': 'Fintech', 'exchange': 'NASDAQ'},
            {'symbol': 'SQ', 'name': 'Block Inc.', 'sector': 'Financial', 'industry': 'Fintech', 'exchange': 'NYSE'},
            {'symbol': 'AXP', 'name': 'American Express', 'sector': 'Financial', 'industry': 'Credit Services', 'exchange': 'NYSE'},

            # Healthcare - Pharma & Biotech
            {'symbol': 'JNJ', 'name': 'Johnson & Johnson', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals', 'exchange': 'NYSE'},
            {'symbol': 'PFE', 'name': 'Pfizer Inc.', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals', 'exchange': 'NYSE'},
            {'symbol': 'UNH', 'name': 'UnitedHealth Group', 'sector': 'Healthcare', 'industry': 'Health Insurance', 'exchange': 'NYSE'},
            {'symbol': 'ABBV', 'name': 'AbbVie Inc.', 'sector': 'Healthcare', 'industry': 'Biotechnology', 'exchange': 'NYSE'},
            {'symbol': 'LLY', 'name': 'Eli Lilly and Co.', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals', 'exchange': 'NYSE'},
            {'symbol': 'MRK', 'name': 'Merck & Co.', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals', 'exchange': 'NYSE'},
            {'symbol': 'TMO', 'name': 'Thermo Fisher Scientific', 'sector': 'Healthcare', 'industry': 'Life Sciences', 'exchange': 'NYSE'},
            {'symbol': 'ABT', 'name': 'Abbott Laboratories', 'sector': 'Healthcare', 'industry': 'Medical Devices', 'exchange': 'NYSE'},
            {'symbol': 'GILD', 'name': 'Gilead Sciences', 'sector': 'Healthcare', 'industry': 'Biotechnology', 'exchange': 'NASDAQ'},
            {'symbol': 'AMGN', 'name': 'Amgen Inc.', 'sector': 'Healthcare', 'industry': 'Biotechnology', 'exchange': 'NASDAQ'},

            # Energy
            {'symbol': 'XOM', 'name': 'Exxon Mobil Corp.', 'sector': 'Energy', 'industry': 'Oil & Gas', 'exchange': 'NYSE'},
            {'symbol': 'CVX', 'name': 'Chevron Corporation', 'sector': 'Energy', 'industry': 'Oil & Gas', 'exchange': 'NYSE'},
            {'symbol': 'COP', 'name': 'ConocoPhillips', 'sector': 'Energy', 'industry': 'Oil & Gas', 'exchange': 'NYSE'},
            {'symbol': 'SLB', 'name': 'Schlumberger', 'sector': 'Energy', 'industry': 'Oil Services', 'exchange': 'NYSE'},
            {'symbol': 'EOG', 'name': 'EOG Resources', 'sector': 'Energy', 'industry': 'Oil & Gas', 'exchange': 'NYSE'},

            # Consumer Goods
            {'symbol': 'PG', 'name': 'Procter & Gamble Co.', 'sector': 'Consumer Defensive', 'industry': 'Household Products', 'exchange': 'NYSE'},
            {'symbol': 'KO', 'name': 'Coca-Cola Company', 'sector': 'Consumer Defensive', 'industry': 'Beverages', 'exchange': 'NYSE'},
            {'symbol': 'PEP', 'name': 'PepsiCo Inc.', 'sector': 'Consumer Defensive', 'industry': 'Beverages', 'exchange': 'NASDAQ'},
            {'symbol': 'PM', 'name': 'Philip Morris Intl', 'sector': 'Consumer Defensive', 'industry': 'Tobacco', 'exchange': 'NYSE'},
            {'symbol': 'MO', 'name': 'Altria Group', 'sector': 'Consumer Defensive', 'industry': 'Tobacco', 'exchange': 'NYSE'},

            # Media & Entertainment
            {'symbol': 'DIS', 'name': 'Walt Disney Company', 'sector': 'Communication Services', 'industry': 'Entertainment', 'exchange': 'NYSE'},
            {'symbol': 'CMCSA', 'name': 'Comcast Corporation', 'sector': 'Communication Services', 'industry': 'Telecom', 'exchange': 'NASDAQ'},
            {'symbol': 'T', 'name': 'AT&T Inc.', 'sector': 'Communication Services', 'industry': 'Telecom', 'exchange': 'NYSE'},
            {'symbol': 'VZ', 'name': 'Verizon Communications', 'sector': 'Communication Services', 'industry': 'Telecom', 'exchange': 'NYSE'},
            {'symbol': 'TMUS', 'name': 'T-Mobile US', 'sector': 'Communication Services', 'industry': 'Telecom', 'exchange': 'NASDAQ'},

            # Industrial
            {'symbol': 'BA', 'name': 'Boeing Company', 'sector': 'Industrials', 'industry': 'Aerospace', 'exchange': 'NYSE'},
            {'symbol': 'CAT', 'name': 'Caterpillar Inc.', 'sector': 'Industrials', 'industry': 'Machinery', 'exchange': 'NYSE'},
            {'symbol': 'GE', 'name': 'General Electric', 'sector': 'Industrials', 'industry': 'Conglomerate', 'exchange': 'NYSE'},
            {'symbol': 'UPS', 'name': 'United Parcel Service', 'sector': 'Industrials', 'industry': 'Logistics', 'exchange': 'NYSE'},
            {'symbol': 'FDX', 'name': 'FedEx Corporation', 'sector': 'Industrials', 'industry': 'Logistics', 'exchange': 'NYSE'},
            {'symbol': 'HON', 'name': 'Honeywell International', 'sector': 'Industrials', 'industry': 'Conglomerate', 'exchange': 'NASDAQ'},
            {'symbol': 'MMM', 'name': '3M Company', 'sector': 'Industrials', 'industry': 'Conglomerate', 'exchange': 'NYSE'},

            # Automotive
            {'symbol': 'F', 'name': 'Ford Motor Company', 'sector': 'Consumer Cyclical', 'industry': 'Automotive', 'exchange': 'NYSE'},
            {'symbol': 'GM', 'name': 'General Motors', 'sector': 'Consumer Cyclical', 'industry': 'Automotive', 'exchange': 'NYSE'},

            # Real Estate & REITs
            {'symbol': 'AMT', 'name': 'American Tower Corp.', 'sector': 'Real Estate', 'industry': 'REIT', 'exchange': 'NYSE'},
            {'symbol': 'PLD', 'name': 'Prologis Inc.', 'sector': 'Real Estate', 'industry': 'REIT', 'exchange': 'NYSE'},
            {'symbol': 'SPG', 'name': 'Simon Property Group', 'sector': 'Real Estate', 'industry': 'REIT', 'exchange': 'NYSE'},

            # Materials
            {'symbol': 'LIN', 'name': 'Linde plc', 'sector': 'Materials', 'industry': 'Chemicals', 'exchange': 'NYSE'},
            {'symbol': 'APD', 'name': 'Air Products & Chemicals', 'sector': 'Materials', 'industry': 'Chemicals', 'exchange': 'NYSE'},
            {'symbol': 'DD', 'name': 'DuPont de Nemours', 'sector': 'Materials', 'industry': 'Chemicals', 'exchange': 'NYSE'},

            # Utilities
            {'symbol': 'NEE', 'name': 'NextEra Energy', 'sector': 'Utilities', 'industry': 'Electric Utilities', 'exchange': 'NYSE'},
            {'symbol': 'DUK', 'name': 'Duke Energy', 'sector': 'Utilities', 'industry': 'Electric Utilities', 'exchange': 'NYSE'},
            {'symbol': 'SO', 'name': 'Southern Company', 'sector': 'Utilities', 'industry': 'Electric Utilities', 'exchange': 'NYSE'},

            # ETFs - Index
            {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF', 'sector': 'ETF', 'industry': 'Index', 'exchange': 'NYSE'},
            {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust', 'sector': 'ETF', 'industry': 'Tech Index', 'exchange': 'NASDAQ'},
            {'symbol': 'IWM', 'name': 'iShares Russell 2000', 'sector': 'ETF', 'industry': 'Small Cap Index', 'exchange': 'NYSE'},
            {'symbol': 'DIA', 'name': 'SPDR Dow Jones Industrial', 'sector': 'ETF', 'industry': 'Index', 'exchange': 'NYSE'},
            {'symbol': 'VOO', 'name': 'Vanguard S&P 500 ETF', 'sector': 'ETF', 'industry': 'Index', 'exchange': 'NYSE'},
            {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market', 'sector': 'ETF', 'industry': 'Index', 'exchange': 'NYSE'},

            # ETFs - Sector
            {'symbol': 'XLK', 'name': 'Technology Select Sector', 'sector': 'ETF', 'industry': 'Tech Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLF', 'name': 'Financial Select Sector', 'sector': 'ETF', 'industry': 'Finance Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLE', 'name': 'Energy Select Sector', 'sector': 'ETF', 'industry': 'Energy Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLV', 'name': 'Health Care Select Sector', 'sector': 'ETF', 'industry': 'Healthcare Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLI', 'name': 'Industrial Select Sector', 'sector': 'ETF', 'industry': 'Industrial Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLP', 'name': 'Consumer Staples Select', 'sector': 'ETF', 'industry': 'Consumer Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLY', 'name': 'Consumer Discretionary Select', 'sector': 'ETF', 'industry': 'Consumer Sector', 'exchange': 'NYSE'},
            {'symbol': 'XLU', 'name': 'Utilities Select Sector', 'sector': 'ETF', 'industry': 'Utilities Sector', 'exchange': 'NYSE'},

            # ETFs - Thematic
            {'symbol': 'ARKK', 'name': 'ARK Innovation ETF', 'sector': 'ETF', 'industry': 'Innovation', 'exchange': 'NYSE'},
            {'symbol': 'SOXX', 'name': 'iShares Semiconductor ETF', 'sector': 'ETF', 'industry': 'Semiconductors', 'exchange': 'NASDAQ'},
            {'symbol': 'ICLN', 'name': 'iShares Clean Energy ETF', 'sector': 'ETF', 'industry': 'Clean Energy', 'exchange': 'NASDAQ'},
        ]

        # Create DataFrame for easier searching
        self.df = pd.DataFrame(self.stocks)

        # Define popular stock presets
        self.presets = {
            'Top 10 US Market Cap': ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'LLY', 'WMT'],
            'FAANG': ['META', 'AAPL', 'AMZN', 'NFLX', 'GOOGL'],
            'Magnificent 7': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'],
            'Tech Giants': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'ORCL', 'CSCO'],
            'Semiconductors': ['NVDA', 'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT'],
            'Dividend Aristocrats': ['JNJ', 'PG', 'KO', 'PEP', 'WMT', 'MCD', 'XOM'],
            'Finance Leaders': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA'],
            'Healthcare Leaders': ['JNJ', 'UNH', 'PFE', 'ABBV', 'LLY', 'MRK', 'TMO'],
            'Index ETFs': ['SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI'],
            'Sector ETFs': ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP'],
        }

    def search(self, query: str, use_yfinance: bool = True) -> List[Dict]:
        """
        Search stocks by symbol or name

        Args:
            query: Search query (symbol or company name)
            use_yfinance: If True, search yfinance if no local matches found

        Returns:
            List of matching stock dictionaries
        """
        if not query:
            return []

        query = query.upper().strip()

        # Search by symbol (exact or prefix match)
        symbol_matches = self.df[self.df['symbol'].str.startswith(query)]

        # Search by name (contains)
        name_matches = self.df[self.df['name'].str.upper().str.contains(query)]

        # Combine and remove duplicates
        matches = pd.concat([symbol_matches, name_matches]).drop_duplicates()

        results = matches.to_dict('records')

        # If no local matches and yfinance is available, try yfinance
        if not results and use_yfinance and YFINANCE_AVAILABLE:
            # Assume query is a symbol and try yfinance
            yf_result = self._search_yfinance(query)
            if yf_result:
                results = [yf_result]

        return results

    def _search_yfinance(self, symbol: str) -> Optional[Dict]:
        """
        Search for a stock using yfinance

        Args:
            symbol: Stock symbol to search

        Returns:
            Stock info dict or None if not found
        """
        if not YFINANCE_AVAILABLE:
            return None

        try:
            info = get_company_info(symbol)
            if info:
                # Convert yfinance format to our format
                return {
                    'symbol': info['symbol'],
                    'name': info['name'],
                    'sector': info['sector'],
                    'industry': info['industry'],
                    'exchange': info['exchange']
                }
        except Exception as e:
            print(f"yfinance search failed for {symbol}: {e}")

        return None

    def get_by_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Get stock info by exact symbol

        Args:
            symbol: Stock symbol (e.g., 'AAPL')

        Returns:
            Stock dict or None if not found
        """
        symbol = symbol.upper().strip()
        result = self.df[self.df['symbol'] == symbol]

        if result.empty:
            return None

        return result.iloc[0].to_dict()

    def get_by_sector(self, sector: str) -> List[Dict]:
        """
        Get all stocks in a sector

        Args:
            sector: Sector name

        Returns:
            List of stock dictionaries
        """
        matches = self.df[self.df['sector'] == sector]
        return matches.to_dict('records')

    def get_all_sectors(self) -> List[str]:
        """Get list of all unique sectors"""
        return sorted(self.df['sector'].unique().tolist())

    def get_popular_stocks(self, limit: int = 10) -> List[Dict]:
        """
        Get list of popular stocks

        Args:
            limit: Maximum number of stocks to return

        Returns:
            List of stock dictionaries
        """
        # Return first N stocks (already sorted by popularity)
        return self.stocks[:limit]

    def get_by_exchange(self, exchange: str) -> List[Dict]:
        """
        Get all stocks by exchange

        Args:
            exchange: Exchange name ('NASDAQ', 'NYSE')

        Returns:
            List of stock dictionaries
        """
        matches = self.df[self.df['exchange'] == exchange]
        return matches.to_dict('records')

    def get_all_exchanges(self) -> List[str]:
        """Get list of all unique exchanges"""
        return sorted(self.df['exchange'].unique().tolist())

    def get_all_symbols(self) -> List[str]:
        """Get list of all stock symbols"""
        return sorted(self.df['symbol'].tolist())

    def get_preset(self, preset_name: str) -> List[str]:
        """
        Get symbols from a preset

        Args:
            preset_name: Name of the preset (e.g., 'FAANG', 'Tech Giants')

        Returns:
            List of stock symbols in the preset
        """
        return self.presets.get(preset_name, [])

    def get_all_presets(self) -> Dict[str, List[str]]:
        """Get all available presets"""
        return self.presets

    def get_preset_names(self) -> List[str]:
        """Get list of all preset names"""
        return list(self.presets.keys())

    def get_sector_count(self, sector: str) -> int:
        """
        Get number of stocks in a sector

        Args:
            sector: Sector name

        Returns:
            Number of stocks in the sector
        """
        return len(self.df[self.df['sector'] == sector])
