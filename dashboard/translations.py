"""
Multi-language support for Trading Dashboard
"""

TRANSLATIONS = {
    'en': {
        # Page title
        'page_title': 'Quant Trading Lab',
        'page_subtitle': 'Algorithmic Trading for Global Markets',

        # Sidebar
        'configuration': '⚙️ Configuration',
        'language': 'Language',
        'data_source': 'Data Source',
        'use_simulation': 'Use Simulation Data',
        'use_simulation_help': 'Use simulated data instead of real exchange data',
        'market_settings': 'Market Settings',
        'symbol': 'Symbol',
        'timeframe': 'Timeframe',
        'strategy_selection': 'Strategy Selection',
        'select_strategy': 'Select Strategy',
        'strategy_parameters': 'Strategy Parameters',
        'trading_parameters': 'Trading Parameters',
        'initial_capital': 'Initial Capital ($)',
        'initialize_system': 'Initialize System',
        'system_initialized': '✅ System initialized!',

        # Strategy names
        'Moving Average Crossover': 'Moving Average Crossover',
        'RSI Strategy': 'RSI Strategy',
        'MACD Strategy': 'MACD Strategy',
        'Bollinger Bands': 'Bollinger Bands',
        'Stochastic Oscillator': 'Stochastic Oscillator',

        # Strategy descriptions
        'ma_desc': 'Generates BUY when fast MA crosses above slow MA, SELL when fast MA crosses below slow MA',
        'rsi_desc': 'Generates BUY when RSI crosses below oversold level, SELL when RSI crosses above overbought level',
        'macd_desc': 'Generates BUY when MACD line crosses above signal line, SELL when MACD line crosses below signal line',
        'bb_desc': 'Generates BUY when price crosses below lower band, SELL when price crosses above upper band',
        'stoch_desc': 'Generates BUY when %K crosses above %D in oversold zone, SELL when %K crosses below %D in overbought zone',

        # Parameter labels
        'Fast MA Period': 'Fast MA Period',
        'Slow MA Period': 'Slow MA Period',
        'RSI Period': 'RSI Period',
        'Overbought Level': 'Overbought Level',
        'Oversold Level': 'Oversold Level',
        'Fast EMA Period': 'Fast EMA Period',
        'Slow EMA Period': 'Slow EMA Period',
        'Signal Period': 'Signal Period',
        'Period': 'Period',
        'Std Deviations': 'Std Deviations',
        '%K Period': '%K Period',
        '%D Period': '%D Period',

        # Tabs
        'tab_backtest': '📊 Backtesting',
        'tab_comparison': '🔍 Strategy Comparison',
        'tab_paper': '📄 Paper Trading',
        'tab_live': '📡 Live Monitor',
        'tab_quotes': '📊 Real-time Quotes',

        # Backtesting
        'backtest_title': '📊 Strategy Backtesting',
        'init_warning': '⚠️ Please initialize the system from the sidebar first.',
        'using_simulation': '📊 Using simulation data for backtesting',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'num_periods': 'Number of periods',
        'run_backtest': 'Run Backtest',
        'running_backtest': 'Running backtest...',
        'backtest_completed': '✅ Backtest completed!',
        'backtest_error': '❌ Error running backtest: ',

        # Results
        'performance_metrics': '📈 Performance Metrics',
        'total_return': 'Total Return',
        'sharpe_ratio': 'Sharpe Ratio',
        'max_drawdown': 'Max Drawdown',
        'win_rate': 'Win Rate',
        'total_trades': 'Total Trades',
        'final_capital': 'Final Capital',
        'equity_curve': '💰 Equity Curve',
        'price_chart': '📊 Price Chart',
        'trade_history': '📝 Trade History',
        'no_trades': 'No trades executed in this backtest.',

        # Strategy Comparison
        'comparison_title': '🔍 Strategy Comparison',
        'comparison_desc': 'Compare the performance of different trading strategies on the same dataset. Select multiple strategies and parameters to see which performs best.',
        'select_strategies': 'Select Strategies to Compare',
        'choose_strategies': 'Choose strategies',
        'min_strategies': 'Please select at least 2 strategies to compare.',
        'configure_params': '⚙️ Configure Strategy Parameters',
        'run_comparison': 'Run Comparison',
        'running_comparison': 'Running strategy comparison...',
        'comparison_completed': '✅ Comparison completed!',
        'comparison_error': '❌ Error during comparison: ',
        'comparison_results': '📊 Comparison Results',
        'visual_comparison': '📈 Visual Comparison',
        'return_comparison': 'Total Return Comparison',
        'sharpe_comparison': 'Sharpe Ratio Comparison',

        # Paper Trading
        'paper_title': '📄 Paper Trading',
        'paper_warning': '⚠️ Paper trading requires real market data. Please disable "Use Simulation Data" in the sidebar.',
        'start_paper': 'Start Paper Trading',
        'stop_paper': 'Stop Paper Trading',
        'paper_active': '🟢 Paper trading is ACTIVE',
        'paper_stopped': '⚪ Paper trading is STOPPED',
        'updates_every': 'Updates every 60 seconds',
        'current_price': 'Current Price',
        'portfolio_value': 'Portfolio Value',
        'pnl': 'P&L',
        'position': 'Position',

        # Live Monitor
        'live_title': '📡 Live Market Monitor',
        'live_warning': '⚠️ Live monitoring requires real market data. Please disable "Use Simulation Data" in the sidebar.',
        'auto_refresh': 'Auto-refresh (30s)',
        'refresh_now': 'Refresh Now',
        'fetching_data': 'Fetching latest data...',
        'current_signal': 'Current Signal',
        'signal': 'Signal',
        'timestamp': 'Timestamp',
        'indicator_values': '📊 Indicator Values',
        'recent_data': 'Recent Data',

        # Footer
        'footer': 'Built with Streamlit | Quant Trading Lab v2.0',

        # Market selection
        'market_type': 'Market Type',
        'crypto_market': 'Cryptocurrency',
        'stock_market': 'Foreign Stocks (US)',
        'select_market': 'Select Market',

        # Stock specific
        'stock_symbol': 'Stock Symbol',
        'stock_search': 'Search Stock',
        'sector': 'Sector',
        'industry': 'Industry',
        'market_hours': 'Market Hours',
        'pre_market': 'Pre-Market',
        'regular_hours': 'Regular Hours',
        'after_hours': 'After Hours',
        'market_closed': 'Market Closed',
        'market_status': 'Market Status',
        'popular_stocks': 'Popular Stocks',
        'us_market_hours': 'US Market Hours (EST)',
        'korea_time': 'Korea Time (KST)',
        'select_stock': 'Select Stock',
        'select_stock_help': 'Choose a US stock to view real-time quotes',
        'selected_symbol': 'Selected Symbol',

        # Real-time quotes (US-005)
        'current_price': 'Current Price',
        'open_price': 'Open',
        'high_price': 'High',
        'low_price': 'Low',
        'volume': 'Volume',
        'change_amount': 'Change',
        'fetching_quote': 'Fetching real-time quote...',
        'kis_not_available': 'KIS broker is not available. Please configure API credentials.',
        'quote_fetch_error': 'Failed to fetch quote',
        'possible_causes': 'Possible causes',
        'cause_network': 'Network connection issue',
        'cause_rate_limit': 'API rate limit exceeded (wait 1 minute)',
        'cause_invalid_symbol': 'Invalid symbol or market closed',
        'try_again': 'Please try again in a moment.'
    },
    'ko': {
        # Page title
        'page_title': 'Quant Trading Lab',
        'page_subtitle': '글로벌 시장을 위한 알고리즘 트레이딩',

        # Sidebar
        'configuration': '⚙️ 설정',
        'language': '언어',
        'data_source': '데이터 소스',
        'use_simulation': '시뮬레이션 데이터 사용',
        'use_simulation_help': '실제 거래소 데이터 대신 시뮬레이션 데이터 사용',
        'market_settings': '마켓 설정',
        'symbol': '심볼',
        'timeframe': '시간프레임',
        'strategy_selection': '전략 선택',
        'select_strategy': '전략 선택',
        'strategy_parameters': '전략 파라미터',
        'trading_parameters': '트레이딩 파라미터',
        'initial_capital': '초기 자본 ($)',
        'initialize_system': '시스템 초기화',
        'system_initialized': '✅ 시스템이 초기화되었습니다!',

        # Strategy names
        'Moving Average Crossover': '이동평균 크로스오버',
        'RSI Strategy': 'RSI 전략',
        'MACD Strategy': 'MACD 전략',
        'Bollinger Bands': '볼린저 밴드',
        'Stochastic Oscillator': '스토캐스틱 오실레이터',

        # Strategy descriptions
        'ma_desc': '빠른 이동평균이 느린 이동평균을 상향 돌파하면 매수, 하향 돌파하면 매도',
        'rsi_desc': 'RSI가 과매도 수준 아래로 교차하면 매수, 과매수 수준 위로 교차하면 매도',
        'macd_desc': 'MACD 선이 시그널 선을 상향 돌파하면 매수, 하향 돌파하면 매도',
        'bb_desc': '가격이 하단 밴드 아래로 교차하면 매수, 상단 밴드 위로 교차하면 매도',
        'stoch_desc': '과매도 구간에서 %K가 %D를 상향 돌파하면 매수, 과매수 구간에서 하향 돌파하면 매도',

        # Parameter labels
        'Fast MA Period': '빠른 이평 기간',
        'Slow MA Period': '느린 이평 기간',
        'RSI Period': 'RSI 기간',
        'Overbought Level': '과매수 수준',
        'Oversold Level': '과매도 수준',
        'Fast EMA Period': '빠른 EMA 기간',
        'Slow EMA Period': '느린 EMA 기간',
        'Signal Period': '시그널 기간',
        'Period': '기간',
        'Std Deviations': '표준편차',
        '%K Period': '%K 기간',
        '%D Period': '%D 기간',

        # Tabs
        'tab_backtest': '📊 백테스팅',
        'tab_comparison': '🔍 전략 비교',
        'tab_paper': '📄 모의 트레이딩',
        'tab_live': '📡 실시간 모니터',
        'tab_quotes': '📊 실시간 시세',

        # Backtesting
        'backtest_title': '📊 전략 백테스팅',
        'init_warning': '⚠️ 먼저 사이드바에서 시스템을 초기화해주세요.',
        'using_simulation': '📊 백테스팅에 시뮬레이션 데이터를 사용합니다',
        'start_date': '시작 날짜',
        'end_date': '종료 날짜',
        'num_periods': '기간 수',
        'run_backtest': '백테스트 실행',
        'running_backtest': '백테스트 실행 중...',
        'backtest_completed': '✅ 백테스트 완료!',
        'backtest_error': '❌ 백테스트 오류: ',

        # Results
        'performance_metrics': '📈 성과 지표',
        'total_return': '총 수익률',
        'sharpe_ratio': '샤프 비율',
        'max_drawdown': '최대 낙폭',
        'win_rate': '승률',
        'total_trades': '총 거래 수',
        'final_capital': '최종 자본',
        'equity_curve': '💰 자본 곡선',
        'price_chart': '📊 가격 차트',
        'trade_history': '📝 거래 내역',
        'no_trades': '이 백테스트에서 실행된 거래가 없습니다.',

        # Strategy Comparison
        'comparison_title': '🔍 전략 비교',
        'comparison_desc': '동일한 데이터셋에서 여러 트레이딩 전략의 성과를 비교합니다. 여러 전략과 파라미터를 선택하여 어떤 전략이 가장 좋은지 확인하세요.',
        'select_strategies': '비교할 전략 선택',
        'choose_strategies': '전략 선택',
        'min_strategies': '비교하려면 최소 2개의 전략을 선택하세요.',
        'configure_params': '⚙️ 전략 파라미터 설정',
        'run_comparison': '비교 실행',
        'running_comparison': '전략 비교 실행 중...',
        'comparison_completed': '✅ 비교 완료!',
        'comparison_error': '❌ 비교 오류: ',
        'comparison_results': '📊 비교 결과',
        'visual_comparison': '📈 시각적 비교',
        'return_comparison': '총 수익률 비교',
        'sharpe_comparison': '샤프 비율 비교',

        # Paper Trading
        'paper_title': '📄 모의 트레이딩',
        'paper_warning': '⚠️ 모의 트레이딩은 실제 시장 데이터가 필요합니다. 사이드바에서 "시뮬레이션 데이터 사용"을 해제하세요.',
        'start_paper': '모의 트레이딩 시작',
        'stop_paper': '모의 트레이딩 중지',
        'paper_active': '🟢 모의 트레이딩 활성',
        'paper_stopped': '⚪ 모의 트레이딩 중지됨',
        'updates_every': '60초마다 업데이트',
        'current_price': '현재 가격',
        'portfolio_value': '포트폴리오 가치',
        'pnl': '손익',
        'position': '포지션',

        # Live Monitor
        'live_title': '📡 실시간 시장 모니터',
        'live_warning': '⚠️ 실시간 모니터링은 실제 시장 데이터가 필요합니다. 사이드바에서 "시뮬레이션 데이터 사용"을 해제하세요.',
        'auto_refresh': '자동 새로고침 (30초)',
        'refresh_now': '지금 새로고침',
        'fetching_data': '최신 데이터 가져오는 중...',
        'current_signal': '현재 신호',
        'signal': '신호',
        'timestamp': '타임스탬프',
        'indicator_values': '📊 지표 값',
        'recent_data': '최근 데이터',

        # Footer
        'footer': 'Streamlit으로 제작 | Quant Trading Lab v2.0',

        # Market selection
        'market_type': '마켓 종류',
        'crypto_market': '암호화폐',
        'stock_market': '해외주식 (미국)',
        'select_market': '마켓 선택',

        # Stock specific
        'stock_symbol': '주식 심볼',
        'stock_search': '주식 검색',
        'sector': '섹터',
        'industry': '산업',
        'market_hours': '장 시간',
        'pre_market': '프리마켓',
        'regular_hours': '정규장',
        'after_hours': '애프터아워',
        'market_closed': '장 마감',
        'market_status': '시장 상태',
        'popular_stocks': '인기 종목',
        'us_market_hours': '미국 시장 시간 (EST)',
        'korea_time': '한국 시간 (KST)',
        'select_stock': '종목 선택',
        'select_stock_help': '실시간 시세를 볼 미국 주식을 선택하세요',
        'selected_symbol': '선택된 종목',

        # Real-time quotes (US-005)
        'current_price': '현재가',
        'open_price': '시가',
        'high_price': '고가',
        'low_price': '저가',
        'volume': '거래량',
        'change_amount': '등락',
        'fetching_quote': '실시간 시세 조회 중...',
        'kis_not_available': 'KIS 브로커를 사용할 수 없습니다. API 인증 정보를 설정해주세요.',
        'quote_fetch_error': '시세 조회 실패',
        'possible_causes': '가능한 원인',
        'cause_network': '네트워크 연결 문제',
        'cause_rate_limit': 'API 호출 제한 초과 (1분 대기)',
        'cause_invalid_symbol': '잘못된 종목 코드 또는 장 마감',
        'try_again': '잠시 후 다시 시도해주세요.'
    }
}

def get_text(key: str, lang: str = 'en') -> str:
    """Get translated text for a given key and language"""
    return TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)

def get_strategy_name(name: str, lang: str = 'en') -> str:
    """Get translated strategy name"""
    return get_text(name, lang)

def get_strategy_desc(strategy_key: str, lang: str = 'en') -> str:
    """Get translated strategy description"""
    desc_keys = {
        'Moving Average Crossover': 'ma_desc',
        'RSI Strategy': 'rsi_desc',
        'MACD Strategy': 'macd_desc',
        'Bollinger Bands': 'bb_desc',
        'Stochastic Oscillator': 'stoch_desc'
    }
    desc_key = desc_keys.get(strategy_key, '')
    return get_text(desc_key, lang)
