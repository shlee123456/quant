#!/usr/bin/env python3
"""
Pine Script Generator - 시장 분석 JSON → TradingView Pine Script v6 자동 생성

시장 분석 결과(종목별 최적 파라미터)를 읽어 TradingView에서 바로 사용할 수 있는
Pine Script v6 통합 지표를 자동 생성합니다.

LLM 부분 개입:
  - 코드 구조/수치: 템플릿 + JSON 직접 삽입 (결정론적)
  - 코멘트/전략/알림: LLM 생성 (claude CLI) → 실패 시 규칙 기반 폴백

출력 파일:
  - {날짜}_indicator.pine : 통합 패널 (RSI, ADX, Stochastic, BB %B + AI 코멘터리)

Usage:
    # 최신 JSON 사용 (LLM 코멘터리 포함)
    python scripts/generate_pine_script.py

    # 특정 날짜 지정
    python scripts/generate_pine_script.py --date 2026-02-21

    # LLM 없이 규칙 기반만
    python scripts/generate_pine_script.py --no-llm

    # Slack으로 .pine 파일 전송
    python scripts/generate_pine_script.py --slack

    # 표준 출력 (파일 저장 없이)
    python scripts/generate_pine_script.py --stdout
"""

import os
import re
import sys
import json
import shutil
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime

import pytz
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 로드
load_dotenv(PROJECT_ROOT / ".env")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MARKET_ANALYSIS_DIR = PROJECT_ROOT / "data" / "market_analysis"
PINE_OUTPUT_DIR = PROJECT_ROOT / "data" / "pine_scripts"

# LLM 설정
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_TIMEOUT = 120  # seconds

# 레짐별 기본 알림 유형 매핑
_REGIME_ALERT_MAP = {
    "VOLATILE": "bb_extreme",
    "BULLISH": "macd_cross",
    "BEARISH": "macd_cross",
    "SIDEWAYS": "rsi_extreme",
}


def find_json(date_str: str | None = None) -> Path | None:
    """시장 분석 JSON 파일을 찾습니다."""
    if not MARKET_ANALYSIS_DIR.is_dir():
        logger.warning(f"시장 분석 디렉토리 없음: {MARKET_ANALYSIS_DIR}")
        return None

    if date_str:
        candidates = sorted(MARKET_ANALYSIS_DIR.glob(f"{date_str}*.json"))
    else:
        kst = pytz.timezone("Asia/Seoul")
        today = datetime.now(kst).strftime("%Y-%m-%d")
        candidates = sorted(MARKET_ANALYSIS_DIR.glob(f"{today}*.json"))
        if not candidates:
            # 오늘 파일 없으면 가장 최신 파일
            candidates = sorted(MARKET_ANALYSIS_DIR.glob("*.json"))

    if not candidates:
        logger.info("분석 JSON 파일 없음")
        return None

    return candidates[-1]


def load_analysis(json_path: Path) -> dict:
    """JSON 파일을 로드합니다."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== LLM 코멘터리 ====================


def _extract_json(text: str) -> dict | None:
    """LLM 응답에서 JSON을 추출합니다."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Try 1: 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: Markdown 코드블록
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try 3: 첫 { ... } 탐색
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning(f"JSON 추출 실패: {text[:200]}")
    return None


def _build_llm_prompt(data: dict) -> str:
    """LLM에게 보낼 프롬프트를 구성합니다 (v2 데이터 포함)."""
    stocks = data.get("stocks", {})
    fg = data.get("fear_greed_index", {}).get("current", {})
    date = data.get("date", "unknown")

    # v2 데이터 추출
    intelligence = data.get("intelligence", {})
    events = data.get("events", {})
    fundamentals_raw = data.get("fundamentals", {})
    fundamentals = fundamentals_raw.get("fundamentals", fundamentals_raw)
    signal_accuracy = data.get("signal_accuracy")

    stock_summaries = []
    for symbol, info in stocks.items():
        ind = info.get("indicators", {})
        regime = info.get("regime", {})
        price = info.get("price", {})
        diag = info.get("signal_diagnosis", {})
        patterns = info.get("patterns", {})

        summary = {
            "symbol": symbol,
            "regime": regime.get("state", "N/A"),
            "regime_conf": regime.get("confidence", 0),
            "rsi": ind.get("rsi", {}).get("value"),
            "rsi_signal": ind.get("rsi", {}).get("signal"),
            "macd_signal": ind.get("macd", {}).get("signal"),
            "macd_cross": ind.get("macd", {}).get("cross_recent"),
            "adx": ind.get("adx", {}).get("value"),
            "adx_trend": ind.get("adx", {}).get("trend"),
            "bb_pctb": ind.get("bollinger", {}).get("pct_b"),
            "stoch_k": ind.get("stochastic", {}).get("k"),
            "change_5d": price.get("change_5d"),
            "change_20d": price.get("change_20d"),
            "optimal_oversold": diag.get("optimal_rsi_range", {}).get("oversold"),
            "optimal_overbought": diag.get("optimal_rsi_range", {}).get(
                "overbought"
            ),
            "support_levels": patterns.get("support_levels", []),
            "double_bottom": patterns.get("double_bottom", False),
        }

        # v2: 펀더멘탈 추가
        fund = fundamentals.get(symbol, {})
        if fund:
            summary["pe_ratio"] = fund.get("pe_ratio")
            summary["forward_pe"] = fund.get("forward_pe")
            summary["eps"] = fund.get("eps")
            summary["dividend_yield"] = fund.get("dividend_yield")
            summary["beta"] = fund.get("beta")

        # v2: 실적발표일 추가
        earnings = events.get("earnings", {}).get(symbol, {})
        if earnings:
            summary["earnings_date"] = earnings.get("date")
            summary["earnings_days_until"] = earnings.get("days_until")

        stock_summaries.append(summary)

    # v2: 인텔리전스 요약
    intel_summary = {}
    if intelligence:
        overall = intelligence.get("overall", {})
        intel_summary["overall_score"] = overall.get("score")
        intel_summary["overall_signal"] = overall.get("signal")
        layers = intelligence.get("layers", {})
        intel_summary["layers"] = {
            name: {"score": l.get("score"), "signal": l.get("signal")}
            for name, l in layers.items()
        }

    # v2: FOMC 일정
    fomc_summary = {}
    fomc = events.get("fomc", {})
    if fomc:
        fomc_summary["next_date"] = fomc.get("next_date")
        fomc_summary["days_until"] = fomc.get("days_until")

    # v3: 경제지표/옵션/VIX 일정
    events_summary = {}
    economic = events.get("economic", {})
    if economic:
        events_summary["economic"] = {
            k: v for k, v in economic.items()
            if v.get("next_date")
        }
    options = events.get("options", {})
    if options.get("monthly_expiry", {}).get("next_date"):
        events_summary["options"] = {
            "monthly_expiry": options["monthly_expiry"],
            "is_quad_witching": options.get("is_quad_witching", False),
        }
    vix_expiry = events.get("vix_expiry", {})
    if vix_expiry.get("next_date"):
        events_summary["vix_expiry"] = vix_expiry

    prompt_obj = {
        "date": date,
        "fear_greed": fg.get("value"),
        "fear_greed_class": fg.get("classification"),
        "stocks": stock_summaries,
    }
    if intel_summary:
        prompt_obj["intelligence"] = intel_summary
    if fomc_summary:
        prompt_obj["fomc"] = fomc_summary
    if events_summary:
        prompt_obj["events"] = events_summary
    if signal_accuracy:
        prompt_obj["signal_accuracy"] = signal_accuracy

    prompt_data = json.dumps(prompt_obj, ensure_ascii=False, indent=2)

    return f"""다음 시장 분석 데이터를 기반으로 TradingView Pine Script에 삽입할 코멘터리를 생성하세요.

데이터:
{prompt_data}

아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

{{
  "market_summary": "전체 시장 한줄 요약 (최대 35자 한글)",
  "comments": {{
    "SYMBOL": "종목별 한줄 코멘트 (최대 30자 한글)"
  }},
  "strategies": {{
    "SYMBOL": "종목별 추천 전략 한줄 (최대 20자 한글)"
  }},
  "alerts": {{
    "SYMBOL": "rsi_extreme 또는 macd_cross 또는 bb_extreme 또는 stoch_cross 중 하나"
  }}
}}

규칙:
1. comments: 레짐+지표+펀더멘탈+이벤트를 종합한 코멘트. 예:
   - "실적 D-5, PER 고평가, 관망" (실적 임박 + 밸류에이션)
   - "RSI 과매도+강세감성, 반등 기대" (기술적 + 감성)
   - "FOMC 전 변동성 확대 주의" (이벤트 영향)
2. strategies: 액션 지향적 전략. 예: "BB 하단 매수 대기", "실적 전 포지션 축소", "추세 추종 홀드"
3. alerts: 레짐에 적합한 알림 조건 선택:
   - VOLATILE → bb_extreme (BB %B 극단 알림)
   - BULLISH/BEARISH (ADX>25) → macd_cross (MACD 크로스 알림)
   - SIDEWAYS → rsi_extreme (RSI 극단 알림)
   - stoch_cross는 Stochastic 크로스가 유의미한 경우 사용
   - 실적발표 7일 이내 → rsi_extreme 우선 (변동성 대비)
4. market_summary: F&G + 인텔리전스 종합점수 + FOMC 일정을 반영한 시장 요약
5. 인텔리전스 overall_score가 +30 이상이면 강세 편향, -30 이하면 약세 편향 반영
6. 모든 텍스트는 한글로 작성
7. 모든 종목(symbol)에 대해 빠짐없이 작성"""


def _call_claude_cli(prompt: str) -> dict | None:
    """claude CLI를 호출하여 LLM 코멘터리를 생성합니다."""
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.warning("claude CLI를 찾을 수 없습니다")
        return None

    # CLAUDECODE 환경 변수 제거 (중첩 세션 방지)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        proc = subprocess.run(
            [
                claude_path,
                "-p",
                "--model",
                LLM_MODEL,
                "--output-format",
                "text",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT,
            env=env,
        )

        if proc.returncode != 0:
            logger.warning(f"claude CLI 실패 (returncode={proc.returncode})")
            if proc.stderr:
                logger.warning(f"stderr: {proc.stderr[:300]}")
            return None

        return _extract_json(proc.stdout)

    except subprocess.TimeoutExpired:
        logger.warning(f"claude CLI 타임아웃 ({LLM_TIMEOUT}초)")
        return None
    except FileNotFoundError:
        logger.warning("claude CLI 실행 불가")
        return None
    except Exception as e:
        logger.warning(f"claude CLI 오류: {e}")
        return None


def _rule_based_commentary(data: dict) -> dict:
    """규칙 기반 코멘터리를 생성합니다 (LLM 폴백, v2 데이터 활용)."""
    stocks = data.get("stocks", {})
    fg = data.get("fear_greed_index", {}).get("current", {})
    fg_value = fg.get("value", 50)

    # v2 데이터 추출
    intelligence = data.get("intelligence", {})
    intel_score = intelligence.get("overall", {}).get("score", 0)
    events = data.get("events", {})
    fomc = events.get("fomc", {})
    fomc_days = fomc.get("days_until")
    earnings_map = events.get("earnings", {})
    fundamentals_raw = data.get("fundamentals", {})
    fundamentals = fundamentals_raw.get("fundamentals", fundamentals_raw)

    # v3: 추가 이벤트 추출
    economic = events.get("economic", {})
    options = events.get("options", {})
    near_economic = False
    near_economic_name = None
    econ_label_map = {
        'nfp': 'NFP', 'cpi': 'CPI', 'ppi': 'PPI', 'pce': 'PCE',
        'gdp': 'GDP', 'ism_manufacturing': 'ISM', 'ism_services': 'ISM',
        'jackson_hole': '잭슨홀',
    }
    for name, info in economic.items():
        if info.get('days_until') is not None and info['days_until'] <= 3:
            near_economic = True
            near_economic_name = econ_label_map.get(name, name)
            break
    is_quad = options.get('is_quad_witching', False)
    opt_days = options.get('monthly_expiry', {}).get('days_until')

    comments = {}
    strategies = {}
    alerts = {}

    for symbol, info in stocks.items():
        ind = info.get("indicators", {})
        regime = info.get("regime", {}).get("state", "SIDEWAYS")
        rsi = ind.get("rsi", {}).get("value", 50)
        adx = ind.get("adx", {}).get("value", 0)
        bb_pctb = ind.get("bollinger", {}).get("pct_b", 0.5)
        diag = info.get("signal_diagnosis", {})
        optimal = diag.get("optimal_rsi_range", {})
        oversold = optimal.get("oversold", 30)
        overbought = optimal.get("overbought", 70)

        # v2: 실적/펀더멘탈 컨텍스트
        earnings = earnings_map.get(symbol, {})
        earnings_days = earnings.get("days_until")
        fund = fundamentals.get(symbol, {})
        pe = fund.get("pe_ratio")

        # 코멘트 생성 (v3: 이벤트/펀더멘탈 우선)
        if earnings_days is not None and earnings_days <= 7:
            comments[symbol] = f"실적 D-{earnings_days}, 변동성 대비"
        elif near_economic:
            comments[symbol] = f"{near_economic_name} 발표 임박, 변동성 대비"
        elif is_quad and opt_days is not None and opt_days <= 3:
            comments[symbol] = "쿼드위칭 주간, 유동성 주의"
        elif fomc_days is not None and fomc_days <= 3:
            comments[symbol] = "FOMC 임박, 관망 권장"
        elif rsi < oversold:
            if intel_score > 20:
                comments[symbol] = "RSI 과매도+강세환경, 반등 기대"
            else:
                comments[symbol] = "RSI 과매도, 반등 모니터링"
        elif rsi > overbought:
            if pe and pe > 40:
                comments[symbol] = "RSI 과매수+고PER, 차익실현"
            else:
                comments[symbol] = "RSI 과매수, 차익실현 고려"
        elif regime == "VOLATILE":
            comments[symbol] = "변동성 확대, 리스크 관리 주의"
        elif regime == "BEARISH":
            comments[symbol] = "하락 추세, 진입 보류"
        elif regime == "BULLISH":
            comments[symbol] = "상승 추세, 추세 추종 유효"
        elif adx > 30:
            comments[symbol] = "강한 추세, 방향 확인 필요"
        else:
            comments[symbol] = "중립 구간, 관망"

        # 전략 생성 (v3: 이벤트 반영)
        if earnings_days is not None and earnings_days <= 7:
            strategies[symbol] = "실적 전 포지션 축소"
        elif near_economic:
            strategies[symbol] = "지표 발표 전 관망"
        elif is_quad and opt_days is not None and opt_days <= 3:
            strategies[symbol] = "만기 변동성 경계"
        elif regime == "VOLATILE":
            strategies[symbol] = "BB 밴드 이탈 대기"
        elif regime == "BEARISH":
            if rsi < oversold:
                strategies[symbol] = "반등 시 소량 진입"
            else:
                strategies[symbol] = "관망 또는 손절 설정"
        elif regime == "BULLISH":
            strategies[symbol] = "추세 추종 홀드"
        else:
            if bb_pctb < 0.2:
                strategies[symbol] = "BB 하단 매수 대기"
            elif bb_pctb > 0.8:
                strategies[symbol] = "BB 상단 매도 고려"
            else:
                strategies[symbol] = "레인지 매매 대기"

        # 알림 유형 (v2: 실적 임박 시 rsi_extreme 우선)
        if earnings_days is not None and earnings_days <= 7:
            alerts[symbol] = "rsi_extreme"
        else:
            alerts[symbol] = _REGIME_ALERT_MAP.get(regime, "rsi_extreme")

    # 시장 요약 (v2: 인텔리전스 점수 + FOMC 반영)
    bullish = sum(
        1
        for s in stocks.values()
        if s.get("regime", {}).get("state") == "BULLISH"
    )
    bearish = sum(
        1
        for s in stocks.values()
        if s.get("regime", {}).get("state") == "BEARISH"
    )
    volatile = sum(
        1
        for s in stocks.values()
        if s.get("regime", {}).get("state") == "VOLATILE"
    )

    if near_economic:
        market_summary = f"{near_economic_name} 임박, 변동성 경계"
    elif is_quad and opt_days is not None and opt_days <= 3:
        market_summary = "쿼드위칭 주간, 유동성 주의"
    elif fomc_days is not None and fomc_days <= 3:
        market_summary = f"FOMC D-{fomc_days}, 변동성 경계"
    elif fg_value and fg_value < 30:
        if intel_score > 20:
            market_summary = "극단적 공포+강세신호, 역발상 매수"
        else:
            market_summary = "극단적 공포, 역발상 매수 관점 주시"
    elif fg_value and fg_value > 70:
        if intel_score < -20:
            market_summary = "극단적 탐욕+약세신호, 리스크 경고"
        else:
            market_summary = "극단적 탐욕, 리스크 관리 강화"
    elif intel_score >= 30:
        market_summary = "인텔리전스 강세, 적극 매수 구간"
    elif intel_score <= -30:
        market_summary = "인텔리전스 약세, 방어적 접근"
    elif bearish > len(stocks) * 0.5:
        market_summary = "약세 우위, 보수적 접근 권장"
    elif bullish > len(stocks) * 0.5:
        market_summary = "강세 우위, 추세 추종 유효"
    elif volatile > len(stocks) * 0.3:
        market_summary = "변동성 장세, 종목별 선별 접근"
    else:
        market_summary = "혼조세, 관망 후 선별 진입"

    return {
        "market_summary": market_summary,
        "comments": comments,
        "strategies": strategies,
        "alerts": alerts,
    }


def _get_commentary(data: dict, use_llm: bool) -> dict:
    """LLM 코멘터리를 가져오거나 규칙 기반 폴백을 사용합니다."""
    fallback = _rule_based_commentary(data)
    fallback["_source"] = "rule_based"

    if not use_llm:
        logger.info("LLM 비활성화 (--no-llm) - 규칙 기반 코멘터리 사용")
        return fallback

    prompt = _build_llm_prompt(data)
    llm_result = _call_claude_cli(prompt)

    if llm_result is None:
        logger.warning("LLM 호출 실패 - 규칙 기반 폴백 사용")
        return fallback

    # 필수 키 검증
    required_keys = {"market_summary", "comments", "strategies", "alerts"}
    if not required_keys.issubset(llm_result.keys()):
        missing = required_keys - llm_result.keys()
        logger.warning(f"LLM 응답 구조 불일치 (누락: {missing}) - 규칙 기반 폴백 사용")
        return fallback

    stocks = data.get("stocks", {})
    symbols = set(stocks.keys())

    # 누락 종목 폴백 보충
    for key in ("comments", "strategies", "alerts"):
        if not isinstance(llm_result.get(key), dict):
            llm_result[key] = fallback[key]
            continue
        for symbol in symbols:
            if symbol not in llm_result[key]:
                llm_result[key][symbol] = fallback[key].get(symbol, "N/A")

    # 알림 값 검증
    valid_alerts = {"rsi_extreme", "macd_cross", "bb_extreme", "stoch_cross"}
    for symbol, alert in llm_result["alerts"].items():
        if alert not in valid_alerts:
            llm_result["alerts"][symbol] = fallback["alerts"].get(
                symbol, "rsi_extreme"
            )

    # 텍스트 길이 제한 (Pine Script 셀 폭)
    ms = llm_result.get("market_summary", "")
    if len(ms) > 40:
        llm_result["market_summary"] = ms[:37] + "..."
    for symbol in list(llm_result["comments"].keys()):
        t = llm_result["comments"][symbol]
        if len(t) > 35:
            llm_result["comments"][symbol] = t[:32] + "..."
    for symbol in list(llm_result["strategies"].keys()):
        t = llm_result["strategies"][symbol]
        if len(t) > 25:
            llm_result["strategies"][symbol] = t[:22] + "..."

    # 개행/특수문자 제거
    for key in ("comments", "strategies"):
        for symbol in llm_result[key]:
            llm_result[key][symbol] = (
                llm_result[key][symbol].replace("\n", " ").replace("\\", "")
            )
    llm_result["market_summary"] = (
        llm_result["market_summary"].replace("\n", " ").replace("\\", "")
    )

    llm_result["_source"] = "llm"
    logger.info("LLM 코멘터리 생성 성공")
    return llm_result


# ==================== Pine Script 생성 ====================


def generate_combined_script(data: dict, commentary: dict) -> str:
    """통합 Pine Script (단일 패널) 생성.

    하나의 overlay=false 지표에 모든 정보를 통합:
    - 플롯: RSI, ADX, Stochastic, BB %B (0-100 스케일)
    - 테이블: 시장 요약, 레짐, 가격, 지지선, 패턴, F&G,
              RSI (zone + 트리거), ADX (trend), MACD (histogram + cross),
              BB (signal), Stochastic (signal), AI 코멘터리
    - 알림: 종목별 레짐 기반 alertcondition + 이중바닥 복합 알림
    - 배경: RSI 과매도/과매수 + ADX 추세 + 이중바닥 패턴
    """
    date = data.get("date", "unknown")
    stocks = data.get("stocks", {})
    fear_greed = data.get("fear_greed_index", {}).get("current", {})
    fg_value = fear_greed.get("value", "N/A")
    fg_class = fear_greed.get("classification", "N/A")
    commentary_source = commentary.get("_source", "rule_based")
    market_summary = commentary.get("market_summary", "N/A").replace('"', "'")

    # --- 종목별 최적 RSI switch ---
    rsi_cases = []
    for symbol, info in stocks.items():
        diag = info.get("signal_diagnosis", {})
        optimal = diag.get("optimal_rsi_range", {})
        oversold = optimal.get("oversold", 30)
        overbought = optimal.get("overbought", 70)
        rsi_cases.append(f'        "{symbol}" => [{oversold}, {overbought}]')
    rsi_switch = "\n".join(rsi_cases)

    # --- 종목별 참조 ADX switch ---
    adx_cases = []
    for symbol, info in stocks.items():
        adx_val = info.get("indicators", {}).get("adx", {}).get("value", 0)
        adx_cases.append(f'        "{symbol}" => {adx_val:.1f}')
    adx_switch = "\n".join(adx_cases)

    # --- 종목별 레짐 switch ---
    regime_cases = []
    for symbol, info in stocks.items():
        regime = info.get("regime", {})
        state = regime.get("state", "N/A")
        conf = regime.get("confidence", 0)
        regime_cases.append(f'        "{symbol}" => ["{state}", "{conf:.0%}"]')
    regime_switch = "\n".join(regime_cases)

    # --- 종목별 가격 정보 switch ---
    price_cases = []
    for symbol, info in stocks.items():
        price = info.get("price", {})
        last = price.get("last", 0)
        chg5 = price.get("change_5d", 0)
        chg20 = price.get("change_20d", 0)
        price_cases.append(f'        "{symbol}" => [{last}, {chg5}, {chg20}]')
    price_switch = "\n".join(price_cases)

    # --- 종목별 지지선 switch ---
    support_cases = []
    for symbol, info in stocks.items():
        levels = info.get("patterns", {}).get("support_levels", [])
        if levels:
            vals = [f"{v:.2f}" for v in levels[:3]]
            while len(vals) < 3:
                vals.append("na")
            support_cases.append(
                f'        "{symbol}" => [{vals[0]}, {vals[1]}, {vals[2]}]'
            )
    support_switch = "\n".join(support_cases)

    # --- AI 코멘트 switch ---
    comment_cases = []
    for symbol in stocks:
        comment = commentary["comments"].get(symbol, "N/A").replace('"', "'")
        comment_cases.append(f'        "{symbol}" => "{comment}"')
    comment_switch = "\n".join(comment_cases)

    # --- AI 전략 switch ---
    strategy_cases = []
    for symbol in stocks:
        strat = commentary["strategies"].get(symbol, "N/A").replace('"', "'")
        strategy_cases.append(f'        "{symbol}" => "{strat}"')
    strategy_switch = "\n".join(strategy_cases)

    # --- 알림 유형 switch ---
    alert_cases = []
    for symbol in stocks:
        alert = commentary["alerts"].get(symbol, "rsi_extreme")
        alert_cases.append(f'        "{symbol}" => "{alert}"')
    alert_switch = "\n".join(alert_cases)

    # --- 종목별 이중 바닥 패턴 switch ---
    double_bottom_cases = []
    for symbol, info in stocks.items():
        db = info.get("patterns", {}).get("double_bottom", False)
        double_bottom_cases.append(
            f'        "{symbol}" => {"true" if db else "false"}'
        )
    double_bottom_switch = "\n".join(double_bottom_cases)

    # --- 종목별 RSI zone 라벨 switch ---
    rsi_zone_cases = []
    for symbol, info in stocks.items():
        zone = info.get("indicators", {}).get("rsi", {}).get("zone", "N/A")
        rsi_zone_cases.append(f'        "{symbol}" => "{zone}"')
    rsi_zone_switch = "\n".join(rsi_zone_cases)

    # --- 종목별 RSI 35/65 트리거 switch ---
    rsi_trigger_cases = []
    for symbol, info in stocks.items():
        diag = info.get("signal_diagnosis", {}).get("rsi_35_65", {})
        buy = diag.get("buy_triggered", False)
        sell = diag.get("sell_triggered", False)
        if buy and sell:
            trigger = "BUY+SELL"
        elif buy:
            trigger = "BUY"
        elif sell:
            trigger = "SELL"
        else:
            trigger = "NONE"
        rsi_trigger_cases.append(f'        "{symbol}" => "{trigger}"')
    rsi_trigger_switch = "\n".join(rsi_trigger_cases)

    # --- 종목별 ADX 추세 라벨 switch ---
    adx_trend_cases = []
    for symbol, info in stocks.items():
        trend = info.get("indicators", {}).get("adx", {}).get("trend", "N/A")
        adx_trend_cases.append(f'        "{symbol}" => "{trend}"')
    adx_trend_switch = "\n".join(adx_trend_cases)

    # --- 종목별 MACD 상세 switch ---
    macd_hist_cases = []
    macd_signal_cases = []
    macd_cross_cases = []
    for symbol, info in stocks.items():
        macd = info.get("indicators", {}).get("macd", {})
        hist = macd.get("histogram", 0)
        sig = macd.get("signal", "N/A")
        cross = macd.get("cross_recent", False)
        macd_hist_cases.append(f'        "{symbol}" => {hist:.3f}')
        macd_signal_cases.append(f'        "{symbol}" => "{sig}"')
        macd_cross_cases.append(
            f'        "{symbol}" => {"true" if cross else "false"}'
        )
    macd_hist_switch = "\n".join(macd_hist_cases)
    macd_signal_switch = "\n".join(macd_signal_cases)
    macd_cross_switch = "\n".join(macd_cross_cases)

    # --- 종목별 BB signal 라벨 switch ---
    bb_signal_cases = []
    for symbol, info in stocks.items():
        bb_sig = (
            info.get("indicators", {}).get("bollinger", {}).get("signal", "N/A")
        )
        bb_signal_cases.append(f'        "{symbol}" => "{bb_sig}"')
    bb_signal_switch = "\n".join(bb_signal_cases)

    # --- 종목별 Stochastic signal 라벨 switch ---
    stoch_signal_cases = []
    for symbol, info in stocks.items():
        stoch_sig = (
            info.get("indicators", {}).get("stochastic", {}).get("signal", "N/A")
        )
        stoch_signal_cases.append(f'        "{symbol}" => "{stoch_sig}"')
    stoch_signal_switch = "\n".join(stoch_signal_cases)

    # --- 시장 전체 요약 (정적 데이터) ---
    mkt = data.get("market_summary", {})
    mkt_bullish = mkt.get("bullish_count", 0)
    mkt_bearish = mkt.get("bearish_count", 0)
    mkt_sideways = mkt.get("sideways_count", 0)
    mkt_avg_rsi = mkt.get("avg_rsi", 0)
    mkt_sentiment = mkt.get("market_sentiment", "N/A").replace('"', "'")
    notable_events = mkt.get("notable_events", [])
    notable_1 = (
        notable_events[0].replace('"', "'")[:40] if len(notable_events) > 0 else ""
    )
    notable_2 = (
        notable_events[1].replace('"', "'")[:40] if len(notable_events) > 1 else ""
    )

    # 코멘터리 소스 라벨
    source_label = "AI" if commentary_source == "llm" else "Rule"

    script = f"""//@version=6
indicator("Market Analysis [{date}]", overlay=false)

// ============================================================
// 자동 생성됨 - 시장 분석 JSON ({date})
// 통합 패널: RSI + ADX + Stochastic + BB %B + AI 코멘터리
// 코멘터리 소스: {commentary_source}
// ============================================================

// ==================== 데이터 함수 ====================

// 종목별 최적 RSI 파라미터 (시장 분석 결과)
getOptimalRSI() =>
    switch syminfo.ticker
{rsi_switch}
        => [30, 70]

[optOversold, optOverbought] = getOptimalRSI()

// 종목별 참조 ADX (분석 시점)
getRefADX() =>
    switch syminfo.ticker
{adx_switch}
        => 0.0

refADX = getRefADX()

// 종목별 시장 레짐
getRegimeInfo() =>
    switch syminfo.ticker
{regime_switch}
        => ["N/A", "N/A"]

[regimeState, regimeConf] = getRegimeInfo()

// 종목별 가격 정보
getPriceInfo() =>
    switch syminfo.ticker
{price_switch}
        => [0.0, 0.0, 0.0]

[refPrice, chg5d, chg20d] = getPriceInfo()

// 종목별 지지선
getSupportLevels() =>
    switch syminfo.ticker
{support_switch}
        => [na, na, na]

[sup1, sup2, sup3] = getSupportLevels()

// 종목별 AI 코멘트
getAIComment() =>
    switch syminfo.ticker
{comment_switch}
        => "N/A"

aiComment = getAIComment()

// 종목별 추천 전략
getAIStrategy() =>
    switch syminfo.ticker
{strategy_switch}
        => "N/A"

aiStrategy = getAIStrategy()

// 종목별 알림 유형
getAlertType() =>
    switch syminfo.ticker
{alert_switch}
        => "rsi_extreme"

alertType = getAlertType()

// 종목별 이중 바닥 패턴
getDoubleBottom() =>
    switch syminfo.ticker
{double_bottom_switch}
        => false

hasDoubleBottom = getDoubleBottom()

// 종목별 RSI zone 라벨
getRSIZone() =>
    switch syminfo.ticker
{rsi_zone_switch}
        => "N/A"

rsiZone = getRSIZone()

// 종목별 RSI 35/65 트리거
getRSITrigger() =>
    switch syminfo.ticker
{rsi_trigger_switch}
        => "NONE"

rsiTrigger = getRSITrigger()

// 종목별 ADX 추세 라벨
getADXTrend() =>
    switch syminfo.ticker
{adx_trend_switch}
        => "N/A"

adxTrend = getADXTrend()

// 종목별 MACD 히스토그램 (분석 시점)
getMACDHist() =>
    switch syminfo.ticker
{macd_hist_switch}
        => 0.0

refMACDHist = getMACDHist()

// 종목별 MACD 시그널 방향
getMACDDir() =>
    switch syminfo.ticker
{macd_signal_switch}
        => "N/A"

refMACDDir = getMACDDir()

// 종목별 MACD 최근 크로스
getMACDCross() =>
    switch syminfo.ticker
{macd_cross_switch}
        => false

refMACDCross = getMACDCross()

// 종목별 BB signal 라벨
getBBSignal() =>
    switch syminfo.ticker
{bb_signal_switch}
        => "N/A"

bbSignalLabel = getBBSignal()

// 종목별 Stochastic signal 라벨
getStochSignal() =>
    switch syminfo.ticker
{stoch_signal_switch}
        => "N/A"

stochSignalLabel = getStochSignal()

// ==================== 지표 계산 ====================

// --- RSI (14) ---
rsi_val = ta.rsi(close, 14)

// --- ADX (14) ---
[diPlus, diMinus, adx_val] = ta.dmi(14, 14)

// --- Stochastic (14, 3, 3) ---
stoch_k = ta.sma(ta.stoch(close, high, low, 14), 3)
stoch_d = ta.sma(stoch_k, 3)

// --- Bollinger Bands %B (20, 2.0) → 0~100 스케일 ---
bb_basis = ta.sma(close, 20)
bb_dev = 2.0 * ta.stdev(close, 20)
bb_upper = bb_basis + bb_dev
bb_lower = bb_basis - bb_dev
bb_pctB = (close - bb_lower) / (bb_upper - bb_lower) * 100

// --- MACD (알림용) ---
[macdLine, macdSignal, _macdHist] = ta.macd(close, 12, 26, 9)
macdCrossUp = ta.crossover(macdLine, macdSignal)
macdCrossDown = ta.crossunder(macdLine, macdSignal)

// --- MACD 신뢰도 (ADX 30+ = Valid) ---
macdValid = adx_val >= 30

// --- Stochastic 크로스 (알림용) ---
stochCrossUp = ta.crossover(stoch_k, stoch_d)
stochCrossDown = ta.crossunder(stoch_k, stoch_d)

// ==================== 플롯 ====================

// RSI (메인)
plot(rsi_val, "RSI", color=color.new(color.purple, 0), linewidth=2)

// 종목별 최적 RSI 존 (plot 사용 - switch 결과는 hline 불가)
p_os = plot(optOversold, "Optimal Oversold", color=color.new(color.green, 30), style=plot.style_line, linewidth=1)
p_ob = plot(optOverbought, "Optimal Overbought", color=color.new(color.red, 30), style=plot.style_line, linewidth=1)
fill(p_os, p_ob, color=color.new(color.purple, 93))

// 고정 기준선
hline(50, "50", color=color.new(color.gray, 80), linestyle=hline.style_dotted)
hline(30, "30", color=color.new(color.gray, 80), linestyle=hline.style_dotted)
hline(70, "70", color=color.new(color.gray, 80), linestyle=hline.style_dotted)

// ADX
plot(adx_val, "ADX", color=color.new(color.yellow, 0), linewidth=1)

// Stochastic
plot(stoch_k, "Stoch %K", color=color.new(color.aqua, 30), linewidth=1)
plot(stoch_d, "Stoch %D", color=color.new(color.orange, 40), linewidth=1)

// BB %B (0~100)
plot(bb_pctB, "BB %B", color=color.new(color.blue, 20), linewidth=1, style=plot.style_stepline)

// ==================== 배경색 ====================

// RSI 과매도/과매수 존
bgcolor(rsi_val <= optOversold ? color.new(color.green, 90) : na, title="RSI Oversold")
bgcolor(rsi_val >= optOverbought ? color.new(color.red, 90) : na, title="RSI Overbought")

// ADX 추세 강도
bgcolor(adx_val >= 30 ? color.new(color.green, 94) : adx_val >= 20 ? color.new(color.yellow, 94) : na, title="ADX Trend")

// 이중 바닥 패턴 강조
bgcolor(hasDoubleBottom ? color.new(color.lime, 92) : na, title="Double Bottom")

// ==================== 알림 조건 ====================

// RSI 극단 알림
alertcondition(alertType == "rsi_extreme" and (rsi_val <= optOversold or rsi_val >= optOverbought), title="RSI Extreme", message="RSI {{{{ticker}}}}: 극단 영역 진입")

// MACD 크로스 알림
alertcondition(alertType == "macd_cross" and (macdCrossUp or macdCrossDown), title="MACD Cross", message="MACD {{{{ticker}}}}: 크로스 발생")

// BB 극단 알림
alertcondition(alertType == "bb_extreme" and (bb_pctB <= 5 or bb_pctB >= 95), title="BB Extreme", message="BB %B {{{{ticker}}}}: 극단 영역")

// Stochastic 크로스 알림
alertcondition(alertType == "stoch_cross" and (stochCrossUp or stochCrossDown), title="Stoch Cross", message="Stochastic {{{{ticker}}}}: K/D 크로스")

// 이중 바닥 + RSI 과매도 복합 알림
alertcondition(hasDoubleBottom and rsi_val <= optOversold, title="Double Bottom + Oversold", message="{{{{ticker}}}}: 이중바닥 + RSI 과매도 — 반등 주시")

// MACD 크로스 지속 확인 알림 (분석 시점 크로스 + 실시간 크로스)
alertcondition(refMACDCross and (macdCrossUp or macdCrossDown), title="MACD Cross Confirmed", message="MACD {{{{ticker}}}}: 분석 시점 크로스 지속 확인")

// ==================== 정보 테이블 ====================

var table infoTable = table.new(position.top_right, 2, 20, bgcolor=color.new(color.black, 80), border_width=1)

if barstate.islast
    // 레짐 색상
    regimeColor = switch regimeState
        "BULLISH"  => color.green
        "BEARISH"  => color.red
        "VOLATILE" => color.orange
        => color.gray

    // === 시장 전체 ===
    // Row 0: 분석 날짜
    table.cell(infoTable, 0, 0, "Date", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 0, "{date}", text_color=color.white, text_size=size.small)

    // Row 1: 시장 현황 (센티먼트 + 강세/횡보/약세 종목 수 + 평균 RSI)
    table.cell(infoTable, 0, 1, "Market", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 1, "{mkt_sentiment} | B:{mkt_bullish} S:{mkt_sideways} R:{mkt_bearish} | RSI:{mkt_avg_rsi:.0f}", text_color=color.white, text_size=size.small)

    // Row 2: 주목 이벤트 1
    table.cell(infoTable, 0, 2, "Notable", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 2, "{notable_1}", text_color=color.orange, text_size=size.small)

    // Row 3: 주목 이벤트 2
    table.cell(infoTable, 0, 3, "", text_size=size.small)
    table.cell(infoTable, 1, 3, "{notable_2}", text_color=color.orange, text_size=size.small)

    // === 종목 정보 ===
    // Row 4: 레짐
    table.cell(infoTable, 0, 4, "Regime", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 4, regimeState + " (" + regimeConf + ")", text_color=regimeColor, text_size=size.small)

    // Row 5: 가격 변동
    table.cell(infoTable, 0, 5, "5D / 20D", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 5, str.tostring(chg5d, "+#.#;-#.#") + "% / " + str.tostring(chg20d, "+#.#;-#.#") + "%", text_color=color.white, text_size=size.small)

    // Row 6: F&G
    table.cell(infoTable, 0, 6, "F&G", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 6, "{fg_value} ({fg_class})", text_color=color.yellow, text_size=size.small)

    // Row 7: 지지선
    table.cell(infoTable, 0, 7, "Support", text_color=color.gray, text_size=size.small)
    supText = (not na(sup1) ? str.tostring(sup1, "#.#") : "-") + " / " + (not na(sup2) ? str.tostring(sup2, "#.#") : "-") + " / " + (not na(sup3) ? str.tostring(sup3, "#.#") : "-")
    table.cell(infoTable, 1, 7, supText, text_color=color.green, text_size=size.small)

    // Row 8: 패턴 (이중 바닥)
    table.cell(infoTable, 0, 8, "Pattern", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 8, hasDoubleBottom ? "Double Bottom" : "-", text_color=hasDoubleBottom ? color.lime : color.gray, text_size=size.small)

    // === 지표 상세 ===
    // Row 9: 구분선
    table.cell(infoTable, 0, 9, "", text_size=size.small)
    table.cell(infoTable, 1, 9, "", text_size=size.small)

    // Row 10: RSI (현재값 + zone 라벨 + 최적 범위)
    table.cell(infoTable, 0, 10, "RSI", text_color=color.gray, text_size=size.small)
    rsiColor = rsi_val <= optOversold ? color.green : rsi_val >= optOverbought ? color.red : color.white
    table.cell(infoTable, 1, 10, str.tostring(rsi_val, "#.#") + " [" + rsiZone + "] " + str.tostring(optOversold) + "/" + str.tostring(optOverbought), text_color=rsiColor, text_size=size.small)

    // Row 11: RSI 트리거 상태 (35/65 기준)
    table.cell(infoTable, 0, 11, "RSI Trig", text_color=color.gray, text_size=size.small)
    trigColor = rsiTrigger == "BUY" ? color.green : rsiTrigger == "SELL" ? color.red : rsiTrigger == "BUY+SELL" ? color.orange : color.gray
    table.cell(infoTable, 1, 11, rsiTrigger, text_color=trigColor, text_size=size.small)

    // Row 12: ADX (현재값 + 추세 라벨)
    table.cell(infoTable, 0, 12, "ADX", text_color=color.gray, text_size=size.small)
    adxColor = adx_val >= 30 ? color.green : adx_val >= 20 ? color.yellow : color.gray
    table.cell(infoTable, 1, 12, str.tostring(adx_val, "#.#") + " (" + adxTrend + ")", text_color=adxColor, text_size=size.small)

    // Row 13: MACD (방향 + 히스토그램 + 크로스 + 유효성)
    table.cell(infoTable, 0, 13, "MACD", text_color=color.gray, text_size=size.small)
    macdColor = refMACDDir == "bullish" ? color.green : refMACDDir == "bearish" ? color.red : color.gray
    macdText = refMACDDir + " " + str.tostring(refMACDHist, "#.###") + (refMACDCross ? " [CROSS]" : "") + (macdValid ? "" : " [WEAK]")
    table.cell(infoTable, 1, 13, macdText, text_color=macdColor, text_size=size.small)

    // Row 14: BB %B (현재값 + signal 라벨)
    table.cell(infoTable, 0, 14, "BB %B", text_color=color.gray, text_size=size.small)
    bbColor = bb_pctB <= 20 ? color.green : bb_pctB >= 80 ? color.red : color.white
    table.cell(infoTable, 1, 14, str.tostring(bb_pctB, "#.#") + " (" + bbSignalLabel + ")", text_color=bbColor, text_size=size.small)

    // Row 15: Stochastic (K/D + signal 라벨)
    table.cell(infoTable, 0, 15, "Stoch", text_color=color.gray, text_size=size.small)
    stochColor = stoch_k <= 20 ? color.green : stoch_k >= 80 ? color.red : color.white
    table.cell(infoTable, 1, 15, "K:" + str.tostring(stoch_k, "#.#") + " D:" + str.tostring(stoch_d, "#.#") + " (" + stochSignalLabel + ")", text_color=stochColor, text_size=size.small)

    // === AI 코멘터리 ===
    // Row 16: 구분선
    table.cell(infoTable, 0, 16, "", text_size=size.small)
    table.cell(infoTable, 1, 16, "", text_size=size.small)

    // Row 17: AI 시장 요약
    table.cell(infoTable, 0, 17, "{source_label}", text_color=color.aqua, text_size=size.small)
    table.cell(infoTable, 1, 17, "{market_summary}", text_color=color.aqua, text_size=size.small)

    // Row 18: AI 종목 코멘트
    table.cell(infoTable, 0, 18, "Comment", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 18, aiComment, text_color=color.white, text_size=size.small)

    // Row 19: AI 추천 전략
    table.cell(infoTable, 0, 19, "Strategy", text_color=color.gray, text_size=size.small)
    table.cell(infoTable, 1, 19, aiStrategy, text_color=color.yellow, text_size=size.small)
"""
    return script


def generate_pine_scripts(
    json_path: Path,
    stdout: bool = False,
    slack: bool = False,
    use_llm: bool = True,
) -> list[Path]:
    """
    시장 분석 JSON에서 통합 Pine Script를 생성합니다.

    Args:
        json_path: 시장 분석 JSON 경로
        stdout: True면 표준 출력으로만 출력
        slack: True면 Slack으로 .pine 파일 전송
        use_llm: True면 LLM 코멘터리 사용 (실패 시 자동 폴백)

    Returns:
        생성된 파일 경로 리스트
    """
    data = load_analysis(json_path)
    date = data.get("date", "unknown")

    commentary = _get_commentary(data, use_llm=use_llm)
    logger.info(f"코멘터리 소스: {commentary.get('_source', 'unknown')}")

    combined_code = generate_combined_script(data, commentary)

    if stdout:
        print(combined_code)
        return []

    # 파일 저장
    PINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = PINE_OUTPUT_DIR / f"{date}_indicator.pine"
    output_path.write_text(combined_code, encoding="utf-8")
    logger.info(f"통합 스크립트 생성: {output_path}")

    generated_files = [output_path]

    # Slack 전송
    if slack:
        _send_to_slack(generated_files, date)

    return generated_files


def _send_to_slack(files: list[Path], date: str) -> None:
    """생성된 Pine Script 파일을 Slack으로 전송합니다."""
    try:
        from trading_bot.notifications import NotificationService

        notifier = NotificationService()
        for fpath in files:
            success = notifier.upload_file_to_slack(
                str(fpath),
                initial_comment=f"Pine Script ({date}) - {fpath.name}",
                title=fpath.name,
            )
            if success:
                logger.info(f"Slack 전송 성공: {fpath.name}")
            else:
                logger.warning(f"Slack 전송 실패: {fpath.name}")
    except Exception as e:
        logger.error(f"Slack 전송 오류: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="시장 분석 JSON → Pine Script v6 자동 생성 (LLM 코멘터리 포함)"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="분석 날짜 (YYYY-MM-DD). 미지정 시 최신 JSON 사용",
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="생성된 .pine 파일을 Slack으로 전송",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="파일 저장 없이 표준 출력으로만 출력",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM 코멘터리 비활성화 (규칙 기반 폴백 사용)",
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Pine Script Generator 시작")
    logger.info("=" * 50)

    json_path = find_json(args.date)
    if json_path is None:
        logger.error("처리할 JSON 파일이 없습니다. 종료.")
        sys.exit(1)

    logger.info(f"대상 JSON: {json_path}")

    files = generate_pine_scripts(
        json_path,
        stdout=args.stdout,
        slack=args.slack,
        use_llm=not args.no_llm,
    )

    if files:
        logger.info(f"생성 완료: {len(files)}개 파일")
        for f in files:
            logger.info(f"  {f}")


if __name__ == "__main__":
    main()
