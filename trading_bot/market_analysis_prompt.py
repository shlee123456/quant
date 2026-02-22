"""
Market Analysis Prompt Builder

최적화/리포트 JSON 데이터를 읽어 Claude CLI용 Notion 분석 페이지 생성 프롬프트를 구성합니다.
Notion Enhanced Markdown 포맷을 강제하여 일관된 리포트 형식을 보장합니다.

Usage:
    from trading_bot.market_analysis_prompt import build_analysis_prompt

    prompt = build_analysis_prompt("reports/2026-02-20/session_report.json")
    # prompt를 Claude CLI에 전달하여 Notion 페이지 자동 생성
"""

import os
import json
import glob as glob_module
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


def _load_session_reports(session_reports_dir: str) -> list:
    """
    세션 리포트 디렉토리에서 *_report.json 파일들을 읽어 세션 요약 리스트를 반환합니다.

    Args:
        session_reports_dir: 세션 리포트 JSON 파일들이 있는 디렉토리 경로

    Returns:
        세션 요약 딕셔너리 리스트
    """
    sessions = []
    pattern = os.path.join(session_reports_dir, "*_report.json")
    report_files = sorted(glob_module.glob(pattern))

    for fpath in report_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                report = json.load(f)

            summary = report.get("summary", {})
            trades = report.get("trades", [])

            sessions.append({
                "session_id": report.get("session_id", "N/A"),
                "strategy_name": summary.get("strategy_name", "N/A"),
                "display_name": summary.get("display_name", summary.get("strategy_name", "N/A")),
                "initial_capital": summary.get("initial_capital", 0),
                "final_capital": summary.get("final_capital", 0),
                "total_return": summary.get("total_return", 0),
                "sharpe_ratio": summary.get("sharpe_ratio"),
                "max_drawdown": summary.get("max_drawdown", 0),
                "win_rate": summary.get("win_rate"),
                "total_trades": len(trades),
                "start_time": report.get("start_time", "N/A"),
                "end_time": report.get("end_time", "N/A"),
                "status": summary.get("status", "N/A"),
            })
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"세션 리포트 로드 실패: {fpath} - {e}")

    return sessions


def _build_session_data_block(sessions: list) -> str:
    """
    세션 요약 데이터를 프롬프트에 포함할 텍스트 블록으로 구성합니다.

    Args:
        sessions: _load_session_reports()가 반환한 세션 요약 리스트

    Returns:
        프롬프트에 삽입할 세션 데이터 텍스트
    """
    if not sessions:
        return ""

    lines = ["\n## 트레이딩 세션 데이터"]
    lines.append("아래 세션 데이터를 '7. 트레이딩 세션 분석' 섹션에 반영하세요.\n")

    for s in sessions:
        ret = s["total_return"]
        ret_str = f"+{ret}%" if ret and ret > 0 else f"{ret}%"
        sharpe = s["sharpe_ratio"] if s["sharpe_ratio"] is not None else "N/A"
        win_rate = f"{s['win_rate']}%" if s["win_rate"] is not None else "N/A"

        lines.append(f"### 세션: {s['display_name']}")
        lines.append(f"- **세션 ID**: {s['session_id']}")
        lines.append(f"- **전략**: {s['strategy_name']}")
        lines.append(f"- **초기 자본**: ${s['initial_capital']}")
        lines.append(f"- **최종 자본**: ${s['final_capital']}")
        lines.append(f"- **수익률**: {ret_str}")
        lines.append(f"- **샤프 비율**: {sharpe}")
        lines.append(f"- **최대 낙폭**: {s['max_drawdown']}%")
        lines.append(f"- **승률**: {win_rate}")
        lines.append(f"- **거래 횟수**: {s['total_trades']}")
        lines.append(f"- **기간**: {s['start_time']} ~ {s['end_time']}")
        lines.append(f"- **상태**: {s['status']}")
        lines.append("")

    return "\n".join(lines)


# Notion Enhanced Markdown 포맷 템플릿
NOTION_FORMAT_TEMPLATE = r"""
=== NOTION ENHANCED MARKDOWN FORMAT SPECIFICATION ===

아래 포맷은 **반드시 그대로** 따라야 합니다. 자유 형식이 아니라 EXACT 구조입니다.
모든 섹션, 테이블, callout, 색상 지정을 빠짐없이 아래 구조대로 출력하세요.

--- FORMAT RULES (MANDATORY) ---
1. ALL section headers (# 1., # 2., ...) MUST have {{{{color="blue"}}}}
2. ALL tables MUST have fit-page-width="true" header-row="true"
3. Header rows in tables MUST have color="blue_bg"
4. Notable/warning rows MUST have color="orange_bg"
5. Risk table headers MUST have color="red_bg"
6. Price changes: <span color="green"> for positive, <span color="red"> for negative
7. MACD: <span color="green">Bullish</span> or <span color="red">Bearish</span>
8. Use --- between ALL major sections
9. Use ::: callout blocks with appropriate icons and colors
10. Escape pipe characters as \\| inside callouts
11. Use <details><summary> for expandable sections
12. Fear & Greed history rows: green_bg for greed periods, red_bg for fear periods, yellow_bg for neutral
13. Start page with <table_of_contents/>
14. End page with ::: callout {{{{icon="📝" color="gray_bg"}}}} footer
15. Tables with stock symbols should have header-column="true"
--- END FORMAT RULES ---

--- EXACT PAGE STRUCTURE ---

<table_of_contents/>
---
# 1. 시장 전체 요약 {{{{color="blue"}}}}
::: callout {{{{icon="📅" color="gray_bg"}}}}
	**분석 일자**: {{date}}  \\|  **대상 종목**: {{count}}개 ({{symbols_list}})
:::
## 오늘의 시장 상황
[2-3 paragraphs analyzing today's market based on the provided data + WebSearch news]

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
<tr>
<td>공포탐욕 지수</td>
<td>**{{value}}**</td>
<td>[interpretation]</td>
</tr>
</table>

## 전반적인 시장 분위기
::: callout {{{{icon="⚠️" color="red_bg"}}}}
(Use red_bg for bearish, green_bg for bullish, yellow_bg for neutral. Choose appropriate emoji.)
	**[강세/약세/중립] ([Bullish/Bearish/Neutral])** — [explanation with data]
:::
---
# 2. 종목별 분석 {{{{color="blue"}}}}
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**현재가 (\\$)**</td>
<td>**5일 변화**</td>
<td>**20일 변화**</td>
<td>**RSI**</td>
<td>**MACD**</td>
<td>**레짐**</td>
<td>**주요 시그널**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable stocks (oversold/overbought/extreme moves)
<td>**{{SYMBOL}}**</td>
<td>{{price}}</td>
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
# 3. 주목할 종목 Top 3 {{{{color="blue"}}}}
## 🥇 1위: {{SYMBOL}} ({{Company}}) — {{action recommendation}}
::: callout {{{{icon="📌" color="yellow_bg"}}}}
	**현재가**: \\${{price}}  \\|  **20일 변화**: {{change}}  \\|  **RSI**: {{rsi}}  \\|  **레짐**: {{regime}}
:::
**선정 이유 및 기술적 근거**:
- [bullet points with technical analysis]
- **지지선**: \\${{support1}} / \\${{support2}}

**뉴스 근거**: [news-based analysis with sources]

> **의견**: [emoji] **[recommendation]** — [detailed reasoning with price targets]
---
(Repeat same structure for 🥈 2위 and 🥉 3위)
---
# 4. 공포/탐욕 지수 분석 {{{{color="blue"}}}}
## 현재 Fear & Greed Index
::: callout {{{{icon="😰" color="red_bg"}}}}
(Choose emoji and color based on value: 😰/red_bg for fear, 😊/green_bg for greed, 😐/yellow_bg for neutral)
	**현재값: {{value}} ({{classification}})** — [interpretation]
	측정 시각: {{timestamp}}
:::
## 차트 시각적 분석 (30일 히스토리)
[analysis of the Fear & Greed chart if chart image was provided]
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**기간**</td>
<td>**지수 범위**</td>
<td>**분류**</td>
<td>**특이사항**</td>
</tr>
<tr color="green_bg"> or <tr color="red_bg"> or <tr color="yellow_bg"> based on sentiment period
<td>{{period}}</td>
<td>{{range}}</td>
<td>{{classification}}</td>
<td>{{notes}}</td>
</tr>
[... periods]
</table>
## 최근 추세 변화 해석
[numbered analysis points]
## 기술적 지표와의 상관관계
[bullet points correlating F&G with RSI and other indicators]
::: callout {{{{icon="💡" color="blue_bg"}}}}
	**역발상 투자 관점**: [contrarian analysis]
:::
---
# 5. 뉴스 & 이벤트 분석 {{{{color="blue"}}}}
## 시장 전체 주요 뉴스
<details>
<summary>📰 거시경제 & 시장 이벤트</summary>
	[numbered news items with sources]
</details>
## 종목별 핵심 뉴스 분석
### [Theme/Category] ([affected symbols])
::: callout {{{{icon="🤖" color="orange_bg"}}}}
	**핵심 이슈**: [key issue description with source links]
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
# 6. 전략 파라미터 제안 {{{{color="blue"}}}}
## 현재 시장 환경 평가
[bullet points]
## RSI 파라미터 제안
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**종목**</td>
<td>**최적 Oversold**</td>
<td>**최적 Overbought**</td>
<td>**근거**</td>
</tr>
<tr> or <tr color="orange_bg"> for notable entries
<td>{{symbol}}</td>
<td>**{{oversold}}**</td>
<td>{{overbought}}</td>
<td>{{reason}}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {{{{icon="📊" color="yellow_bg"}}}}
	**[MACD recommendation]**
	[details]
:::
## 추천 전략
[numbered strategy recommendations]
---
{session_section_placeholder}
# {risk_section_number}. 리스크 요인 {{{{color="blue"}}}}
## 시장 주요 리스크
[numbered risk items]
## 변동성 이상 종목
<table fit-page-width="true" header-row="true">
<tr color="red_bg">
<td>**종목**</td>
<td>**리스크 유형**</td>
<td>**주의 사항**</td>
</tr>
<tr>
<td>{{symbol}}</td>
<td>{{risk_type}}</td>
<td>{{caution}}</td>
</tr>
[... all notable symbols]
</table>
## 뉴스 기반 잠재 리스크
[bullet points]
---
::: callout {{{{icon="📝" color="gray_bg"}}}}
	**분석 생성**: {{date}}  \\|  **데이터 수집**: {{date}} {{time}} KST  \\|  **공포탐욕 지수 수집**: {{date}} {{time}} KST
	**주의사항**: 본 분석은 자동 수집된 데이터와 기술적 지표를 기반으로 생성된 참고 자료입니다. 실제 투자 결정은 개인의 판단과 책임 하에 이루어져야 합니다.
:::

--- END EXACT PAGE STRUCTURE ---
"""

SESSION_SECTION_TEMPLATE = r"""# 7. 트레이딩 세션 분석 {{{{color="blue"}}}}
## 세션 실행 결과
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**세션**</td>
<td>**전략**</td>
<td>**초기 자본**</td>
<td>**최종 자본**</td>
<td>**수익률**</td>
<td>**거래 횟수**</td>
</tr>
<tr>
<td>{{session_display_name}}</td>
<td>{{strategy}}</td>
<td>\\${{initial}}</td>
<td>\\${{final}}</td>
<td><span color="green">+{{return}}%</span> or <span color="red">{{return}}%</span></td>
<td>{{trades}}</td>
</tr>
[... repeat for all sessions from the provided session data]
</table>
## 세션별 분석
[per-session analysis: strategy effectiveness, trades detail if any, comparison between sessions]
## 전략 효과 평가
::: callout {{{{icon="📈" color="blue_bg"}}}}
	[evaluation of strategy effectiveness based on session results and market conditions]
:::
---
"""


def build_analysis_prompt(json_path: str, session_reports_dir: str = None) -> str:
    """
    JSON 리포트 파일을 읽어 Claude CLI용 Notion 시장 분석 페이지 생성 프롬프트를 구성합니다.
    Notion Enhanced Markdown 포맷을 강제하여 일관된 리포트 형식을 보장합니다.

    Args:
        json_path: 분석할 JSON 리포트 파일 경로
        session_reports_dir: 세션 리포트 JSON 파일들이 있는 디렉토리 경로 (선택)

    Returns:
        Claude CLI에 전달할 프롬프트 문자열

    Raises:
        FileNotFoundError: JSON 파일이 존재하지 않을 때
        json.JSONDecodeError: JSON 파싱에 실패했을 때
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # JSON 덤프 시 news/fear_greed_index는 별도 블록으로 추출하므로 중복 제거 (프롬프트 경량화)
    json_for_prompt = {k: v for k, v in data.items() if k not in ('news', 'fear_greed_index')}
    json_str = json.dumps(json_for_prompt, ensure_ascii=False, indent=2)

    today = datetime.now().strftime("%Y-%m-%d")
    parent_page_id = get_notion_page_id()

    # 뉴스 데이터 블록
    news_data_block = ""
    has_news = 'news' in data and data['news']
    if has_news:
        news = data['news']
        news_lines = []

        market_news = news.get('market_news', [])
        if market_news:
            news_lines.append("### 시장 전체 뉴스")
            for item in market_news:
                news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        stock_news = news.get('stock_news', {})
        if stock_news:
            news_lines.append("\n### 종목별 뉴스")
            for symbol, items in stock_news.items():
                news_lines.append(f"\n**{symbol}**:")
                for item in items[:3]:
                    news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        news_data_block = "\n## 수집된 뉴스 데이터\n" + "\n".join(news_lines)

    # Fear & Greed Index 데이터 블록
    fear_greed_data_block = ""
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

        fear_greed_data_block = "\n## 공포/탐욕 지수 (Fear & Greed Index)\n" + "\n".join(fg_lines)

    # 세션 리포트 데이터 블록
    session_data_block = ""
    has_sessions = False
    if session_reports_dir and os.path.isdir(session_reports_dir):
        sessions = _load_session_reports(session_reports_dir)
        if sessions:
            has_sessions = True
            session_data_block = _build_session_data_block(sessions)

    # 세션 섹션 유무에 따라 포맷 템플릿 조정
    if has_sessions:
        session_section = SESSION_SECTION_TEMPLATE
        risk_section_number = "8"
    else:
        session_section = ""
        risk_section_number = "7"

    format_spec = NOTION_FORMAT_TEMPLATE.replace(
        "{session_section_placeholder}", session_section
    ).replace(
        "{risk_section_number}", risk_section_number
    )

    prompt = f"""아래 JSON은 오늘의 트레이딩 세션 데이터입니다.
이 데이터를 분석하여 Notion에 시장 분석 페이지를 생성해주세요.

Notion MCP 도구(notion-create-pages)를 사용하여 다음 상위 페이지의 하위 페이지로 생성하세요:
- 상위 페이지 ID: {parent_page_id}
- 페이지 제목: "📊 시장 분석 | {today}"

## 추가 지시사항 (WebSearch 활용)
- WebSearch 도구를 사용하여 각 종목의 최신 뉴스와 시장 동향을 추가로 검색하세요.
- 특히 기술적 지표에서 주목할 종목(극단적 과매도/과매수, 급등/급락)의 뉴스를 심층 검색하세요.
- 뉴스와 기술적 지표를 종합하여 더 정확한 분석을 제공하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.
{news_data_block}
{fear_greed_data_block}
{session_data_block}

## ⚠️ 필수 출력 포맷 (MANDATORY)

아래 Notion Enhanced Markdown 포맷을 **반드시 정확히** 따라야 합니다.
이 포맷은 제안이 아니라 **필수 사양**입니다. 구조, 색상, callout, 테이블 형식을 모두 준수하세요.
{format_spec}
---

JSON 데이터:
```json
{json_str}
```"""

    logger.info(f"시장 분석 프롬프트 생성 완료 (JSON: {json_path}, 날짜: {today}, 세션 데이터: {has_sessions})")

    return prompt
