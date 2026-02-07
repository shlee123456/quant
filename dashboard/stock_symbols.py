"""
Stock Symbol Database and Search Utilities
"""

from typing import List, Dict, Optional
import pandas as pd


class StockSymbolDB:
    """Database of popular US stock symbols with sector/industry info"""

    def __init__(self):
        """Initialize stock symbol database"""
        self.stocks = [
            # Technology
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology', 'industry': 'Consumer Electronics'},
            {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'sector': 'Technology', 'industry': 'Software'},
            {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'sector': 'Technology', 'industry': 'Internet'},
            {'symbol': 'META', 'name': 'Meta Platforms Inc.', 'sector': 'Technology', 'industry': 'Social Media'},
            {'symbol': 'NVDA', 'name': 'NVIDIA Corporation', 'sector': 'Technology', 'industry': 'Semiconductors'},
            {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'sector': 'Technology', 'industry': 'Electric Vehicles'},
            {'symbol': 'AMD', 'name': 'Advanced Micro Devices', 'sector': 'Technology', 'industry': 'Semiconductors'},
            {'symbol': 'INTC', 'name': 'Intel Corporation', 'sector': 'Technology', 'industry': 'Semiconductors'},
            {'symbol': 'CRM', 'name': 'Salesforce Inc.', 'sector': 'Technology', 'industry': 'Cloud Computing'},
            {'symbol': 'ORCL', 'name': 'Oracle Corporation', 'sector': 'Technology', 'industry': 'Database Software'},

            # E-commerce & Retail
            {'symbol': 'AMZN', 'name': 'Amazon.com Inc.', 'sector': 'Consumer Cyclical', 'industry': 'E-commerce'},
            {'symbol': 'WMT', 'name': 'Walmart Inc.', 'sector': 'Consumer Defensive', 'industry': 'Retail'},
            {'symbol': 'HD', 'name': 'Home Depot Inc.', 'sector': 'Consumer Cyclical', 'industry': 'Home Improvement'},
            {'symbol': 'NKE', 'name': 'Nike Inc.', 'sector': 'Consumer Cyclical', 'industry': 'Apparel'},

            # Finance
            {'symbol': 'JPM', 'name': 'JPMorgan Chase & Co.', 'sector': 'Financial', 'industry': 'Banking'},
            {'symbol': 'BAC', 'name': 'Bank of America Corp.', 'sector': 'Financial', 'industry': 'Banking'},
            {'symbol': 'GS', 'name': 'Goldman Sachs Group', 'sector': 'Financial', 'industry': 'Investment Banking'},
            {'symbol': 'V', 'name': 'Visa Inc.', 'sector': 'Financial', 'industry': 'Payment Processing'},
            {'symbol': 'MA', 'name': 'Mastercard Inc.', 'sector': 'Financial', 'industry': 'Payment Processing'},

            # Healthcare
            {'symbol': 'JNJ', 'name': 'Johnson & Johnson', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals'},
            {'symbol': 'PFE', 'name': 'Pfizer Inc.', 'sector': 'Healthcare', 'industry': 'Pharmaceuticals'},
            {'symbol': 'UNH', 'name': 'UnitedHealth Group', 'sector': 'Healthcare', 'industry': 'Health Insurance'},
            {'symbol': 'ABBV', 'name': 'AbbVie Inc.', 'sector': 'Healthcare', 'industry': 'Biotechnology'},

            # Energy
            {'symbol': 'XOM', 'name': 'Exxon Mobil Corp.', 'sector': 'Energy', 'industry': 'Oil & Gas'},
            {'symbol': 'CVX', 'name': 'Chevron Corporation', 'sector': 'Energy', 'industry': 'Oil & Gas'},

            # Consumer Goods
            {'symbol': 'PG', 'name': 'Procter & Gamble Co.', 'sector': 'Consumer Defensive', 'industry': 'Household Products'},
            {'symbol': 'KO', 'name': 'Coca-Cola Company', 'sector': 'Consumer Defensive', 'industry': 'Beverages'},
            {'symbol': 'PEP', 'name': 'PepsiCo Inc.', 'sector': 'Consumer Defensive', 'industry': 'Beverages'},
            {'symbol': 'MCD', 'name': 'McDonald\'s Corporation', 'sector': 'Consumer Cyclical', 'industry': 'Restaurants'},

            # Media & Entertainment
            {'symbol': 'DIS', 'name': 'Walt Disney Company', 'sector': 'Communication Services', 'industry': 'Entertainment'},
            {'symbol': 'NFLX', 'name': 'Netflix Inc.', 'sector': 'Communication Services', 'industry': 'Streaming'},

            # Industrial
            {'symbol': 'BA', 'name': 'Boeing Company', 'sector': 'Industrials', 'industry': 'Aerospace'},
            {'symbol': 'CAT', 'name': 'Caterpillar Inc.', 'sector': 'Industrials', 'industry': 'Machinery'},
        ]

        # Create DataFrame for easier searching
        self.df = pd.DataFrame(self.stocks)

    def search(self, query: str) -> List[Dict]:
        """
        Search stocks by symbol or name

        Args:
            query: Search query (symbol or company name)

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

        return matches.to_dict('records')

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
