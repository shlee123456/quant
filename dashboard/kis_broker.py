"""
KIS Broker Helper for Dashboard

한국투자증권 브로커 초기화를 위한 헬퍼 함수입니다.
환경 변수에서 인증 정보를 로드하여 브로커를 생성합니다.
"""

import os
from typing import Optional
import streamlit as st

from trading_bot.brokers import KoreaInvestmentBroker
from trading_bot.brokers.base_broker import BrokerError, AuthenticationError


def get_kis_broker() -> Optional[KoreaInvestmentBroker]:
    """
    환경 변수에서 한국투자증권 브로커를 초기화합니다.

    환경 변수에서 다음 값을 읽어옵니다:
    - KIS_APPKEY: 한국투자증권 AppKey
    - KIS_APPSECRET: 한국투자증권 AppSecret
    - KIS_ACCOUNT: 계좌번호 (예: 12345678-01)
    - KIS_USER_ID: 사용자 ID (선택, 기본값: KIS_ACCOUNT 값 사용)
    - KIS_MOCK: 모의투자 여부 (true/false, 기본값: true)

    Returns:
        KoreaInvestmentBroker: 초기화된 브로커 객체
        None: 초기화 실패 시 (환경 변수 누락, 인증 실패 등)

    Example:
        >>> broker = get_kis_broker()
        >>> if broker:
        ...     ticker = broker.fetch_ticker('AAPL', overseas=True)
        ...     print(ticker['last'])
        ... else:
        ...     print("KIS 브로커를 초기화할 수 없습니다.")

    Notes:
        - 환경 변수 누락 시 사용자에게 명확한 에러 메시지를 표시합니다.
        - Streamlit 환경에서 st.error()를 사용하여 에러를 표시합니다.
        - 초기화 실패 시 None을 반환하여 graceful degradation을 지원합니다.
    """
    # 필수 환경 변수 검증
    required_vars = {
        'KIS_APPKEY': 'Korea Investment APPKEY',
        'KIS_APPSECRET': 'Korea Investment APPSECRET',
        'KIS_ACCOUNT': 'Account number (e.g., 12345678-01)'
    }

    missing_vars = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value or value.strip() == '' or 'your_' in value.lower():
            missing_vars.append(f"- {var}: {description}")

    # 환경 변수 누락 시 명확한 에러 메시지 표시 (US-009)
    if missing_vars:
        error_message = (
            "**한국투자증권 API 환경 변수가 설정되지 않았습니다.**\n\n"
            "다음 환경 변수를 설정해주세요:\n\n"
            + "\n".join(missing_vars) + "\n\n"
            "**설정 방법:**\n"
            "1. `.env` 파일을 생성하거나 수정하세요.\n"
            "2. `.env.example` 파일을 참고하여 필요한 값을 입력하세요.\n"
        )
        st.error(error_message)

        # Add helpful links (US-009)
        st.info(
            "📖 **설정 가이드:**\n\n"
            "- [README - API Setup](https://github.com/yourusername/crypto-trading-bot#korea-investment-securities-api-setup)\n"
            "- [한국투자증권 API 신청](https://securities.koreainvestment.com/main/research/invest/PB_ETF_PopupTradingAPIInfo.jsp)"
        )
        return None

    # 환경 변수에서 값 읽기
    appkey = os.getenv('KIS_APPKEY', '').strip()
    appsecret = os.getenv('KIS_APPSECRET', '').strip()
    account = os.getenv('KIS_ACCOUNT', '').strip()

    # 선택적 환경 변수
    # KIS_USER_ID가 없으면 KIS_ACCOUNT 값을 사용
    user_id = os.getenv('KIS_USER_ID', account).strip()

    # 모의투자 여부 (기본값: true)
    mock_str = os.getenv('KIS_MOCK', 'true').strip().lower()
    mock = mock_str in ('true', '1', 'yes', 'on')

    try:
        # 브로커 초기화
        broker = KoreaInvestmentBroker(
            user_id=user_id,
            appkey=appkey,
            appsecret=appsecret,
            account=account,
            mock=mock
        )

        # 초기화 성공 메시지 (디버깅용)
        mode = "모의투자" if mock else "실전투자"
        st.success(f"✅ 한국투자증권 브로커 초기화 성공 ({mode} 모드)")

        return broker

    except AuthenticationError as e:
        # 인증 실패
        st.error(
            f"**한국투자증권 인증 실패:**\n\n"
            f"{str(e)}\n\n"
            f"**해결 방법:**\n"
            f"1. APPKEY와 APPSECRET이 올바른지 확인하세요.\n"
            f"2. 모의투자와 실전투자의 키가 다릅니다. KIS_MOCK 설정을 확인하세요.\n"
            f"3. API 키가 만료되었는지 확인하세요."
        )
        return None

    except BrokerError as e:
        # 브로커 초기화 실패
        st.error(
            f"**한국투자증권 브로커 초기화 실패:**\n\n"
            f"{str(e)}\n\n"
            f"**해결 방법:**\n"
            f"1. `python-kis` 라이브러리가 설치되어 있는지 확인하세요: `pip install python-kis`\n"
            f"2. 환경 변수 값이 올바른지 확인하세요.\n"
            f"3. 계좌번호 형식이 올바른지 확인하세요 (예: 12345678-01)."
        )
        return None

    except Exception as e:
        # 예상치 못한 에러
        st.error(
            f"**예상치 못한 에러가 발생했습니다:**\n\n"
            f"{str(e)}\n\n"
            f"문제가 계속되면 GitHub Issues에 문의해주세요."
        )
        return None
