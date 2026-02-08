"""
공통 pytest fixtures

모든 테스트에서 사용 가능한 fixture 정의
"""

import os
import pytest
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


@pytest.fixture
def kis():
    """한국투자증권 API 클라이언트 fixture

    환경 변수에서 KIS API 인증 정보를 로드하고 PyKis 객체를 생성합니다.
    환경 변수가 설정되지 않았으면 테스트를 건너뜁니다.

    필요한 환경 변수:
        - KIS_ID: 한국투자증권 ID
        - KIS_APPKEY: API Key
        - KIS_APPSECRET: API Secret
        - KIS_ACCOUNT: 계좌번호
        - KIS_MOCK: 모의투자 여부 (기본값: true)

    Returns:
        PyKis: 한국투자증권 API 클라이언트
    """
    # 환경 변수 로드
    user_id = os.getenv('KIS_ID')
    appkey = os.getenv('KIS_APPKEY')
    appsecret = os.getenv('KIS_APPSECRET')
    account = os.getenv('KIS_ACCOUNT')
    mock = os.getenv('KIS_MOCK', 'true').lower() == 'true'

    # 환경 변수가 설정되지 않으면 테스트 건너뛰기
    if not all([user_id, appkey, appsecret, account]):
        pytest.skip("KIS API credentials not set in .env")

    try:
        # PyKis는 lazy import로 처리 (선택적 의존성)
        from pykis import PyKis

        # PyKis 객체 생성
        kis_client = PyKis(
            id=user_id,
            appkey=appkey,
            secretkey=appsecret,
            virtual_id=user_id,
            virtual_appkey=appkey,
            virtual_secretkey=appsecret,
            account=account
        )

        return kis_client

    except ImportError:
        pytest.skip("pykis package not installed")
    except Exception as e:
        pytest.skip(f"Failed to initialize PyKis: {e}")
