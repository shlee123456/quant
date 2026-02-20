"""
Market Analysis Prompt Builder

최적화/리포트 JSON 데이터를 읽어 Claude CLI용 Notion 분석 페이지 생성 프롬프트를 구성합니다.

Usage:
    from trading_bot.market_analysis_prompt import build_analysis_prompt

    prompt = build_analysis_prompt("reports/2026-02-20/session_report.json")
    # prompt를 Claude CLI에 전달하여 Notion 페이지 자동 생성
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 기본 Notion 페이지 ID (시장 분석 상위 페이지)
DEFAULT_NOTION_PAGE_ID = "30dd62f0-dffd-80a6-b624-e5a061ed26a9"


def get_notion_page_id() -> str:
    """
    Notion 시장 분석 상위 페이지 ID를 환경 변수에서 읽어 반환합니다.

    환경 변수 NOTION_MARKET_ANALYSIS_PAGE_ID가 설정되어 있으면 해당 값을 사용하고,
    없으면 기본값을 반환합니다.

    Returns:
        Notion 페이지 ID 문자열
    """
    return os.getenv("NOTION_MARKET_ANALYSIS_PAGE_ID", DEFAULT_NOTION_PAGE_ID)


def build_analysis_prompt(json_path: str) -> str:
    """
    JSON 리포트 파일을 읽어 Claude CLI용 Notion 시장 분석 페이지 생성 프롬프트를 구성합니다.

    Args:
        json_path: 분석할 JSON 리포트 파일 경로

    Returns:
        Claude CLI에 전달할 프롬프트 문자열

    Raises:
        FileNotFoundError: JSON 파일이 존재하지 않을 때
        json.JSONDecodeError: JSON 파싱에 실패했을 때
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    today = datetime.now().strftime("%Y-%m-%d")
    parent_page_id = get_notion_page_id()

    prompt = f"""아래 JSON은 오늘의 트레이딩 세션 데이터입니다.
이 데이터를 분석하여 Notion에 시장 분석 페이지를 생성해주세요.

Notion MCP 도구(notion-create-pages)를 사용하여 다음 상위 페이지의 하위 페이지로 생성하세요:
- 상위 페이지 ID: {parent_page_id}
- 페이지 제목: "📊 시장 분석 | {today}"

페이지에 포함할 섹션:

1. **시장 전체 요약**
   - 오늘의 시장 상황 요약 (데이터 기반)
   - 주요 지표 (총 수익률, 샤프 비율, 최대 낙폭, 승률)
   - 전반적인 시장 분위기 판단

2. **종목별 분석** (테이블 형식)
   - 각 종목의 매수/매도 시그널, 수익률, 거래 횟수
   - 포지션 현황 및 평가손익

3. **주목할 종목 Top 3**
   - 가장 높은 수익률 또는 강한 시그널을 보인 종목
   - 각 종목의 주목 이유 설명

4. **전략 파라미터 제안**
   - 현재 전략 파라미터 분석
   - 시장 상황에 맞는 파라미터 조정 제안
   - 다음 세션을 위한 권장 설정

5. **리스크 요인**
   - 현재 포트폴리오의 리스크 요소
   - 주의가 필요한 종목이나 상황
   - 손절/익절 기준 적정성 평가

---

JSON 데이터:
```json
{json_str}
```"""

    logger.info(f"시장 분석 프롬프트 생성 완료 (JSON: {json_path}, 날짜: {today})")

    return prompt
