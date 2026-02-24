"""
Parallel Prompt Builder for Market Analysis

시장 분석 Notion 페이지를 병렬로 생성하기 위한 워커별 프롬프트 빌더입니다.
3개 워커(A, B, C)가 각각 독립적인 섹션을 생성하고,
Notion Writer가 최종 페이지를 조립하여 생성합니다.

Worker A: 섹션 1 (시장 요약), 2 (종목별 분석) - WebSearch 필요
Worker B: 섹션 3 (Top 3), 4 (공포/탐욕), 5 (뉴스) - WebSearch + Read 필요
Worker C: 섹션 6-10 (전략/성과/세션/전망/리스크) - 도구 불필요
Notion Writer: 조립된 콘텐츠로 Notion 페이지 생성

Usage:
    from trading_bot.parallel_prompt_builder import (
        build_worker_a_prompt,
        build_worker_b_prompt,
        build_worker_c_prompt,
        build_notion_writer_prompt,
        precompute_session_metrics,
        assemble_sections,
    )
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from trading_bot.market_analysis_prompt import (
    NOTION_FORMAT_TEMPLATE,
    _load_session_reports,
    get_notion_page_id,
)
from trading_bot.performance_calculator import PerformanceCalculator

logger = logging.getLogger(__name__)

# 워커별 모델 ID 매핑
WORKER_MODELS = {
    'Worker-A': 'claude-sonnet-4-6',        # WebSearch required
    'Worker-B': 'claude-sonnet-4-6',        # WebSearch + Read required
    'Worker-C': 'claude-haiku-4-5-20251001',  # No tools, data analysis only
    'Notion-Writer': 'claude-haiku-4-5-20251001',  # Simple page creation
}

# 페이지 하단 푸터 템플릿
FOOTER_TEMPLATE = """::: callout {{{{icon="📝" color="gray_bg"}}}}
\t**분석 생성**: {date}  \\|  **데이터 수집**: {date} KST  \\|  **병렬 생성**: Worker A + B + C
\t**주의사항**: 본 분석은 자동 수집된 데이터와 기술적 지표를 기반으로 생성된 참고 자료입니다. 실제 투자 결정은 개인의 판단과 책임 하에 이루어져야 합니다.
:::"""

# Notion Enhanced Markdown 포맷 규칙 (각 워커에 포함)
_FORMAT_RULES = r"""--- FORMAT RULES (MANDATORY) ---
1. ALL section headers (# 1., # 2., ...) MUST have {{color="blue"}}
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
12. Fear & Greed history rows: green_bg for greed periods, red_bg for fear periods, yellow_bg for neutral
13. Tables with stock symbols should have header-column="true"
--- END FORMAT RULES ---"""


def _calculate_var_95(snapshots: List[Dict]) -> Optional[float]:
    """
    95% VaR를 히스토리컬 시뮬레이션으로 계산합니다.

    Args:
        snapshots: 포트폴리오 스냅샷 리스트 (total_value 키 포함)

    Returns:
        95% VaR 값 (퍼센트), 데이터 부족 시 None
    """
    if len(snapshots) < 3:
        return None

    values = [s.get('total_value', s.get('equity', 0)) for s in snapshots]
    returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            returns.append((values[i] - values[i - 1]) / values[i - 1])

    if len(returns) < 2:
        return None

    sorted_returns = sorted(returns)
    index = int(len(sorted_returns) * 0.05)
    var_95 = sorted_returns[index] * 100
    return round(var_95, 4)


def _calculate_strategy_pnl_breakdown(trades: List[Dict]) -> List[Dict]:
    """
    전략별 PnL 분석을 계산합니다.

    Args:
        trades: 거래 리스트 (symbol, type, pnl 키 포함)

    Returns:
        전략(심볼)별 PnL 분석 딕셔너리 리스트
    """
    if not trades:
        return []

    sell_trades = [t for t in trades if t.get('type') == 'SELL']
    if not sell_trades:
        return []

    # 심볼별 그룹핑
    symbol_pnl: Dict[str, List[float]] = {}
    for t in sell_trades:
        symbol = t.get('symbol', 'N/A')
        pnl = t.get('pnl', 0)
        if symbol not in symbol_pnl:
            symbol_pnl[symbol] = []
        symbol_pnl[symbol].append(pnl)

    breakdown = []
    for symbol, pnls in sorted(symbol_pnl.items()):
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        breakdown.append({
            'symbol': symbol,
            'total_pnl': round(total_pnl, 2),
            'trade_count': len(pnls),
            'win_count': len(wins),
            'loss_count': len(losses),
            'avg_pnl': round(total_pnl / len(pnls), 2) if pnls else 0,
            'max_win': round(max(wins), 2) if wins else 0,
            'max_loss': round(min(losses), 2) if losses else 0,
        })

    return breakdown


def _format_trade_log(trades: List[Dict], limit: int = 50) -> List[Dict]:
    """
    거래 로그를 통합하여 최근 N건을 반환합니다.

    Args:
        trades: 전체 거래 리스트
        limit: 반환할 최대 건수

    Returns:
        최근 거래 딕셔너리 리스트
    """
    if not trades:
        return []

    formatted = []
    for t in trades:
        formatted.append({
            'timestamp': t.get('timestamp', 'N/A'),
            'symbol': t.get('symbol', 'N/A'),
            'type': t.get('type', 'N/A'),
            'price': t.get('price', 0),
            'size': t.get('size', 0),
            'pnl': t.get('pnl'),
            'commission': t.get('commission', 0),
        })

    # 타임스탬프 기준 정렬 (최신순)
    formatted.sort(key=lambda x: x['timestamp'], reverse=True)
    return formatted[:limit]


def precompute_session_metrics(session_reports_dir: str) -> Dict[str, Any]:
    """
    세션 리포트 디렉토리에서 고급 메트릭을 사전 계산합니다.

    _load_session_reports()로 세션 데이터를 로드하고,
    VaR(95%), 전략별 PnL, 통합 거래 로그 등을 계산합니다.

    Args:
        session_reports_dir: 세션 리포트 JSON 파일들이 있는 디렉토리 경로

    Returns:
        사전 계산된 메트릭 딕셔너리:
        - sessions: 세션 요약 리스트
        - has_sessions: 세션 데이터 존재 여부
        - var_95: 전체 VaR(95%) 값
        - strategy_pnl_breakdown: 전략별 PnL 분석
        - trade_log: 통합 거래 로그 (최근 50건)
        - session_details: 세션별 상세 메트릭
    """
    sessions = _load_session_reports(session_reports_dir)

    if not sessions:
        return {
            'sessions': [],
            'has_sessions': False,
            'var_95': None,
            'strategy_pnl_breakdown': [],
            'trade_log': [],
            'session_details': [],
        }

    # 리포트 파일 직접 읽기 (스냅샷, 거래 데이터)
    import glob as glob_module
    pattern = os.path.join(session_reports_dir, "*_report.json")
    report_files = sorted(glob_module.glob(pattern))

    all_trades: List[Dict] = []
    all_snapshots: List[Dict] = []
    session_details: List[Dict] = []
    calc = PerformanceCalculator()

    for fpath in report_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                report = json.load(f)

            summary = report.get("summary", {})
            trades = report.get("trades", [])
            snapshots = report.get("snapshots", [])

            all_trades.extend(trades)
            all_snapshots.extend(snapshots)

            # 세션별 상세 메트릭
            profit_factor = calc.calculate_profit_factor(trades)
            var_95 = _calculate_var_95(snapshots)

            session_details.append({
                'session_id': report.get('session_id', 'N/A'),
                'display_name': summary.get('display_name', summary.get('strategy_name', 'N/A')),
                'strategy_name': summary.get('strategy_name', 'N/A'),
                'total_return': summary.get('total_return', 0),
                'sharpe_ratio': summary.get('sharpe_ratio'),
                'max_drawdown': summary.get('max_drawdown', 0),
                'win_rate': summary.get('win_rate'),
                'profit_factor': profit_factor,
                'var_95': var_95,
                'total_trades': len(trades),
                'initial_capital': summary.get('initial_capital', 0),
                'final_capital': summary.get('final_capital', 0),
            })
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"세션 리포트 상세 로드 실패: {fpath} - {e}")

    # 전체 메트릭 계산
    overall_var_95 = _calculate_var_95(all_snapshots)
    strategy_pnl = _calculate_strategy_pnl_breakdown(all_trades)
    trade_log = _format_trade_log(all_trades)

    return {
        'sessions': sessions,
        'has_sessions': True,
        'var_95': overall_var_95,
        'strategy_pnl_breakdown': strategy_pnl,
        'trade_log': trade_log,
        'session_details': session_details,
    }


def build_worker_a_prompt(market_data: Dict, today: str) -> str:
    """
    Worker A 프롬프트를 생성합니다.
    담당 섹션: 1 (시장 전체 요약), 2 (종목별 분석)

    Args:
        market_data: 시장 분석 JSON 데이터 (market_summary, stocks 포함)
        today: 분석 날짜 (YYYY-MM-DD)

    Returns:
        Worker A용 프롬프트 문자열
    """
    # stocks 데이터만 추출 (뉴스, fear_greed 제외)
    data_for_worker = {
        'market_summary': market_data.get('market_summary', {}),
        'stocks': market_data.get('stocks', {}),
    }
    json_str = json.dumps(data_for_worker, ensure_ascii=False, indent=2)

    symbols = list(market_data.get('stocks', {}).keys())
    symbols_str = ", ".join(symbols)

    prompt = f"""당신은 시장 분석 워커 A입니다.
아래 JSON 데이터를 분석하여 **섹션 1과 섹션 2만** Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 섹션 1과 2만 출력합니다.

## WebSearch 활용 지시
- WebSearch 도구를 사용하여 각 종목의 최신 뉴스와 시장 동향을 검색하세요.
- 특히 극단적 과매도/과매수, 급등/급락 종목의 뉴스를 심층 검색하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.

## 대상 종목
{symbols_str} ({len(symbols)}개)

{_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 1. 시장 전체 요약 {{{{color="blue"}}}}
::: callout {{{{icon="📅" color="gray_bg"}}}}
\t**분석 일자**: {today}  \\|  **대상 종목**: {len(symbols)}개 ({symbols_str})
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
<td>**{{{{value}}}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>강세 종목 수</td>
<td>**{{{{value}}}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>약세 종목 수</td>
<td>**{{{{value}}}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>횡보 종목 수</td>
<td>**{{{{value}}}}**</td>
<td>[interpretation]</td>
</tr>
<tr>
<td>공포탐욕 지수</td>
<td>**{{{{value}}}}**</td>
<td>[interpretation]</td>
</tr>
</table>

## 전반적인 시장 분위기
::: callout {{{{icon="⚠️" color="red_bg"}}}}
(Use red_bg for bearish, green_bg for bullish, yellow_bg for neutral. Choose appropriate emoji.)
\t**[강세/약세/중립] ([Bullish/Bearish/Neutral])** — [explanation with data]
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
<td>**{{{{SYMBOL}}}}**</td>
<td>{{{{price}}}}</td>
<td><span color="red">{{{{negative%}}}}</span> or <span color="green">{{{{positive%}}}}</span></td>
<td><span color="red">{{{{negative%}}}}</span> or <span color="green">{{{{positive%}}}}</span></td>
<td>{{{{rsi}}}} ({{{{label}}}})</td>
<td><span color="red">Bearish</span> or <span color="green">Bullish</span></td>
<td>{{{{REGIME}}}} ({{{{confidence}}}}%)</td>
<td>{{{{signal_notes}}}}</td>
</tr>
[... repeat for all stocks]
</table>
---

--- END EXACT OUTPUT STRUCTURE ---

JSON 데이터:
```json
{json_str}
```"""

    logger.info(f"Worker A 프롬프트 생성 완료 (길이: {len(prompt)}자, 종목: {len(symbols)}개)")
    return prompt


def build_worker_b_prompt(
    market_data: Dict,
    news_data: Dict,
    fear_greed_data: Dict,
    today: str,
) -> str:
    """
    Worker B 프롬프트를 생성합니다.
    담당 섹션: 3 (주목할 종목 Top 3), 4 (공포/탐욕 지수), 5 (뉴스 분석)

    Args:
        market_data: 시장 분석 JSON 데이터 (stocks 포함)
        news_data: 뉴스 데이터 딕셔너리
        fear_greed_data: Fear & Greed 지수 데이터 딕셔너리
        today: 분석 날짜 (YYYY-MM-DD)

    Returns:
        Worker B용 프롬프트 문자열
    """
    # 종목 데이터
    stocks_json = json.dumps(market_data.get('stocks', {}), ensure_ascii=False, indent=2)

    # 뉴스 블록 구성
    news_block = ""
    if news_data:
        news_lines = []
        market_news = news_data.get('market_news', [])
        if market_news:
            news_lines.append("### 시장 전체 뉴스")
            for item in market_news:
                news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        stock_news = news_data.get('stock_news', {})
        if stock_news:
            news_lines.append("\n### 종목별 뉴스")
            for symbol, items in stock_news.items():
                news_lines.append(f"\n**{symbol}**:")
                for item in items[:3]:
                    news_lines.append(f"- {item['title']} ({item.get('source', 'N/A')})")

        news_block = "\n## 수집된 뉴스 데이터\n" + "\n".join(news_lines)

    # Fear & Greed 블록 구성
    fg_block = ""
    if fear_greed_data:
        current = fear_greed_data.get('current', {})
        fg_lines = []
        fg_lines.append("### 현재 Fear & Greed Index")
        fg_lines.append(f"- **값**: {current.get('value', 'N/A')}")
        fg_lines.append(f"- **분류**: {current.get('classification', 'N/A')}")
        fg_lines.append(f"- **시각**: {current.get('timestamp', 'N/A')}")

        history = fear_greed_data.get('history', [])
        if history:
            fg_lines.append(f"\n### 최근 {len(history)}일 히스토리")
            for item in history[:7]:
                fg_lines.append(f"- {item['date']}: {item['value']} ({item['classification']})")
            if len(history) > 7:
                fg_lines.append(f"- ... 외 {len(history) - 7}일")

        chart_path = fear_greed_data.get('chart_path')
        if chart_path:
            fg_lines.append(f"\n### 차트")
            fg_lines.append(f"- 차트 파일 경로: `{chart_path}`")
            fg_lines.append(f"- Read 도구로 이 차트 이미지를 읽어서 시각적 분석에 반영하세요.")

        fg_block = "\n## 공포/탐욕 지수 (Fear & Greed Index)\n" + "\n".join(fg_lines)

    prompt = f"""당신은 시장 분석 워커 B입니다.
아래 데이터를 분석하여 **섹션 3, 4, 5만** Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 섹션 3, 4, 5만 출력합니다.

## WebSearch + Read 도구 활용 지시
- WebSearch: 주목할 종목 Top 3 선정 시 최신 뉴스를 검색하여 분석에 반영하세요.
- Read: Fear & Greed 차트 이미지 파일을 읽어 시각적 분석에 반영하세요.
- 검색 결과에서 발견한 주요 뉴스는 분석에 반영하되, 출처를 명시하세요.
{news_block}
{fg_block}

{_FORMAT_RULES}

--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 3. 주목할 종목 Top 3 {{{{color="blue"}}}}
## 🥇 1위: {{{{SYMBOL}}}} ({{{{Company}}}}) — {{{{action recommendation}}}}
::: callout {{{{icon="📌" color="yellow_bg"}}}}
\t**현재가**: \\${{{{price}}}}  \\|  **20일 변화**: {{{{change}}}}  \\|  **RSI**: {{{{rsi}}}}  \\|  **레짐**: {{{{regime}}}}
:::
**선정 이유 및 기술적 근거**:
- [bullet points with technical analysis]
- **지지선**: \\${{{{support1}}}} / \\${{{{support2}}}}

**뉴스 근거**: [news-based analysis with sources]

> **의견**: [emoji] **[recommendation]** — [detailed reasoning with price targets]
---
(Repeat same structure for 🥈 2위 and 🥉 3위)
---
# 4. 공포/탐욕 지수 분석 {{{{color="blue"}}}}
## 현재 Fear & Greed Index
::: callout {{{{icon="😰" color="red_bg"}}}}
(Choose emoji and color based on value: 😰/red_bg for fear, 😊/green_bg for greed, 😐/yellow_bg for neutral)
\t**현재값: {{{{value}}}} ({{{{classification}}}})** — [interpretation]
\t측정 시각: {{{{timestamp}}}}
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
<td>{{{{period}}}}</td>
<td>{{{{range}}}}</td>
<td>{{{{classification}}}}</td>
<td>{{{{notes}}}}</td>
</tr>
[... periods]
</table>
## 최근 추세 변화 해석
[numbered analysis points]
## 기술적 지표와의 상관관계
[bullet points correlating F&G with RSI and other indicators]
::: callout {{{{icon="💡" color="blue_bg"}}}}
\t**역발상 투자 관점**: [contrarian analysis]
:::
---
# 5. 뉴스 & 이벤트 분석 {{{{color="blue"}}}}
## 시장 전체 주요 뉴스
<details>
<summary>📰 거시경제 & 시장 이벤트</summary>
\t[numbered news items with sources]
</details>
## 종목별 핵심 뉴스 분석
### [Theme/Category] ([affected symbols])
::: callout {{{{icon="🤖" color="orange_bg"}}}}
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
<td>{{{{symbol}}}}</td>
<td>{{{{technical}}}}</td>
<td>{{{{news}}}}</td>
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

    logger.info(f"Worker B 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


def build_worker_c_prompt(
    market_data: Dict,
    session_metrics: Dict,
    today: str,
    has_sessions: bool,
) -> str:
    """
    Worker C 프롬프트를 생성합니다.
    담당 섹션: 6 (전략 파라미터), 7 (성과 대시보드), 8 (세션 분석),
               9 (전방 전망), 10 (리스크)
    세션 없으면: 6, 7 (전방 전망), 8 (리스크) - 7, 8번 섹션 스킵

    Args:
        market_data: 시장 분석 JSON 데이터 (stocks 포함)
        session_metrics: precompute_session_metrics()가 반환한 메트릭
        today: 분석 날짜 (YYYY-MM-DD)
        has_sessions: 세션 데이터 존재 여부

    Returns:
        Worker C용 프롬프트 문자열
    """
    # 종목 데이터 (전략 파라미터/전망용)
    stocks_json = json.dumps(market_data.get('stocks', {}), ensure_ascii=False, indent=2)

    # 세션 메트릭 JSON
    metrics_json = ""
    if has_sessions:
        metrics_for_prompt = {
            'session_details': session_metrics.get('session_details', []),
            'var_95': session_metrics.get('var_95'),
            'strategy_pnl_breakdown': session_metrics.get('strategy_pnl_breakdown', []),
            'trade_log': session_metrics.get('trade_log', [])[:20],  # 프롬프트 경량화
        }
        metrics_json = json.dumps(metrics_for_prompt, ensure_ascii=False, indent=2)

    # 전방 전망용 데이터 (지지선, RSI 임계치 근접 종목)
    forward_data = _extract_forward_look_data(market_data)
    forward_json = json.dumps(forward_data, ensure_ascii=False, indent=2)

    if has_sessions:
        # 세션 있을 때: 섹션 6, 7, 8, 9, 10
        section_structure = _build_worker_c_sections_with_sessions()
        session_data_block = f"""
## 세션 메트릭 데이터
```json
{metrics_json}
```"""
    else:
        # 세션 없을 때: 섹션 6, 7(전방전망), 8(리스크)
        section_structure = _build_worker_c_sections_without_sessions()
        session_data_block = ""

    prompt = f"""당신은 시장 분석 워커 C입니다.
아래 데이터를 분석하여 아래 지정된 섹션만 Notion Enhanced Markdown으로 출력하세요.

**중요**: TOC, 푸터, 다른 섹션은 절대 출력하지 마세요. 지정된 섹션만 출력합니다.
**중요**: 도구(WebSearch, Read 등)는 사용하지 마세요. 주어진 데이터만으로 분석하세요.

{_FORMAT_RULES}

{section_structure}
{session_data_block}

## 전방 전망 데이터 (지지선/RSI 임계치 근접)
```json
{forward_json}
```

종목 데이터:
```json
{stocks_json}
```"""

    logger.info(f"Worker C 프롬프트 생성 완료 (길이: {len(prompt)}자, 세션: {has_sessions})")
    return prompt


def _extract_forward_look_data(market_data: Dict) -> Dict[str, Any]:
    """
    전방 전망 섹션에 필요한 데이터를 추출합니다.

    지지선/저항선, RSI 임계치 근접 종목(±3 이내) 등을 추출합니다.

    Args:
        market_data: 시장 분석 JSON 데이터

    Returns:
        전방 전망용 데이터 딕셔너리
    """
    stocks = market_data.get('stocks', {})
    support_resistance = {}
    rsi_pending_signals = []

    for symbol, data in stocks.items():
        # 지지선 추출
        patterns = data.get('patterns', {})
        support_levels = patterns.get('support_levels', [])
        if support_levels:
            support_resistance[symbol] = {
                'support_levels': support_levels,
                'current_price': data.get('price', {}).get('last', 0),
            }

        # RSI 임계치 근접 종목 (±3 이내)
        indicators = data.get('indicators', {})
        rsi_val = indicators.get('rsi', {}).get('value')
        if rsi_val is not None:
            # signal_diagnosis에서 최적 범위 추출
            diagnosis = data.get('signal_diagnosis', {})
            optimal = diagnosis.get('optimal_rsi_range', {})
            oversold = optimal.get('oversold', 30)
            overbought = optimal.get('overbought', 70)

            if abs(rsi_val - oversold) <= 3:
                rsi_pending_signals.append({
                    'symbol': symbol,
                    'rsi': rsi_val,
                    'threshold': oversold,
                    'type': 'near_oversold',
                    'distance': round(rsi_val - oversold, 1),
                })
            elif abs(rsi_val - overbought) <= 3:
                rsi_pending_signals.append({
                    'symbol': symbol,
                    'rsi': rsi_val,
                    'threshold': overbought,
                    'type': 'near_overbought',
                    'distance': round(rsi_val - overbought, 1),
                })

    return {
        'support_resistance': support_resistance,
        'rsi_pending_signals': rsi_pending_signals,
    }


def _build_worker_c_sections_with_sessions() -> str:
    """세션이 있을 때의 Worker C 출력 구조를 반환합니다 (섹션 6-10)."""
    return r"""--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 6. 전략 파라미터 제안 {color="blue"}
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
<td>{symbol}</td>
<td>**{oversold}**</td>
<td>{overbought}</td>
<td>{reason}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {icon="📊" color="yellow_bg"}
	**[MACD recommendation]**
	[details]
:::
## 추천 전략
[numbered strategy recommendations]
---
# 7. 성과 대시보드 {color="blue"}
## 전략별 성과 테이블
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**세션**</td>
<td>**수익률**</td>
<td>**Sharpe**</td>
<td>**Profit Factor**</td>
<td>**Max DD**</td>
<td>**VaR(95%)**</td>
<td>**Win Rate**</td>
</tr>
[... rows from session_details data, use color="orange_bg" for negative returns]
</table>
## PnL 기여도 분석
[analysis based on strategy_pnl_breakdown data - which symbols contributed most/least]
## 거래 로그
<details>
<summary>📋 최근 거래 내역 (최대 20건)</summary>
<table fit-page-width="true" header-row="true">
<tr color="blue_bg">
<td>**시간**</td>
<td>**종목**</td>
<td>**유형**</td>
<td>**가격**</td>
<td>**수량**</td>
<td>**PnL**</td>
</tr>
[... rows from trade_log data]
</table>
</details>
---
# 8. 트레이딩 세션 분석 {color="blue"}
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
[... rows from session_details data]
</table>
## 세션별 분석
[per-session analysis: strategy effectiveness, trades detail if any, comparison between sessions]
## 전략 효과 평가
::: callout {icon="📈" color="blue_bg"}
	[evaluation of strategy effectiveness based on session results and market conditions]
:::
---
# 9. 전방 전망 {color="blue"}
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
::: callout {icon="🔔" color="yellow_bg"}
[list stocks where RSI is within ±3 of their oversold/overbought thresholds from rsi_pending_signals]
:::
## 향후 주시 사항
[numbered points about what to watch for tomorrow/this week based on data]
---
# 10. 리스크 요인 {color="blue"}
## 시장 주요 리스크
[numbered risk items based on market data analysis]
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

--- END EXACT OUTPUT STRUCTURE ---"""


def _build_worker_c_sections_without_sessions() -> str:
    """세션이 없을 때의 Worker C 출력 구조를 반환합니다 (섹션 6, 7, 8)."""
    return r"""--- EXACT OUTPUT STRUCTURE (이 구조만 출력하세요) ---

# 6. 전략 파라미터 제안 {color="blue"}
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
<td>{symbol}</td>
<td>**{oversold}**</td>
<td>{overbought}</td>
<td>{reason}</td>
</tr>
[... all symbols]
</table>
## MACD 사용 적합성 판단
::: callout {icon="📊" color="yellow_bg"}
	**[MACD recommendation]**
	[details]
:::
## 추천 전략
[numbered strategy recommendations]
---
# 7. 전방 전망 {color="blue"}
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
::: callout {icon="🔔" color="yellow_bg"}
[list stocks where RSI is within ±3 of their oversold/overbought thresholds from rsi_pending_signals]
:::
## 향후 주시 사항
[numbered points about what to watch for tomorrow/this week based on data]
---
# 8. 리스크 요인 {color="blue"}
## 시장 주요 리스크
[numbered risk items based on market data analysis]
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

--- END EXACT OUTPUT STRUCTURE ---"""


def build_notion_writer_prompt(
    assembled_content: str,
    today: str,
    parent_page_id: str,
) -> str:
    """
    Notion Writer 프롬프트를 생성합니다.
    조립된 콘텐츠를 Notion 페이지로 생성하는 지시를 포함합니다.

    Args:
        assembled_content: assemble_sections()가 반환한 조립된 콘텐츠
        today: 분석 날짜 (YYYY-MM-DD)
        parent_page_id: Notion 상위 페이지 ID

    Returns:
        Notion Writer용 프롬프트 문자열
    """
    prompt = f"""아래 콘텐츠를 Notion 페이지로 생성하세요.

Notion MCP 도구(notion-create-pages)를 사용하여 다음 설정으로 페이지를 생성하세요:
- 상위 페이지 ID: {parent_page_id}
- 페이지 제목: "📊 시장 분석 | {today}"

**중요**:
- 아래 콘텐츠를 그대로 페이지 content로 사용하세요.
- 콘텐츠를 수정하거나 재작성하지 마세요.
- notion-create-pages 도구만 호출하면 됩니다.

--- 페이지 콘텐츠 시작 ---
{assembled_content}
--- 페이지 콘텐츠 끝 ---"""

    logger.info(f"Notion Writer 프롬프트 생성 완료 (길이: {len(prompt)}자)")
    return prompt


def assemble_sections(
    worker_a_output: str,
    worker_b_output: str,
    worker_c_output: str,
    today: str,
) -> str:
    """
    워커 출력들을 최종 페이지 콘텐츠로 조립합니다.

    TOC + Worker A + Worker B + Worker C + Footer 순서로 결합합니다.

    Args:
        worker_a_output: Worker A의 출력 (섹션 1, 2)
        worker_b_output: Worker B의 출력 (섹션 3, 4, 5)
        worker_c_output: Worker C의 출력 (섹션 6+)
        today: 분석 날짜 (YYYY-MM-DD)

    Returns:
        조립된 최종 페이지 콘텐츠
    """
    footer = FOOTER_TEMPLATE.format(date=today)

    content = f"""<table_of_contents/>
---
{worker_a_output.strip()}
{worker_b_output.strip()}
{worker_c_output.strip()}
{footer}"""

    logger.info(f"섹션 조립 완료 (총 길이: {len(content)}자)")
    return content


def validate_assembly(content: str, expected_sections: List[str]) -> bool:
    """
    조립된 콘텐츠에서 예상되는 섹션 헤더가 순서대로 존재하는지 검증합니다.

    Args:
        content: 조립된 페이지 콘텐츠
        expected_sections: 예상되는 섹션 헤더 리스트 (예: ["# 1.", "# 2.", ...])

    Returns:
        모든 섹션이 순서대로 존재하면 True
    """
    last_pos = -1
    for section in expected_sections:
        pos = content.find(section, last_pos + 1)
        if pos == -1:
            logger.warning(f"섹션 누락: '{section}'")
            return False
        if pos <= last_pos:
            logger.warning(f"섹션 순서 오류: '{section}' (pos={pos}, last={last_pos})")
            return False
        last_pos = pos

    logger.info(f"섹션 검증 통과: {len(expected_sections)}개 섹션 모두 확인")
    return True
