"""
일일 시장 분석 수동 실행 스크립트

실제 KIS API로 시가총액 Top 10 종목을 분석하고
JSON 저장 + Claude CLI로 노션 페이지 작성까지 수행합니다.

Usage:
    python scripts/run_market_analysis.py
    python scripts/run_market_analysis.py --symbols AAPL,MSFT,NVDA
    python scripts/run_market_analysis.py --skip-notion  # JSON만 저장, 노션 작성 스킵
"""

import sys
import os
import argparse
import logging
import subprocess
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_bot.market_analyzer import MarketAnalyzer
from trading_bot.market_analysis_prompt import build_analysis_prompt
from trading_bot.brokers import KoreaInvestmentBroker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_broker() -> KoreaInvestmentBroker:
    appkey = os.getenv('KIS_APPKEY', '').strip()
    appsecret = os.getenv('KIS_APPSECRET', '').strip()
    account = os.getenv('KIS_ACCOUNT', '').strip()
    user_id = os.getenv('KIS_USER_ID', account).strip()
    mock = os.getenv('KIS_MOCK', 'true').strip().lower() in ('true', '1', 'yes')

    if not appkey or not appsecret or not account:
        raise ValueError("KIS API 환경 변수 미설정 (.env 파일 확인)")

    return KoreaInvestmentBroker(
        appkey=appkey,
        appsecret=appsecret,
        account=account,
        user_id=user_id,
        mock=mock,
    )


def main():
    parser = argparse.ArgumentParser(description='일일 시장 분석 수동 실행')
    parser.add_argument('--symbols', type=str, default=None,
                        help='분석 종목 (쉼표 구분, 기본: Top 10)')
    parser.add_argument('--skip-notion', action='store_true',
                        help='노션 작성 스킵 (JSON만 저장)')
    parser.add_argument('--output-dir', type=str, default='data/market_analysis',
                        help='JSON 저장 디렉토리')
    args = parser.parse_args()

    # 종목 설정
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    else:
        symbols_env = os.getenv(
            'MARKET_ANALYSIS_SYMBOLS',
            'AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,WMT'
        )
        symbols = [s.strip() for s in symbols_env.split(',')]

    logger.info(f"분석 대상 종목: {', '.join(symbols)}")

    # Step 1: 브로커 초기화
    logger.info("KIS 브로커 초기화...")
    broker = create_broker()
    logger.info("KIS 브로커 초기화 성공")

    # Step 2: 시장 분석
    analyzer = MarketAnalyzer(ohlcv_limit=200, api_delay=0.5)
    logger.info("시장 분석 실행 중...")
    results = analyzer.analyze(symbols, broker)

    if not results['stocks']:
        logger.error("분석 가능한 종목이 없습니다. 종료합니다.")
        sys.exit(1)

    # Step 3: JSON 저장
    json_path = analyzer.save_json(results, output_dir=args.output_dir)
    logger.info(f"JSON 저장 완료: {json_path}")

    # 요약 출력
    summary = results['market_summary']
    logger.info("=" * 60)
    logger.info(f"시장 분석 결과 요약")
    logger.info(f"  분석 종목: {summary['total_stocks']}개")
    logger.info(f"  강세: {summary['bullish_count']}개, 약세: {summary['bearish_count']}개, 횡보: {summary['sideways_count']}개")
    logger.info(f"  평균 RSI: {summary['avg_rsi']}")
    logger.info(f"  시장 심리: {summary['market_sentiment']}")
    if summary['notable_events']:
        logger.info(f"  주목 이벤트:")
        for event in summary['notable_events']:
            logger.info(f"    - {event}")
    logger.info("=" * 60)

    # 종목별 핵심 지표
    for sym, data in results['stocks'].items():
        ind = data['indicators']
        logger.info(
            f"  {sym}: ${data['price']['last']:.2f} | "
            f"RSI={ind['rsi']['value']} ({ind['rsi']['signal']}) | "
            f"MACD={ind['macd']['signal']} | "
            f"레짐={data['regime']['state']}"
        )

    # Step 4: 노션 작성
    if args.skip_notion:
        logger.info("--skip-notion 플래그: 노션 작성 스킵")
        logger.info(f"완료. JSON: {json_path}")
        return

    logger.info("Claude CLI로 노션 페이지 작성 중...")
    prompt = build_analysis_prompt(json_path)

    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", "opus", "--allowedTools", "mcp__claude_ai_Notion__*,Read", prompt],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if proc.returncode == 0:
            logger.info("노션 페이지 작성 성공")
            if proc.stdout:
                logger.info(f"Claude 응답:\n{proc.stdout[:500]}")
        else:
            logger.error(f"노션 작성 실패 (returncode={proc.returncode})")
            if proc.stderr:
                logger.error(f"stderr: {proc.stderr[:500]}")

    except subprocess.TimeoutExpired:
        logger.error("Claude CLI 타임아웃 (180초 초과)")
    except FileNotFoundError:
        logger.error("claude CLI를 찾을 수 없습니다. Claude Code가 설치되어 있는지 확인하세요.")

    logger.info(f"완료. JSON: {json_path}")


if __name__ == '__main__':
    main()
