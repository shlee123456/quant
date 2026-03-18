"""
Korean Market Parallel Prompt Builder

한국 시장 분석 Notion 페이지를 병렬로 생성하기 위한 워커별 프롬프트 빌더입니다.
US parallel_prompt_builder.py 와 동일한 구조이며, 한국 시장에 맞게 커스터마이징.

차이점:
- 섹터명: 반도체, 은행, 화학 등 한국식 분류
- 매크로 이벤트: 금통위, 한국 소비자물가 등
- F&G 섹션 -> VKOSPI 센티먼트 섹션으로 대체
- KOSPI MA200 추세 (SPY MA200 대신)
- 가격 표시: 원화(KRW)

Worker A: 섹션 0 (매크로), 1 (시장 요약), 2 (종목별 분석)
Worker B: 섹션 3 (Top 3), 4 (VKOSPI 센티먼트), 5 (뉴스)
Worker C: 섹션 6-9 (전략/전망/리스크)
Notion Writer: 조립된 콘텐츠로 Notion 페이지 생성

Usage:
    from trading_bot.kr_parallel_prompt_builder import (
        build_kr_worker_a_prompt,
        build_kr_worker_b_prompt,
        build_kr_worker_c_prompt,
        build_kr_notion_writer_prompt,
    )
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from trading_bot.kr_market_analyzer import KR_STOCK_NAMES

logger = logging.getLogger(__name__)

# 워커별 모델 ID 매핑
KR_WORKER_MODELS: Dict[str, str] = {
    'Worker-A': 'claude-sonnet-4-6',
    'Worker-B': 'claude-sonnet-4-6',
    'Worker-C': 'claude-haiku-4-5-20251001',
    'Notion-Writer': 'claude-haiku-4-5-20251001',
}

# Notion Enhanced Markdown 포맷 규칙
_KR_FORMAT_RULES: str = r"""--- FORMAT RULES (MANDATORY) ---
1. ALL section headers (# 0., # 1., ...) MUST have {color="blue"}
2. ALL tables MUST have fit-page-width="true" header-row="true"
3. Header rows in tables MUST have color="blue_bg"
4. Notable/warning rows MUST have color="orange_bg"
5. Risk table headers MUST have color="red_bg"
6. Price changes: <span color="green"> for positive, <span color="red"> for negative
7. MACD: <span color="green">Bullish</span> or <span color="red">Bearish</span>
8. Use --- between ALL major sections
9. Use ::: callout blocks with appropriate icons and colors
10. Escape pipe characters as \| inside callouts
11. Use <details><summary> for expandable sections
12. Tables with stock symbols should have header-column="true"
13. 가격은 원화(KRW) 형식으로 표시: ₩65,000 또는 65,000원
--- END FORMAT RULES ---"""


def _get_kr_notion_page_id() -> str:
    """한국 시장 분석용 Notion 페이지 ID를 환경변수에서 가져옵니다."""
    return os.getenv(
        'NOTION_KR_MARKET_ANALYSIS_PAGE_ID',
        'placeholder-kr-page-id',
    )


def _build_kr_stocks_json(market_data: Dict) -> str:
    """종목 데이터를 JSON 문자열로 직렬화합니다."""
    stocks = market_data.get('stocks', {})
    return json.dumps(stocks, ensure_ascii=False, indent=2, default=str)


def _build_kr_macro_block(macro_data: Optional[Dict]) -> str:
    """한국 매크로 데이터를 프롬프트 블록으로 구성합니다."""
    if not macro_data:
        return ""

    lines: List[str] = ["\n## 한국 매크로 시장 환경 데이터"]

    # 지수 (KOSPI, KOSDAQ)
    indices = macro_data.get('indices', {})
    if indices:
        lines.append("\n### 주요 지수")
        index_names = {'^KS11': 'KOSPI', '^KQ11': 'KOSDAQ'}
        for symbol, data in indices.items():
            name = index_names.get(symbol, symbol)
            lines.append(
                f"- **{name}**: {data.get('last', 'N/A'):,.2f} "
                f"(5일: {data.get('chg_5d', 'N/A')}%, 20일: {data.get('chg_20d', 'N/A')}%, "
                f"RSI: {data.get('rsi', 'N/A')})"
            )

    # 섹터
    sectors = macro_data.get('sectors', {})
    if sectors:
        lines.append("\n### 섹터 ETF 순위 (5일 수익률)")
        sorted_sectors = sorted(
            sectors.items(),
            key=lambda x: x[1].get('rank_5d', 999),
        )
        for symbol, data in sorted_sectors:
            lines.append(
                f"- {data.get('rank_5d', '?')}위 {data.get('name', symbol)}: "
                f"{data.get('chg_5d', 'N/A'):+.1f}%"
            )

    # 로테이션
    rotation = macro_data.get('rotation', {})
    if rotation:
        lines.append(f"\n### 로테이션: {rotation.get('signal', 'N/A')}")
        lines.append(
            f"- 공격적 섹터 평균: {rotation.get('offensive_avg_5d', 0):+.2f}%"
        )
        lines.append(
            f"- 방어적 섹터 평균: {rotation.get('defensive_avg_5d', 0):+.2f}%"
        )

    # 리스크 환경
    risk = macro_data.get('risk_environment', {})
    if risk:
        lines.append(f"\n### 리스크 환경: {risk.get('assessment', 'N/A')}")

    # 종합
    overall = macro_data.get('overall', '')
    if overall:
        lines.append(f"\n### 종합: {overall}")

    return "\n".join(lines)


def _build_kr_events_block(events_data: Optional[Dict]) -> str:
    """한국 이벤트 캘린더 데이터를 프롬프트 블록으로 구성합니다."""
    if not events_data:
        return ""

    lines: List[str] = ["\n## 한국 이벤트 캘린더"]

    # 금통위
    bok = events_data.get('bok_rate', {})
    if bok.get('next_date'):
        lines.append(
            f"- **금융통화위원회**: {bok['next_date']} (D-{bok.get('days_until', '?')})"
        )

    # 경제지표
    economic = events_data.get('economic', {})
    for key, label in [('cpi', '소비자물가'), ('gdp', 'GDP'), ('trade', '수출입통계')]:
        info = economic.get(key, {})
        if info.get('next_date'):
            lines.append(
                f"- **{label}**: {info['next_date']} (D-{info.get('days_until', '?')})"
            )

    # 옵션만기
    options = events_data.get('options', {})
    expiry = options.get('monthly_expiry', {})
    if expiry.get('next_date'):
        lines.append(
            f"- **옵션만기**: {expiry['next_date']} (D-{expiry.get('days_until', '?')})"
        )

    # KRX 공휴일
    holidays = events_data.get('holidays', {})
    next_holiday = holidays.get('next_holiday', {})
    if next_holiday.get('date'):
        lines.append(
            f"- **다음 휴장일**: {next_holiday['date']} {next_holiday.get('name', '')} "
            f"(D-{next_holiday.get('days_until', '?')})"
        )

    return "\n".join(lines)


def _build_kr_intelligence_block(intelligence_data: Optional[Dict]) -> str:
    """5-Layer 인텔리전스 분석 결과를 프롬프트 블록으로 구성합니다."""
    if not intelligence_data:
        return ""

    lines: List[str] = ["\n## 5-Layer Market Intelligence (한국)"]
    overall = intelligence_data.get("overall", {})
    score = overall.get("score", 0)
    signal = overall.get("signal", "N/A")
    interpretation = overall.get("interpretation", "N/A")

    lines.append(f"**종합 점수**: {score:+.1f} ({signal})")
    lines.append(f"**종합 판단**: {interpretation}")

    return "\n".join(lines)


def _build_kr_daily_changes_block(daily_changes: Optional[Dict]) -> str:
    """전일 대비 변화 데이터를 프롬프트 블록으로 구성합니다."""
    if not daily_changes or not daily_changes.get('has_previous'):
        return ""

    lines: List[str] = [
        f"\n## 전일 대비 변화 (이전: {daily_changes.get('previous_date', '?')})"
    ]

    stocks_changes = daily_changes.get('stocks', {})
    if stocks_changes:
        for symbol, changes in stocks_changes.items():
            stock_name = KR_STOCK_NAMES.get(symbol, symbol)
            parts: List[str] = []
            if 'price_change_pct' in changes:
                parts.append(f"가격 {changes['price_change_pct']:+.2f}%")
            if 'rsi_change' in changes:
                parts.append(f"RSI {changes['rsi_change']:+.1f}")
            if parts:
                lines.append(f"- {stock_name}({symbol}): {', '.join(parts)}")

    return "\n".join(lines)


def _compute_kr_top3_candidates(
    market_data: Dict,
    previous_top3: Optional[List[str]] = None,
) -> Tuple[List[str], str]:
    """한국 TOP 3 종목 후보를 계산합니다."""
    stocks = market_data.get('stocks', {})
    if not stocks:
        return [], ""

    scored: List[Tuple[str, float]] = []
    for symbol, data in stocks.items():
        score = 0.0
        indicators = data.get('indicators', {})
        price = data.get('price', {})

        rsi_val = indicators.get('rsi', {}).get('value', 50)
        if rsi_val < 30:
            score += 3.0
        elif rsi_val < 40:
            score += 1.5
        elif rsi_val > 70:
            score += 2.0

        change_20d = price.get('change_20d')
        if change_20d is not None:
            if change_20d < -15:
                score += 3.0
            elif change_20d < -10:
                score += 2.0
            elif change_20d > 15:
                score += 2.0

        adx_val = indicators.get('adx', {}).get('value', 0)
        if adx_val > 30:
            score += 1.5

        macd_cross = indicators.get('macd', {}).get('cross_recent', False)
        if macd_cross:
            score += 1.0

        regime = data.get('regime', {}).get('state', '')
        if regime in ('BULLISH', 'BEARISH'):
            score += 0.5

        # 이전 TOP3 종목 페널티
        if previous_top3 and symbol in previous_top3:
            score -= 2.0

        scored.append((symbol, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top3_symbols = [s[0] for s in scored[:3]]

    info_lines: List[str] = []
    for symbol, sc in scored[:3]:
        stock_name = KR_STOCK_NAMES.get(symbol, symbol)
        info_lines.append(f"  - {stock_name}({symbol}): score={sc:.1f}")

    return top3_symbols, "\n".join(info_lines)


def build_kr_worker_a_prompt(
    market_data: Dict,
    today: str,
    macro_data: Optional[Dict] = None,
    intelligence_data: Optional[Dict] = None,
    events_data: Optional[Dict] = None,
    daily_changes: Optional[Dict] = None,
) -> str:
    """
    Worker A 프롬프트를 생성합니다.
    담당 섹션: 0 (매크로, macro_data 있을 때), 1 (시장 요약), 2 (종목별 분석)

    Args:
        market_data: 시장 분석 JSON 데이터
        today: 분석 날짜 (YYYY-MM-DD)
        macro_data: 매크로 시장 환경 데이터
        intelligence_data: Intelligence 분석 결과
        events_data: 이벤트 캘린더 데이터
        daily_changes: 전일 대비 변화 데이터

    Returns:
        Worker A용 프롬프트 문자열
    """
    stocks = market_data.get('stocks', {})
    symbols = list(stocks.keys())
    symbols_with_names = [
        f"{s}({KR_STOCK_NAMES.get(s, '?')})" for s in symbols
    ]
    symbols_str = ', '.join(symbols_with_names)

    macro_block = _build_kr_macro_block(macro_data)
    events_block = _build_kr_events_block(events_data)
    intel_block = _build_kr_intelligence_block(intelligence_data)
    daily_changes_block = _build_kr_daily_changes_block(daily_changes)

    # 매크로 섹션 템플릿
    macro_section_template = ""
    section_spec = "섹션 1, 2만"
    section_note = "섹션 1, 2만 출력합니다"
    if macro_data:
        section_spec = "섹션 0, 1, 2만"
        section_note = "섹션 0, 1, 2만 출력합니다"
        macro_section_template = """# 0. 한국 매크로 시장 환경 {color="blue"}
## KOSPI/KOSDAQ 지수 현황
[KOSPI, KOSDAQ 지수 분석: 현재가, 수익률, RSI, 거래량 변화]
## 섹터 로테이션 분석
[KODEX 섹터 ETF 순위표 + 해석]
## 리스크 환경
[국채/금 흐름 기반 리스크 평가]
---
"""

    json_str = json.dumps(stocks, ensure_ascii=False, indent=2, default=str)

    prompt = f"""당신은 한국 시장 분석 워커 A입니다.
아래 JSON 데이터를 분석하여 {section_spec} Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. {section_note}.

## WebSearch 활용 지시
- WebSearch 도구를 사용하여 각 종목의 최신 뉴스와 시장 동향을 검색하세요.
{intel_block}
- 특히 극단적 과매도/과매수, 급등/급락 종목의 뉴스를 심층 검색하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.
{macro_block}
{events_block}
{daily_changes_block}

## 대상 종목
{symbols_str} ({len(symbols)}개)

{_KR_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---
{macro_section_template}
# 1. 한국 시장 전체 요약 {{color="blue"}}
::: callout {{icon="📅" color="gray_bg"}}
\t**분석 일자**: {today}  \\|  **대상 종목**: {len(symbols)}개 ({symbols_str})
:::
## 오늘의 시장 상황
[2-3 paragraphs analyzing today's Korean market based on the provided data + WebSearch news]

## 주요 지표 요약
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**지표**</td>
<td>**값**</td>
<td>**해석**</td>
</tr>
<tr>
<td>평균 RSI</td>
<td>**{{value}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>강세 종목 수</td>
<td>**{{value}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>약세 종목 수</td>
<td>**{{value}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>횡보 종목 수</td>
<td>**{{value}}**</td>
<td>[interpretation]</td>
</tr>
</table>

## 전반적인 시장 분위기
::: callout {{icon="⚠️" color="red_bg"}}
(Use red_bg for bearish, green_bg for bullish, yellow_bg for neutral. Choose appropriate emoji.)
\t**[강세/약세/중립] ([Bullish/Bearish/Neutral])** — [explanation with data]
:::
---
# 2. 종목별 분석 {{color="blue"}}
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가 (원)**</td>
<td>**5일 변화**</td>
<td>**20일 변화**</td>
<td>**RSI**</td>
<td>**MACD**</td>
<td>**레짐**</td>
<td>**주요 시그널**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable stocks (oversold/overbought/extreme moves)
<td>**{{종목명(코드)}}**</td>
<td>{{price}}원</td>
<td><span color="red">{{negative%}}</span> or <span color="green">{{positive%}}</span></td>
<td><span color="red">{{negative%}}</span> or <span color="green">{{positive%}}</span></td>
<td>{{rsi}} ({{label}})</td>
<td><span color="red">Bearish</span> or <span color="green">Bullish</span></td>
<td>{{REGIME}} ({{confidence}}%)</td>
<td>{{signal_notes}}</td>
</tr>
[... repeat for all stocks]
</table>
---

--- END EXACT OUTPUT STRUCTURE ---

JSON 데이터:
```json
{json_str}
```"""

    logger.info(f"KR Worker A 프롬프트 생성 완료 (길이: {len(prompt)}자, 종목: {len(symbols)}개)")
    return prompt


def build_kr_worker_b_prompt(
    market_data: Dict,
    news_data: Dict,
    today: str,
    intelligence_data: Optional[Dict] = None,
    worker_a_context: Optional[str] = None,
    daily_changes: Optional[Dict] = None,
    previous_top3: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """
    Worker B 프롬프트를 생성합니다.
    담당 섹션: 3 (Top 3), 4 (VKOSPI 센티먼트), 5 (뉴스)

    Args:
        market_data: 시장 분석 JSON 데이터
        news_data: 뉴스 데이터 딕셔너리
        today: 분석 날짜 (YYYY-MM-DD)
        intelligence_data: Intelligence 분석 결과
        worker_a_context: Worker A의 출력 (교차 검증용)
        daily_changes: 전일 대비 변화 데이터
        previous_top3: 이전 TOP 3 종목 리스트

    Returns:
        (Worker B용 프롬프트 문자열, TOP 3 심볼 리스트) 튜플
    """
    stocks = market_data.get('stocks', {})
    stocks_json = json.dumps(stocks, ensure_ascii=False, indent=2, default=str)

    # TOP 3 후보 계산
    top3_symbols, top3_info = _compute_kr_top3_candidates(
        market_data, previous_top3=previous_top3
    )

    # 뉴스 블록
    news_block = ""
    if news_data:
        news_block = "\n## 수집된 뉴스 데이터\n"
        market_news = news_data.get('market_news', [])
        if market_news:
            news_block += "### 시장 전체 뉴스\n"
            for item in market_news[:5]:
                news_block += f"- [{item.get('title', '')}]({item.get('link', '')}) — {item.get('source', '')}\n"

        stock_news = news_data.get('stock_news', {})
        if stock_news:
            news_block += "\n### 종목별 뉴스\n"
            for symbol, news_list in stock_news.items():
                stock_name = KR_STOCK_NAMES.get(symbol, symbol)
                news_block += f"#### {stock_name}({symbol})\n"
                for item in news_list[:3]:
                    news_block += f"- {item.get('title', '')} — {item.get('source', '')}\n"

    # 인텔리전스 요약
    intel_summary = _build_kr_intelligence_block(intelligence_data)

    # TOP 3 후보 안내
    top3_block = ""
    if top3_symbols:
        names = [f"{s}({KR_STOCK_NAMES.get(s, '?')})" for s in top3_symbols]
        top3_block = f"\n## TOP 3 후보 (코드 기반 선정)\n추천 순서: {', '.join(names)}\n{top3_info}"

    # 이전 TOP 3 안내
    prev_top3_block = ""
    if previous_top3:
        prev_names = [f"{s}({KR_STOCK_NAMES.get(s, '?')})" for s in previous_top3]
        prev_top3_block = f"\n## 이전 TOP 3 (중복 방지)\n이전: {', '.join(prev_names)}\n가능하면 다른 종목을 선정하세요."

    # Reflection 블록
    reflection_block = ""
    if worker_a_context:
        reflection_block = f"\n## Worker A 분석 결과 (교차 검증용)\n{worker_a_context[:2000]}"

    daily_changes_block = _build_kr_daily_changes_block(daily_changes)

    prompt = f"""당신은 한국 시장 분석 워커 B입니다.
아래 데이터를 분석하여 **섹션 3, 4, 5만** Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 섹션 3, 4, 5만 출력합니다.

## WebSearch + Read 도구 활용 지시 (예산 절약 중요!)
- WebSearch는 **최대 3회**만 사용하세요.
- 이미 수집된 뉴스 데이터가 아래에 있으므로, WebSearch는 추가 확인이 필요한 경우에만 사용하세요.
- **중요**: 도구 호출보다 최종 마크다운 출력 생성을 우선하세요.
{intel_summary}
{top3_block}
{prev_top3_block}
{reflection_block}
{news_block}
{daily_changes_block}

{_KR_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 3. 주목할 종목 Top 3 {{color="blue"}}
## 🥇 1위: {{종목명(코드)}} — {{action recommendation}}
::: callout {{icon="📌" color="yellow_bg"}}
\t**현재가**: {{price}}원  \\|  **20일 변화**: {{change}}  \\|  **RSI**: {{rsi}}  \\|  **레짐**: {{regime}}
:::
**선정 이유 및 기술적 근거**:
- [bullet points with technical analysis]
- **지지선**: {{support1}}원 / {{support2}}원

**뉴스 근거**: [news-based analysis with sources]

> **의견**: [emoji] **[recommendation]** — [detailed reasoning with price targets]
---
(Repeat same structure for 🥈 2위 and 🥉 3위)
---
# 4. VKOSPI 센티먼트 분석 {{color="blue"}}
## 현재 시장 변동성
::: callout {{icon="📊" color="yellow_bg"}}
\t**VKOSPI 기반 센티먼트 평가** — [WebSearch로 최신 VKOSPI 값 확인]
:::
## 투자심리 지표 분석
[VKOSPI 수준, 개인/외인/기관 수급 동향, 신용융자 잔고 등 분석]
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**지표**</td>
<td>**현재값**</td>
<td>**해석**</td>
</tr>
[... rows for VKOSPI, 수급 동향 등]
</table>
## 기술적 지표와의 상관관계
[bullet points correlating VKOSPI with RSI and other indicators]
::: callout {{icon="💡" color="blue_bg"}}
\t**역발상 투자 관점**: [contrarian analysis for Korean market]
:::
---
# 5. 뉴스 & 이벤트 분석 {{color="blue"}}
## 시장 전체 주요 뉴스
<details>
<summary>📰 거시경제 & 시장 이벤트</summary>
\t[numbered news items with sources]
</details>
## 종목별 핵심 뉴스 분석
### [Theme/Category] ([affected symbols])
::: callout {{icon="🤖" color="orange_bg"}}
\t**핵심 이슈**: [key issue description with source links]
:::
[bullet points per symbol]
[... more themes as needed]
## 기술적 지표 vs 뉴스 일치성 분석
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**기술적 시그널**</td>
<td>**뉴스 방향**</td>
<td>**일치 여부**</td>
</tr>
<tr>
<td>{{symbol}}</td>
<td>{{technical}}</td>
<td>{{news}}</td>
<td>✅ 일치 or ⚠️ 혼재 or ❌ 불일치</td>
</tr>
[... all symbols]
</table>
---

--- END EXACT OUTPUT STRUCTURE ---

종목 데이터:
```json
{stocks_json}
```"""

    logger.info(f"KR Worker B 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt, top3_symbols


def build_kr_worker_c_prompt(
    market_data: Dict,
    today: str,
    intelligence_data: Optional[Dict] = None,
    daily_changes: Optional[Dict] = None,
) -> str:
    """
    Worker C 프롬프트를 생성합니다.
    담당 섹션: 6 (전략 파라미터), 7 (전방 전망), 8 (리스크)

    Args:
        market_data: 시장 분석 JSON 데이터
        today: 분석 날짜 (YYYY-MM-DD)
        intelligence_data: Intelligence 분석 결과
        daily_changes: 전일 대비 변화 데이터

    Returns:
        Worker C용 프롬프트 문자열
    """
    stocks = market_data.get('stocks', {})
    stocks_json = json.dumps(stocks, ensure_ascii=False, indent=2, default=str)

    intel_summary = _build_kr_intelligence_block(intelligence_data)
    daily_changes_block = _build_kr_daily_changes_block(daily_changes)

    # 전방 전망 데이터 추출
    forward_data: Dict = {'support_resistance': {}, 'rsi_pending_signals': []}
    for symbol, data in stocks.items():
        stock_name = KR_STOCK_NAMES.get(symbol, symbol)
        patterns = data.get('patterns', {})
        support_levels = patterns.get('support_levels', [])
        last_price = data.get('price', {}).get('last')

        if support_levels and last_price:
            forward_data['support_resistance'][f"{stock_name}({symbol})"] = {
                'current_price': last_price,
                'support_levels': support_levels,
            }

        rsi_val = data.get('indicators', {}).get('rsi', {}).get('value', 50)
        diagnosis = data.get('signal_diagnosis', {})
        optimal = diagnosis.get('optimal_rsi_range', {})
        oversold = optimal.get('oversold', 35)
        overbought = optimal.get('overbought', 65)

        if abs(rsi_val - oversold) <= 3 or abs(rsi_val - overbought) <= 3:
            forward_data['rsi_pending_signals'].append({
                'symbol': f"{stock_name}({symbol})",
                'rsi': rsi_val,
                'threshold': oversold if abs(rsi_val - oversold) <= 3 else overbought,
                'type': 'buy' if abs(rsi_val - oversold) <= 3 else 'sell',
            })

    forward_json = json.dumps(forward_data, ensure_ascii=False, indent=2, default=str)

    prompt = f"""당신은 한국 시장 분석 워커 C입니다.
아래 데이터를 분석하여 아래 지정된 섹션만 Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 지정된 섹션만 출력합니다.
**중요**: 도구(WebSearch, Read 등)는 사용하지 마세요. 주어진 데이터만으로 분석하세요.
{intel_summary}
{daily_changes_block}

{_KR_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 6. 전략 파라미터 제안 {{color="blue"}}
## 현재 시장 환경 평가
[bullet points about Korean market environment]
## RSI 파라미터 제안
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**최적 Oversold**</td>
<td>**최적 Overbought**</td>
<td>**근거**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable entries
<td>{{종목명(코드)}}</td>
<td>**{{oversold}}**</td>
<td>{{overbought}}</td>
<td>{{reason}}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {{icon="📊" color="yellow_bg"}}
\t**[MACD recommendation for Korean stocks]**
\t[details]
:::
## 추천 전략
[numbered strategy recommendations for Korean market]
---
# 7. 전방 전망 {{color="blue"}}
## 주요 지지선/저항선
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가**</td>
<td>**지지선 1**</td>
<td>**지지선 2**</td>
<td>**지지선 3**</td>
<td>**현재가 대비 거리**</td>
</tr>
[... rows from support_resistance data]
</table>
## RSI 시그널 대기 종목
::: callout {{icon="🔔" color="yellow_bg"}}
[list stocks where RSI is within ±3 of their oversold/overbought thresholds]
:::
## 향후 주시 사항
[numbered points about what to watch for in Korean market]
---
# 8. 리스크 요인 {{color="blue"}}
## 시장 주요 리스크
[numbered risk items for Korean market: 환율, 금리, 반도체 업황, 지정학적 리스크 등]
## 변동성 이상 종목
<table fit-page-width="true" header-row="true">
<tr color="red_bg">
<td>**종목**</td>
<td>**리스크 유형**</td>
<td>**주의 사항**</td>
</tr>
[... rows for high-volatility or extreme-move stocks]
</table>
## 뉴스 기반 잠재 리스크
[bullet points - infer from data patterns, regime states, extreme indicators]
---

--- END EXACT OUTPUT STRUCTURE ---

## 전방 전망 데이터 (지지선/RSI 임계치 근접)
```json
{forward_json}
```

종목 데이터:
```json
{stocks_json}
```"""

    logger.info(f"KR Worker C 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


def build_kr_notion_writer_prompt(
    assembled_content: str,
    today: str,
    parent_page_id: str,
) -> str:
    """
    Notion Writer 프롬프트를 생성합니다.

    Args:
        assembled_content: assemble_sections()가 반환한 조립된 콘텐츠
        today: 분석 날짜 (YYYY-MM-DD)
        parent_page_id: Notion 상위 페이지 ID

    Returns:
        Notion Writer용 프롬프트 문자열
    """
    # 월별 폴더명 (예: "2026-03 KR")
    month_folder_name = f"{today[:7]} KR"

    prompt = f"""아래 콘텐츠를 Notion 페이지로 생성하세요.

## 페이지 생성 절차

**1단계: 월별 서브페이지 확인**
- 상위 페이지 ID {parent_page_id} 아래에서 "{month_folder_name}" 제목의 서브페이지를 notion-search 또는 notion-fetch로 찾으세요.
- 해당 서브페이지가 존재하면, 그 서브페이지의 ID를 상위 페이지로 사용하세요.
- 존재하지 않으면, 상위 페이지 ID {parent_page_id} 아래에 "{month_folder_name}" 제목의 빈 페이지를 먼저 생성하고, 그 페이지의 ID를 상위 페이지로 사용하세요.

**2단계: 시장 분석 페이지 생성**
- notion-create-pages 도구를 사용하여 다음 설정으로 페이지를 생성하세요:
  - 상위 페이지 ID: 1단계에서 확인/생성한 월별 서브페이지 ID
  - 페이지 제목: "🇰🇷 한국 시장 분석 | {today}"
  - 페이지 content: 아래 콘텐츠를 그대로 사용

**중요**:
- 아래 콘텐츠를 그대로 페이지 content로 사용하세요.
- 콘텐츠를 수정하거나 재작성하지 마세요.
- 백슬래시(\\)를 추가로 이스케이핑하지 마세요.
- 페이지 생성 후, 반드시 마지막에 생성된 페이지의 URL을 "NOTION_PAGE_URL: https://..." 형식으로 출력하세요.

--- 페이지 콘텐츠 시작 ---
{assembled_content}
--- 페이지 콘텐츠 끝 ---"""

    logger.info(f"KR Notion Writer 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


def assemble_kr_sections(
    worker_a_output: str,
    worker_b_output: str,
    worker_c_output: str,
    today: str,
) -> str:
    """3개 워커의 출력을 하나로 조립합니다.

    Args:
        worker_a_output: Worker A의 마크다운 출력
        worker_b_output: Worker B의 마크다운 출력
        worker_c_output: Worker C의 마크다운 출력
        today: 분석 날짜

    Returns:
        조립된 전체 마크다운 콘텐츠
    """
    footer = (
        f'::: callout {{icon="📝" color="gray_bg"}}\n'
        f'\t**분석 생성**: {today}  \\|  **데이터 수집**: {today} KST  \\|  '
        f'**병렬 생성**: Worker A + B + C\n'
        f'\t**주의사항**: 본 분석은 자동 수집된 데이터와 기술적 지표를 기반으로 '
        f'생성된 참고 자료입니다. 실제 투자 결정은 개인의 판단과 책임 하에 이루어져야 합니다.\n'
        f':::'
    )

    assembled = "\n\n".join([
        worker_a_output.strip(),
        worker_b_output.strip(),
        worker_c_output.strip(),
        footer,
    ])

    return assembled


def validate_kr_assembly(assembled: str, expected_sections: List[str]) -> bool:
    """조립된 콘텐츠에 필수 섹션이 모두 포함되어 있는지 검증합니다.

    Args:
        assembled: 조립된 마크다운 콘텐츠
        expected_sections: 기대하는 섹션 마커 리스트

    Returns:
        모든 섹션이 포함되어 있으면 True
    """
    missing: List[str] = []
    for section in expected_sections:
        if section not in assembled:
            missing.append(section)

    if missing:
        logger.warning(f"누락된 섹션: {missing}")
        return False

    return True
