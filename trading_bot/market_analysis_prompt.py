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

MACRO_SECTION_TEMPLATE_PARALLEL = r"""
# 0. 매크로 시장 환경 {color="blue"}
::: callout {icon="🌍" color="blue_bg"}
	**시장 환경 종합**: [매크로 데이터의 overall 요약 기반 1-2문장. 어떤 섹터가 강세/약세인지, 로테이션 방향, 리스크 환경 포함]
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
<td>\${price}</td>
<td><span color="red/green">{chg}</span></td>
<td><span color="red/green">{chg}</span></td>
<td><span color="red/green">{chg}</span></td>
<td>{rsi}</td>
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
<tr color="green_bg"> for top 3 sectors (rank 1-3)
<td>{rank}</td>
<td>{sector_name}</td>
<td>{ETF}</td>
<td><span color="green">+{chg}%</span></td>
<td>...</td>
<td>{rsi}</td>
<td>🟢 강세</td>
</tr>
[... middle sectors with no special color]
<tr color="red_bg"> for bottom 3 sectors (rank 9-11)
<td>{rank}</td>
<td>{sector_name}</td>
<td>{ETF}</td>
<td><span color="red">-{chg}%</span></td>
<td>...</td>
<td>{rsi}</td>
<td>🔴 약세</td>
</tr>
</table>
## 섹터 로테이션 & 시장 폭
::: callout {icon="🔄" color="yellow_bg"}
	**섹터 로테이션**: [공격적 vs 방어적 평균 비교 분석. signal 데이터 활용]
	**시장 폭**: SPY vs IWM 괴리 {value}%p — [interpretation 데이터 활용]
	상승 섹터 {n}개 / 하락 섹터 {n}개
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
<td><span color="green/red">{chg}%</span></td>
<td>[금리 하락=채권상승=리스크오프, 금리 상승=채권하락=리스크온 해석]</td>
</tr>
<tr>
<td>**GLD** (금)</td>
<td><span color="green/red">{chg}%</span></td>
<td>[안전자산 수요 해석]</td>
</tr>
<tr>
<td>**HYG** (하이일드 채권)</td>
<td><span color="green/red">{chg}%</span></td>
<td>[신용 스프레드 해석. HYG 하락=스프레드 확대=리스크오프]</td>
</tr>
</table>
::: callout {icon="⚡" color="orange_bg"}
	**리스크 판단**: [risk_environment assessment 기반 분석]
:::
---
"""


INTELLIGENCE_SECTION_TEMPLATE = r"""# 0.5 시장 인텔리전스 대시보드 {{{{color="blue"}}}}
::: callout {{{{icon="🧠" color="blue_bg"}}}}
	**종합 시장 점수**: {{score}} ({{signal}}) — {{interpretation}}
:::
__DATA_QUALITY_CALLOUT__
## 5-Layer 분석 결과
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**Layer**</td>
<td>**점수**</td>
<td>**시그널**</td>
<td>**신뢰도**</td>
<td>**신선도**</td>
<td>**핵심 판단**</td>
</tr>
{{layer_rows}}
</table>
## Layer별 핵심 지표
{{layer_details}}
---
"""


def _build_data_quality_callout(intelligence: dict) -> str:
    """data_quality 딕셔너리에서 Notion Enhanced Markdown callout 문자열 생성."""
    dq = intelligence.get('data_quality', {})
    if not dq:
        return ""

    completeness = dq.get('layer_completeness', 1.0)
    freshness = dq.get('avg_freshness', 1.0)
    missing = dq.get('layers_missing', [])

    if completeness >= 1.0 and freshness >= 0.8:
        return (
            '::: callout {{{{icon="✅" color="green_bg"}}}}\n'
            f'\t**데이터 품질**: 5/5 레이어 완전, 평균 신선도 {freshness:.0%}\n'
            ':::\n'
        )

    parts = []
    if completeness < 1.0:
        n = len(dq.get('layers_contributing', []))
        parts.append(f"{n}/5 레이어만 분석에 기여")
    if freshness < 0.8:
        parts.append(f"평균 신선도 {freshness:.0%}")
    if missing:
        layer_kr = {
            'macro_regime': '매크로', 'market_structure': '시장구조',
            'sector_rotation': '섹터', 'enhanced_technicals': '기술적',
            'sentiment': '심리',
        }
        names = [layer_kr.get(m, m) for m in missing]
        parts.append(f"누락: {', '.join(names)}")

    return (
        '::: callout {{{{icon="⚠️" color="orange_bg"}}}}\n'
        f'\t**데이터 품질 주의**: {"; ".join(parts)}\n'
        ':::\n'
    )


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
        freshness = data.get('avg_freshness', 1.0)
        lines.append(f"- 점수: {score:+.1f} ({signal}), 신뢰도: {conf:.0%}, 신선도: {freshness:.0%}")
        lines.append(f"- 판단: {interp}")

    # 데이터 품질 요약
    dq = intelligence.get('data_quality', {})
    if dq:
        lines.append(f"\n### 데이터 품질 요약")
        contributing = len(dq.get('layers_contributing', []))
        lines.append(f"- 레이어 완전성: {contributing}/5")
        lines.append(f"- 평균 신선도: {dq.get('avg_freshness', 1.0):.0%}")

        missing = dq.get('layers_missing', [])
        if missing:
            names = [layer_names_kr.get(m, m) for m in missing]
            lines.append(f"- ⚠ 누락 레이어: {', '.join(names)}")

        stale = {k: v for k, v in dq.get('per_layer_freshness', {}).items() if v < 0.8}
        if stale:
            for k, v in stale.items():
                lines.append(f"- ⚠ {layer_names_kr.get(k, k)} 신선도: {v:.0%}")

    return "\n".join(lines)


def _build_trend_data_block(trend_data: dict) -> str:
    """TrendReader.analyze_trends() 결과를 프롬프트에 포함할 텍스트 블록으로 구성합니다.

    Args:
        trend_data: TrendReader.analyze_trends()가 반환한 딕셔너리

    Returns:
        프롬프트에 삽입할 트렌드 분석 텍스트. 데이터가 비어있으면 빈 문자열.
    """
    if not trend_data:
        return ""

    period = trend_data.get('period', {})
    if not period.get('start') or period.get('days', 0) == 0:
        return ""

    lines = ["\n## 멀티데이 트렌드 분석"]
    lines.append(
        f"- **분석 기간**: {period['start']} ~ {period['end']} ({period['days']}일간)"
    )

    # F&G 추세
    fg = trend_data.get('fear_greed_trend', {})
    if fg.get('values'):
        fg_dir_kr = {'improving': '개선', 'worsening': '악화', 'stable': '유지'}
        direction = fg_dir_kr.get(fg.get('direction', 'stable'), fg.get('direction', ''))
        vals = [f"{v['date']}: {v['value']}({v.get('classification', '')})" for v in fg['values']]
        lines.append(f"- **F&G 추세**: {direction} (변화: {fg.get('change', 0):+.1f})")
        lines.append(f"  - 값: {', '.join(vals)}")

    # 레짐 전환
    regime = trend_data.get('regime_summary', {})
    if regime.get('transitions_count', 0) > 0:
        lines.append(f"- **레짐 전환**: {regime['transitions_count']}건")
        for t in regime.get('notable_transitions', [])[:5]:
            lines.append(f"  - {t}")

    # 주요 종목 가격/RSI 변화
    symbol_trends = trend_data.get('symbol_trends', {})
    if symbol_trends:
        big_movers = []
        for sym, st in symbol_trends.items():
            pct = st.get('price_change_pct', 0)
            if abs(pct) > 2:
                rsi_vals = st.get('rsi_values', [])
                rsi_str = ""
                if rsi_vals:
                    rsi_str = f", RSI {rsi_vals[0].get('rsi', '?')}→{rsi_vals[-1].get('rsi', '?')}"
                big_movers.append(f"{sym}: {pct:+.1f}%{rsi_str}")
        if big_movers:
            lines.append(f"- **주요 종목 변동**: {', '.join(big_movers[:5])}")

    # Intelligence 점수 추세
    intel = trend_data.get('intelligence_trend', {})
    if intel.get('scores'):
        intel_dir_kr = {'rising': '상승', 'falling': '하락', 'stable': '유지'}
        direction = intel_dir_kr.get(intel.get('direction', 'stable'), intel.get('direction', ''))
        first_s = intel['scores'][0]
        last_s = intel['scores'][-1]
        lines.append(
            f"- **Intelligence 추세**: {first_s['score']:.1f} → {last_s['score']:.1f} "
            f"({direction}, 현재 {last_s.get('signal', 'N/A')})"
        )

    # 요약 텍스트
    summary = trend_data.get('summary_text', '')
    if summary:
        lines.append(f"\n**요약**: {summary}")

    return "\n".join(lines)


def _build_scorecard_data_block(scorecard: dict) -> str:
    """SignalTracker.generate_scorecard() 결과를 프롬프트에 포함할 텍스트 블록으로 구성합니다.

    data_coverage.sufficient가 False이면 간단한 '데이터 축적 중' 메시지를 반환합니다.

    Args:
        scorecard: SignalTracker.generate_scorecard()가 반환한 딕셔너리

    Returns:
        프롬프트에 삽입할 성적표 텍스트. 데이터가 비어있으면 빈 문자열.
    """
    if not scorecard:
        return ""

    coverage = scorecard.get('data_coverage', {})
    total = coverage.get('total_signals', 0)
    with_outcomes = coverage.get('with_outcomes', 0)

    if total == 0:
        return ""

    # 데이터 부족 시 간단 메시지
    if not coverage.get('sufficient', False):
        return (
            f"\n## 시그널 성적표\n"
            f"- 데이터 축적 중 ({with_outcomes}/최소10건)"
        )

    # 충분한 데이터 — 상세 성적표
    lines = ["\n## 시그널 성적표"]
    lines.append(
        f"- **데이터 커버리지**: {with_outcomes}/{total}건 채점 완료 "
        f"({coverage.get('coverage_pct', 0):.0f}%)"
    )

    overall = scorecard.get('overall_accuracy_pct')
    if overall is not None:
        lines.append(f"- **전체 적중률**: {overall:.1f}%")

    # F&G 구간별
    by_fg = scorecard.get('by_fear_greed_zone', {})
    fg_parts = []
    for zone, stats in by_fg.items():
        if stats.get('total', 0) > 0 and stats.get('accuracy_pct') is not None:
            fg_parts.append(f"{zone}: {stats['accuracy_pct']:.0f}%({stats['total']}건)")
    if fg_parts:
        lines.append(f"- **F&G 구간별 적중률**: {', '.join(fg_parts)}")

    # 시그널별
    by_signal = scorecard.get('by_signal_type', {})
    sig_parts = []
    for sig, stats in by_signal.items():
        if stats.get('total', 0) > 0 and stats.get('accuracy_pct') is not None:
            sig_parts.append(f"{sig}: {stats['accuracy_pct']:.0f}%({stats['total']}건)")
    if sig_parts:
        lines.append(f"- **시그널별 적중률**: {', '.join(sig_parts)}")

    # 종목별 상위/하위
    by_symbol = scorecard.get('by_symbol', {})
    if by_symbol:
        sorted_symbols = sorted(
            [(s, st) for s, st in by_symbol.items()
             if st.get('total', 0) >= 3 and st.get('accuracy_pct') is not None],
            key=lambda x: x[1]['accuracy_pct'],
            reverse=True,
        )
        if sorted_symbols:
            top = sorted_symbols[:3]
            bottom = sorted_symbols[-3:] if len(sorted_symbols) > 3 else []
            top_str = ', '.join(f"{s}({st['accuracy_pct']:.0f}%)" for s, st in top)
            lines.append(f"- **적중률 상위**: {top_str}")
            if bottom:
                bottom_str = ', '.join(f"{s}({st['accuracy_pct']:.0f}%)" for s, st in bottom)
                lines.append(f"- **적중률 하위**: {bottom_str}")

    # best/worst conditions
    best = scorecard.get('best_conditions')
    worst = scorecard.get('worst_conditions')
    if best:
        lines.append(f"- **최적 조건**: {best}")
    if worst:
        lines.append(f"- **최악 조건**: {worst}")

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

    def _fmt(label: str, info: dict, extra: str = '') -> str:
        """이벤트 항목 포맷팅 (7일 이내 ⚠️ 표시)"""
        nd = info.get('next_date')
        du = info.get('days_until')
        if not nd:
            return ''
        warn = ' ⚠️' if du is not None and du <= 7 else ''
        return f"- {label}: {nd} ({du}일 후){warn}{extra}"

    # --- 매크로 경제 지표 ---
    economic = events_data.get('economic', {})
    if economic:
        econ_labels = {
            'nfp': 'NFP (고용)',
            'cpi': 'CPI',
            'ppi': 'PPI',
            'pce': 'PCE',
            'gdp': 'GDP',
            'ism_manufacturing': 'ISM 제조업',
            'ism_services': 'ISM 서비스업',
            'jackson_hole': '잭슨홀',
        }
        econ_lines = []
        for key, label in econ_labels.items():
            info = economic.get(key, {})
            line = _fmt(label, info)
            if line:
                econ_lines.append(line)
        if econ_lines:
            lines.append("\n### 매크로 경제 지표")
            lines.extend(econ_lines)

    # --- 중앙은행 ---
    fomc = events_data.get('fomc', {})
    fomc_minutes = events_data.get('fomc_minutes', {})
    if fomc.get('next_date') or fomc_minutes.get('next_date'):
        lines.append("\n### 중앙은행")
        next_fomc = fomc.get('next_date')
        fomc_days = fomc.get('days_until')
        if next_fomc:
            warn = ' ⚠️' if fomc_days is not None and fomc_days <= 7 else ''
            lines.append(f"- 다음 FOMC: {next_fomc} ({fomc_days}일 후){warn}")
            remaining = fomc.get('remaining_2026', [])
            if len(remaining) > 1:
                lines.append(f"- 2026년 남은 FOMC: {len(remaining) - 1}회 ({', '.join(remaining[1:])})")
        fm_date = fomc_minutes.get('next_date')
        if fm_date:
            lines.append(f"- FOMC 의사록: {fm_date}")

    # --- 옵션/파생 ---
    options = events_data.get('options', {})
    vix_expiry = events_data.get('vix_expiry', {})
    if options.get('monthly_expiry', {}).get('next_date') or vix_expiry.get('next_date'):
        lines.append("\n### 옵션/파생")
        me = options.get('monthly_expiry', {})
        if me.get('next_date'):
            quad_tag = ' [Quad Witching]' if options.get('is_quad_witching') else ''
            line = _fmt('옵션 만기', me, quad_tag)
            if line:
                lines.append(line)
        if vix_expiry.get('next_date'):
            line = _fmt('VIX 만기', vix_expiry)
            if line:
                lines.append(line)

    # --- 실적발표 (가까운 순) ---
    earnings = events_data.get('earnings', {})
    if earnings:
        lines.append("\n### 실적발표 (가까운 순)")
        for symbol, info in sorted(earnings.items(), key=lambda x: x[1].get('days_until', 999)):
            eps_str = f", 컨센서스 EPS ${info['estimate_eps']:.2f}" if info.get('estimate_eps') is not None else ""
            rev_str = f", 예상 매출 ${info['estimate_revenue']:,.0f}" if info.get('estimate_revenue') is not None else ""
            du = info.get('days_until')
            warn = ' ⚠️' if du is not None and du <= 7 else ''
            lines.append(f"- {symbol}: {info['date']} ({du}일 후){warn}{eps_str}{rev_str}")

    # --- 시장 구조 ---
    market_structure = events_data.get('market_structure', {})
    holidays = events_data.get('holidays', {})
    ms_lines = []
    sp500 = market_structure.get('sp500_rebalance', {})
    if sp500.get('next_date'):
        line = _fmt('S&P 500 리밸런싱', sp500)
        if line:
            ms_lines.append(line)
    russell = market_structure.get('russell_rebalance', {})
    if russell.get('next_date'):
        line = _fmt('Russell 리밸런싱', russell)
        if line:
            ms_lines.append(line)
    nh = holidays.get('next_holiday', {})
    if nh.get('date'):
        nh_info = {'next_date': nh['date'], 'days_until': nh['days_until']}
        line = _fmt(f"다음 휴장일 ({nh['name']})", nh_info)
        if line:
            ms_lines.append(line)
    if ms_lines:
        lines.append("\n### 시장 구조")
        lines.extend(ms_lines)

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

    # JSON 덤프 시 news/fear_greed_index/macro/intelligence/trend/scorecard는 별도 블록으로 추출하므로 중복 제거 (프롬프트 경량화)
    json_for_prompt = {k: v for k, v in data.items() if k not in ('news', 'fear_greed_index', 'macro', 'intelligence', 'trend', 'scorecard')}
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

    # 트렌드 데이터 블록
    trend_data_block = ""
    if 'trend' in data and data['trend']:
        trend_data_block = _build_trend_data_block(data['trend'])

    # 성적표 데이터 블록
    scorecard_data_block = ""
    if 'scorecard' in data and data['scorecard']:
        scorecard_data_block = _build_scorecard_data_block(data['scorecard'])

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
        dq_callout = _build_data_quality_callout(data['intelligence'])
        intel_template = INTELLIGENCE_SECTION_TEMPLATE.replace(
            '__DATA_QUALITY_CALLOUT__', dq_callout
        )
        format_spec = format_spec.replace(
            "---\n# 1.",
            "---\n" + intel_template + "# 1."
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
{trend_data_block}
{scorecard_data_block}
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
