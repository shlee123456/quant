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

    # 뉴스 데이터가 있으면 뉴스 섹션 추가
    news_section = ""
    has_news = 'news' in data and data['news']
    if has_news:
        news = data['news']
        news_lines = []

        # 시장 전체 뉴스
        market_news = news.get('market_news', [])
        if market_news:
            news_lines.append("### 시장 전체 뉴스")
            for item in market_news:
                news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        # 종목별 뉴스
        stock_news = news.get('stock_news', {})
        if stock_news:
            news_lines.append("\n### 종목별 뉴스")
            for symbol, items in stock_news.items():
                news_lines.append(f"\n**{symbol}**:")
                for item in items[:3]:  # 프롬프트 길이 제한을 위해 최대 3개
                    news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        news_section = "\n".join(news_lines)

    # Fear & Greed Index 섹션
    fear_greed_section = ""
    has_fear_greed = 'fear_greed_index' in data and data['fear_greed_index']
    if has_fear_greed:
        fg = data['fear_greed_index']
        current = fg.get('current', {})
        fg_lines = []
        fg_lines.append(f"### 현재 Fear & Greed Index")
        fg_lines.append(f"- **값**: {current.get('value', 'N/A')}")
        fg_lines.append(f"- **분류**: {current.get('classification', 'N/A')}")
        fg_lines.append(f"- **시각**: {current.get('timestamp', 'N/A')}")

        history = fg.get('history', [])
        if history:
            fg_lines.append(f"\n### 최근 {len(history)}일 히스토리")
            for item in history[:7]:
                fg_lines.append(f"- {item['date']}: {item['value']} ({item['classification']})")
            if len(history) > 7:
                fg_lines.append(f"- ... 외 {len(history) - 7}일")

        chart_path = fg.get('chart_path')
        if chart_path:
            fg_lines.append(f"\n### 차트")
            fg_lines.append(f"- 차트 파일 경로: `{chart_path}`")
            fg_lines.append(f"- Read 도구로 이 차트 이미지를 읽어서 시각적 분석에 반영하세요.")

        fear_greed_section = "\n".join(fg_lines)

    # WebSearch 사용 안내 (뉴스 유무와 관계없이 포함)
    websearch_instruction = """
## 추가 지시사항 (WebSearch 활용)
- WebSearch 도구를 사용하여 각 종목의 최신 뉴스와 시장 동향을 추가로 검색하세요.
- 특히 기술적 지표에서 주목할 종목(극단적 과매도/과매수, 급등/급락)의 뉴스를 심층 검색하세요.
- 뉴스와 기술적 지표를 종합하여 더 정확한 분석을 제공하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요."""

    # 뉴스 섹션 구성
    news_prompt_block = ""
    if has_news:
        news_prompt_block = f"""

## 수집된 뉴스 데이터
{news_section}
"""

    # Fear & Greed 섹션 구성
    fear_greed_prompt_block = ""
    if has_fear_greed:
        fear_greed_prompt_block = f"""

## 공포/탐욕 지수 (Fear & Greed Index)
{fear_greed_section}
"""

    prompt = f"""아래 JSON은 오늘의 트레이딩 세션 데이터입니다.
이 데이터를 분석하여 Notion에 시장 분석 페이지를 생성해주세요.

Notion MCP 도구(notion-create-pages)를 사용하여 다음 상위 페이지의 하위 페이지로 생성하세요:
- 상위 페이지 ID: {parent_page_id}
- 페이지 제목: "📊 시장 분석 | {today}"

페이지에 포함할 섹션:

1. **시장 전체 요약**
   - 오늘의 시장 상황 요약 (데이터 기반)
   - 주요 지표 (평균 RSI, 강세/약세 비율)
   - 전반적인 시장 분위기 판단

2. **종목별 분석** (테이블 형식)
   - 각 종목의 가격, 5일/20일 변화율, RSI, MACD, 레짐
   - 주요 시그널 및 패턴

3. **주목할 종목 Top 3**
   - 가장 주목해야 할 3개 종목 선정
   - 선정 이유와 기술적 근거 설명
   - 매수/매도/관망 의견

4. **공포/탐욕 지수 분석** (Fear & Greed Index 데이터가 있는 경우)
   - 현재 공포/탐욕 지수와 시장 심리 해석
   - 최근 추세 변화 (30일 히스토리 기반)
   - 기술적 지표와의 상관관계 분석
   - 차트 이미지가 제공된 경우 Read 도구로 읽어 시각적 분석 반영

5. **뉴스 & 이벤트 분석**
   - 수집된 뉴스와 WebSearch로 추가 검색한 뉴스를 종합
   - 뉴스가 기술적 지표와 일치하는지 분석
   - 시장에 영향을 줄 수 있는 주요 이벤트

6. **전략 파라미터 제안**
   - 현재 시장 상황에 맞는 RSI oversold/overbought 값 제안
   - MACD 사용 적합성 판단
   - 추천 전략과 근거

7. **리스크 요인**
   - 주의해야 할 시장 리스크
   - 변동성 이상 종목
   - 뉴스에서 발견된 잠재적 리스크
{websearch_instruction}
{news_prompt_block}
{fear_greed_prompt_block}
---

JSON 데이터:
```json
{json_str}
```"""

    logger.info(f"시장 분석 프롬프트 생성 완료 (JSON: {json_path}, 날짜: {today})")

    return prompt
