"""
Error Handler for Dashboard

Provides centralized error handling and user-friendly error messages.
"""

import streamlit as st
from typing import Optional
from dashboard.translations import get_text


class ErrorType:
    """Error type constants for categorizing errors"""
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    INVALID_SYMBOL = "invalid_symbol"
    MARKET_CLOSED = "market_closed"
    GENERIC = "generic"


def identify_error_type(exception: Exception) -> str:
    """
    Identify the type of error from the exception.

    Args:
        exception: The exception object

    Returns:
        Error type constant from ErrorType class
    """
    error_msg = str(exception).lower()

    # Check for rate limit errors
    if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', '429', 'quota']):
        return ErrorType.RATE_LIMIT

    # Check for network errors
    if any(keyword in error_msg for keyword in ['connection', 'timeout', 'network', 'unreachable', 'timed out']):
        return ErrorType.NETWORK

    # Check for authentication errors
    if any(keyword in error_msg for keyword in ['auth', 'unauthorized', '401', '403', 'forbidden', 'invalid key']):
        return ErrorType.AUTHENTICATION

    # Check for invalid symbol errors
    if any(keyword in error_msg for keyword in ['invalid symbol', 'not found', 'unknown symbol', 'does not exist']):
        return ErrorType.INVALID_SYMBOL

    # Check for market closed errors
    if any(keyword in error_msg for keyword in ['market closed', 'not trading', 'outside trading hours']):
        return ErrorType.MARKET_CLOSED

    return ErrorType.GENERIC


def display_error(
    exception: Exception,
    lang: str = 'en',
    context: Optional[str] = None,
    show_solution: bool = True
) -> None:
    """
    Display a user-friendly error message based on the error type.

    Args:
        exception: The exception object
        lang: Language code ('en' or 'ko')
        context: Optional context string (e.g., 'fetching quote', 'loading chart')
        show_solution: Whether to show solution suggestions
    """
    error_type = identify_error_type(exception)

    # Build error title and description
    if error_type == ErrorType.RATE_LIMIT:
        title = get_text('error_rate_limit', lang)
        description = get_text('error_rate_limit_desc', lang)
        icon = "⏱️"
        solutions = [
            f"⏰ {get_text('retry_after', lang)} 1-2 {get_text('minutes', lang)}",
            get_text('cause_rate_limit', lang)
        ]

    elif error_type == ErrorType.NETWORK:
        title = get_text('error_network', lang)
        description = get_text('error_network_desc', lang)
        icon = "🌐"
        solutions = [
            get_text('cause_network', lang),
            "VPN을 사용 중이라면 비활성화해보세요" if lang == 'ko' else "Try disabling VPN if enabled",
            "방화벽 설정을 확인하세요" if lang == 'ko' else "Check your firewall settings"
        ]

    elif error_type == ErrorType.AUTHENTICATION:
        title = get_text('error_authentication', lang)
        description = get_text('error_authentication_desc', lang)
        icon = "🔐"
        solutions = [
            get_text('check_credentials', lang),
            f"📖 [{get_text('view_readme', lang)}](https://github.com/yourusername/crypto-trading-bot#api-setup)",
            "API 키가 만료되었는지 확인하세요" if lang == 'ko' else "Check if your API keys have expired"
        ]

    elif error_type == ErrorType.INVALID_SYMBOL:
        title = get_text('error_invalid_symbol', lang)
        description = get_text('error_invalid_symbol_desc', lang)
        icon = "❓"
        solutions = [
            get_text('cause_invalid_symbol', lang),
            "지원되는 종목 코드 목록을 확인하세요" if lang == 'ko' else "Check the list of supported symbols",
            "종목 코드 철자를 확인하세요" if lang == 'ko' else "Verify the symbol spelling"
        ]

    elif error_type == ErrorType.MARKET_CLOSED:
        title = get_text('error_market_closed', lang)
        description = get_text('error_market_closed_desc', lang)
        icon = "🕐"
        solutions = [
            "미국 시장 정규장: 23:30-06:00 (KST)" if lang == 'ko' else "US Market Hours: 09:30-16:00 (EST)",
            "프리마켓/애프터아워 시간대에는 시세가 제한적일 수 있습니다" if lang == 'ko'
                else "Quotes may be limited during pre-market/after-hours"
        ]

    else:  # GENERIC
        title = get_text('error_generic', lang)
        description = str(exception)
        icon = "⚠️"
        solutions = [
            get_text('try_again', lang),
            "문제가 계속되면 GitHub Issues에 문의해주세요" if lang == 'ko'
                else "If the problem persists, please report it on GitHub Issues"
        ]

    # Display error message
    error_message = f"**{icon} {title}**\n\n{description}"

    if context:
        error_message = f"**{icon} {title}** ({context})\n\n{description}"

    # Add technical details in expander
    with st.expander(f"🔍 {get_text('troubleshooting', lang)}", expanded=False):
        st.error(f"**{get_text('error_generic', lang)}:** {str(exception)}")

        if show_solution:
            st.markdown(f"**{get_text('common_solutions', lang)}:**")
            for solution in solutions:
                st.markdown(f"- {solution}")

    # Display main error message
    st.error(error_message)


def handle_kis_broker_error(
    exception: Exception,
    lang: str = 'en',
    symbol: Optional[str] = None
) -> None:
    """
    Handle KIS broker-specific errors with enhanced context.

    Args:
        exception: The exception object
        lang: Language code ('en' or 'ko')
        symbol: Optional symbol being queried
    """
    context = None
    if symbol:
        context = f"{get_text('stock_symbol', lang)}: {symbol}"

    display_error(exception, lang=lang, context=context, show_solution=True)
