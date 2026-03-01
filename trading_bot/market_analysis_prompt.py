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

MACRO_SECTION_TEMPLATE = r"""# 0. 매크로 시장 환경 {{{{color="blue"}}}}
::: callout {{{{icon="🌍" color="blue_bg"}}}}
	**시장 환경 종합**: [매크로 데이터의 overall 요약을 기반으로 한 1-2문장]
:::
## 주요 지수 동향
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**지수**</td>
<td>**현재가**</td>
<td>**1일**</td>
<td>**5일**</td>
<td>**20일**</td>
<td>**RSI**</td>
<td>**해석**</td>
</tr>
<tr>
<td>**SPY** (S&P 500)</td>
<td>\\${{price}}</td>
<td><span color="red/green">{{chg}}</span></td>
<td><span color="red/green">{{chg}}</span></td>
<td><span color="red/green">{{chg}}</span></td>
<td>{{rsi}}</td>
<td>[interpretation]</td>
</tr>
[... QQQ, DIA, IWM rows]
</table>
## 섹터 상대강도 히트맵
<table fit-page-width="true" header-row="true" header-column="true">
<tr color="blue_bg">
<td>**순위**</td>
<td>**섹터**</td>
<td>**ETF**</td>
<td>**5일 수익률**</td>
<td>**20일 수익률**</td>
<td>**RSI**</td>
<td>**강약**</td>
</tr>
<tr color="green_bg"> for top 3 sectors
<td>1</td>
<td>{{sector_name}}</td>
<td>{{ETF}}</td>
<td><span color="green">+{{chg}}%</span></td>
<td>...</td>
<td>{{rsi}}</td>
<td>🟢 강세</td>
</tr>
[... middle sectors with no color]
<tr color="red_bg"> for bottom 3 sectors
<td>9</td>
<td>{{sector_name}}</td>
<td>{{ETF}}</td>
<td><span color="red">-{{chg}}%</span></td>
<td>...</td>
<td>{{rsi}}</td>
<td>🔴 약세</td>
</tr>
</table>
## 섹터 로테이션 & 시장 폭
::: callout {{{{icon="🔄" color="yellow_bg"}}}}
	**섹터 로테이션**: [공격적 vs 방어적 평균 비교 분석]
	**시장 폭**: SPY vs IWM 괴리 {{value}}%p — [interpretation]
	상승 섹터 {{n}}개 / 하락 섹터 {{n}}개
:::
## 리스크 환경
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**자산**</td>
<td>**5일 변화**</td>
<td>**의미**</td>
</tr>
<tr>
<td>**TLT** (장기국채)</td>
<td><span color="green/red">{{chg}}%</span></td>
<td>[금리 하락/상승 해석]</td>
</tr>
<tr>
<td>**GLD** (금)</td>
<td><span color="green/red">{{chg}}%</span></td>
<td>[안전자산 수요 해석]</td>
</tr>
<tr>
<td>**HYG** (하이일드 채권)</td>
<td><span color="green/red">{{chg}}%</span></td>
<td>[신용 스프레드 해석]</td>
</tr>
</table>
::: callout {{{{icon="⚡" color="orange_bg"}}}}
	**리스크 판단**: [risk_environment assessment 기반 분석]
:::
---
"""


INTELLIGENCE_SECTION_TEMPLATE = r"""# 0.5 시장 인텔리전스 대시보드 {{{{color="blue"}}}}
::: callout {{{{icon="🧠" color="blue_bg"}}}}
	**종합 시장 점수**: {{score}} ({{signal}}) — {{interpretation}}
:::
## 5-Layer 분석 결과
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**Layer**</td>
<td>**점수**</td>
<td>**시그널**</td>
<td>**신뢰도**</td>
<td>**핵심 판단**</td>
</tr>
{{layer_rows}}
</table>
## Layer별 핵심 지표
{{layer_details}}
---
"""


def _build_intelligence_data_block(intelligence: dict) -> str:
    """인텔리전스 데이터를 프롬프트에 포함할 텍스트 블록으로 구성합니다.

    Args:
        intelligence: MarketIntelligence.analyze() 반환값

    Returns:
        프롬프트에 삽입할 인텔리전스 데이터 텍스트
    """
    if not intelligence:
        return ""

    overall = intelligence.get('overall', {})
    lines = ["\n## 5-Layer 시장 인텔리전스 데이터"]
    lines.append(
        f"- **종합 점수**: {overall.get('score', 0):+.1f} "
        f"({overall.get('signal', 'N/A')})"
    )
    lines.append(f"- **종합 판단**: {overall.get('interpretation', 'N/A')}")

    layer_names_kr = {
        'macro_regime': 'Layer 1: 매크로 레짐',
        'market_structure': 'Layer 2: 시장 구조',
        'sector_rotation': 'Layer 3: 섹터/팩터 로테이션',
        'enhanced_technicals': 'Layer 4: 기술적 분석',
        'sentiment': 'Layer 5: 센티먼트',
    }

    layers = intelligence.get('layers', {})
    for key, data in layers.items():
        name = layer_names_kr.get(key, key)
        score = data.get('score', 0)
        signal = data.get('signal', 'N/A')
        conf = data.get('confidence', 0)
        interp = data.get('interpretation', '')
        lines.append(f"\n### {name}")
        lines.append(f"- 점수: {score:+.1f} ({signal}), 신뢰도: {conf:.0%}")
        lines.append(f"- 판단: {interp}")

    return "\n".join(lines)


def _build_events_data_block(events_data: dict) -> str:
    """이벤트 캘린더 데이터를 프롬프트에 포함할 텍스트 블록으로 구성합니다.

    Args:
        events_data: EventCalendarCollector.collect() 반환값

    Returns:
        프롬프트에 삽입할 이벤트 캘린더 텍스트
    """
    if not events_data:
        return ""

    lines = ["\n## 이벤트 캘린더"]

    # FOMC 일정
    fomc = events_data.get('fomc', {})
    next_fomc = fomc.get('next_date')
    fomc_days = fomc.get('days_until')
    if next_fomc:
        lines.append(f"- 다음 FOMC: {next_fomc} ({fomc_days}일 후)")
        remaining = fomc.get('remaining_2026', [])
        if len(remaining) > 1:
            lines.append(f"- 2026년 남은 FOMC: {len(remaining) - 1}회 ({', '.join(remaining[1:])})")

    # 실적발표 일정
    earnings = events_data.get('earnings', {})
    if earnings:
        lines.append("")
        for symbol, info in sorted(earnings.items(), key=lambda x: x[1].get('days_until', 999)):
            eps_str = f", 컨센서스 EPS ${info['estimate_eps']:.2f}" if info.get('estimate_eps') is not None else ""
            rev_str = f", 예상 매출 ${info['estimate_revenue']:,.0f}" if info.get('estimate_revenue') is not None else ""
            lines.append(f"- {symbol} 실적발표: {info['date']} ({info['days_until']}일 후){eps_str}{rev_str}")

    return "\n".join(lines)


def _build_fundamentals_data_block(fundamentals_data: dict) -> str:
    """펀더멘탈 데이터를 마크다운 테이블로 변환

    Args:
        fundamentals_data: FundamentalCollector.collect() 반환값

    Returns:
        프롬프트에 삽입할 펀더멘탈 데이터 텍스트
    """
    if not fundamentals_data:
        return ''

    funds = fundamentals_data.get('fundamentals', {})
    if not funds:
        return ''

    lines = ['\n## Company Fundamentals']
    lines.append('| Symbol | P/E | Forward P/E | EPS | Dividend | Sector | Beta | 52W High/Low |')
    lines.append('|--------|-----|------------|-----|----------|--------|------|-------------|')

    for symbol, data in funds.items():
        pe = f"{data.get('pe_ratio'):.1f}" if isinstance(data.get('pe_ratio'), (int, float)) else '-'
        fpe = f"{data.get('forward_pe'):.1f}" if isinstance(data.get('forward_pe'), (int, float)) else '-'
        eps = f"{data.get('eps'):.2f}" if isinstance(data.get('eps'), (int, float)) else '-'
        div = f"{data.get('dividend_yield', 0)*100:.2f}%" if isinstance(data.get('dividend_yield'), (int, float)) else '-'
        sector = data.get('sector', '-')
        beta = f"{data.get('beta'):.2f}" if isinstance(data.get('beta'), (int, float)) else '-'
        high = data.get('fifty_two_week_high')
        low = data.get('fifty_two_week_low')
        high_str = f"${high:.0f}" if isinstance(high, (int, float)) else '-'
        low_str = f"${low:.0f}" if isinstance(low, (int, float)) else '-'

        lines.append(f'| {symbol} | {pe} | {fpe} | {eps} | {div} | {sector} | {beta} | {high_str}/{low_str} |')

    return '\n'.join(lines)


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

    # JSON 덤프 시 news/fear_greed_index/macro/intelligence는 별도 블록으로 추출하므로 중복 제거 (프롬프트 경량화)
    json_for_prompt = {k: v for k, v in data.items() if k not in ('news', 'fear_greed_index', 'macro', 'intelligence')}
    json_str = json.dumps(json_for_prompt, ensure_ascii=False, indent=2)

    today = datetime.now().strftime("%Y-%m-%d")
    parent_page_id = get_notion_page_id()

    # 매크로 시장 환경 데이터 블록
    macro_data_block = ""
    has_macro = 'macro' in data and data['macro']
    if has_macro:
        macro = data['macro']
        macro_lines = []

        # 주요 지수
        macro_lines.append("### 주요 지수 현황")
        indices = macro.get('indices', {})
        for sym, info in indices.items():
            chg_1d = info.get('chg_1d', 0)
            chg_5d = info.get('chg_5d', 0)
            chg_20d = info.get('chg_20d', 0)
            sign_1d = '+' if chg_1d and chg_1d > 0 else ''
            sign_5d = '+' if chg_5d > 0 else ''
            sign_20d = '+' if chg_20d and chg_20d > 0 else ''
            macro_lines.append(
                f"- **{sym}**: ${info.get('last', 'N/A')} "
                f"(1일 {sign_1d}{chg_1d}%, 5일 {sign_5d}{chg_5d}%, 20일 {sign_20d}{chg_20d}%, RSI {info.get('rsi', 'N/A')})"
            )

        # 섹터 랭킹 (5일 수익률 기준 정렬)
        macro_lines.append("\n### 섹터 상대강도 (5일 수익률 순)")
        sectors = macro.get('sectors', {})
        sorted_sectors = sorted(sectors.items(), key=lambda x: x[1].get('rank_5d', 99))
        for sym, info in sorted_sectors:
            chg_5d = info.get('chg_5d', 0)
            chg_20d = info.get('chg_20d', 0)
            sign_5d = '+' if chg_5d > 0 else ''
            sign_20d = '+' if chg_20d and chg_20d > 0 else ''
            rank_20d = info.get('rank_20d', '?')
            macro_lines.append(
                f"- #{info.get('rank_5d', '?')} **{info.get('name', sym)}**({sym}): "
                f"5일 {sign_5d}{chg_5d}%, 20일 {sign_20d}{chg_20d}% (20일순위 #{rank_20d}, RSI {info.get('rsi', 'N/A')})"
            )

        # 섹터 로테이션
        rotation = macro.get('rotation', {})
        if rotation:
            macro_lines.append(f"\n### 섹터 로테이션")
            macro_lines.append(f"- 공격적 섹터 평균: {rotation.get('offensive_avg_5d', 'N/A')}%")
            macro_lines.append(f"- 방어적 섹터 평균: {rotation.get('defensive_avg_5d', 'N/A')}%")
            macro_lines.append(f"- **판단**: {rotation.get('signal', 'N/A')}")

        # 시장 폭
        breadth = macro.get('breadth', {})
        if breadth:
            macro_lines.append(f"\n### 시장 폭 (Breadth)")
            macro_lines.append(f"- SPY vs IWM 5일 괴리: {breadth.get('spy_vs_iwm_5d', 'N/A')}%p")
            macro_lines.append(f"- SPY vs QQQ 5일 괴리: {breadth.get('spy_vs_qqq_5d', 'N/A')}%p")
            macro_lines.append(f"- 5일 상승 섹터: {breadth.get('sectors_positive_5d', 0)}개 / 하락: {breadth.get('sectors_negative_5d', 0)}개")
            macro_lines.append(f"- **해석**: {breadth.get('interpretation', 'N/A')}")

        # 리스크 환경
        risk = macro.get('risk_environment', {})
        if risk:
            macro_lines.append(f"\n### 리스크 환경")
            macro_lines.append(f"- TLT(장기국채) 5일: {risk.get('tlt_chg_5d', 'N/A')}%")
            macro_lines.append(f"- GLD(금) 5일: {risk.get('gld_chg_5d', 'N/A')}%")
            macro_lines.append(f"- HYG(하이일드) 5일: {risk.get('hyg_chg_5d', 'N/A')}%")
            macro_lines.append(f"- **판단**: {risk.get('assessment', 'N/A')}")

        # 종합
        overall = macro.get('overall', '')
        if overall:
            macro_lines.append(f"\n### 종합 판단")
            macro_lines.append(f"- {overall}")

        macro_data_block = "\n## 매크로 시장 환경 데이터\n" + "\n".join(macro_lines)

    # 5-Layer 인텔리전스 데이터 블록
    intelligence_data_block = ""
    has_intelligence = 'intelligence' in data and data['intelligence']
    if has_intelligence:
        intelligence_data_block = _build_intelligence_data_block(data['intelligence'])

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

    # 매크로 섹션 조건부 삽입 (<table_of_contents/> 다음, # 1. 앞)
    if has_macro:
        format_spec = format_spec.replace(
            "<table_of_contents/>\n---\n# 1.",
            "<table_of_contents/>\n---\n" + MACRO_SECTION_TEMPLATE + "# 1."
        )

    # 인텔리전스 섹션 조건부 삽입 (매크로 섹션 다음, # 1. 앞)
    if has_intelligence:
        format_spec = format_spec.replace(
            "---\n# 1.",
            "---\n" + INTELLIGENCE_SECTION_TEMPLATE + "# 1."
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
{macro_data_block}
{intelligence_data_block}
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

    logger.info(f"시장 분석 프롬프트 생성 완료 (JSON: {json_path}, 날짜: {today}, 매크로: {has_macro}, 인텔리전스: {has_intelligence}, 세션 데이터: {has_sessions})")

    return prompt
