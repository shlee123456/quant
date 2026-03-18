"""
한국 시장 일일 분석 수동 실행 스크립트

KIS API로 KRX 시가총액 상위 종목을 분석하고
JSON 저장 + Claude CLI로 노션 페이지 작성까지 수행합니다.

Usage:
    python scripts/run_kr_market_analysis.py
    python scripts/run_kr_market_analysis.py --symbols 005930,000660,005380
    python scripts/run_kr_market_analysis.py --skip-notion
"""

import sys
import os
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_bot.kr_market_analyzer import KRMarketAnalyzer, KRX_TOP_SYMBOLS, KR_STOCK_NAMES
from trading_bot.brokers import KoreaInvestmentBroker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_broker() -> KoreaInvestmentBroker:
    """KIS 브로커 인스턴스 생성"""
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


def main() -> None:
    parser = argparse.ArgumentParser(description='한국 시장 일일 분석 수동 실행')
    parser.add_argument('--symbols', type=str, default=None,
                        help='분석 종목 (쉼표 구분, 기본: KRX Top 16)')
    parser.add_argument('--skip-notion', action='store_true',
                        help='노션 작성 스킵 (JSON만 저장)')
    parser.add_argument('--output-dir', type=str, default='data/market_analysis',
                        help='JSON 저장 디렉토리')
    args = parser.parse_args()

    # 종목 설정
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    else:
        symbols_env = os.getenv('KR_MARKET_ANALYSIS_SYMBOLS')
        if symbols_env:
            symbols = [s.strip() for s in symbols_env.split(',')]
        else:
            symbols = list(KRX_TOP_SYMBOLS)

    symbol_names = [f"{s}({KR_STOCK_NAMES.get(s, '?')})" for s in symbols]
    logger.info(f"분석 대상 종목: {', '.join(symbol_names)}")

    # Step 1: 브로커 초기화
    logger.info("KIS 브로커 초기화...")
    broker = create_broker()
    logger.info("KIS 브로커 초기화 성공")

    # Step 2: 시장 분석
    analyzer = KRMarketAnalyzer(ohlcv_limit=200, api_delay=0.5)
    logger.info("한국 시장 분석 실행 중...")
    results = analyzer.analyze(symbols, broker)

    if not results['stocks']:
        logger.error("분석 가능한 종목이 없습니다. 종료합니다.")
        sys.exit(1)

    # Step 2.5: 매크로 시장 환경 분석 (yfinance 기반)
    try:
        macro_result = analyzer.analyze_macro()
        if macro_result:
            results['macro'] = macro_result
            logger.info(
                f"한국 매크로 분석 완료: "
                f"지수 {len(macro_result.get('indices', {}))}개, "
                f"섹터 {len(macro_result.get('sectors', {}))}개"
            )
        else:
            logger.info("매크로 분석 건너뜀 (yfinance 미설치 또는 데이터 없음)")
    except Exception as e:
        logger.warning(f"매크로 분석 실패 (개별 종목 분석은 정상): {e}")

    # Step 2.7: 5-Layer Market Intelligence (한국 시장)
    try:
        from trading_bot.market_intelligence import MarketIntelligence
        mi = MarketIntelligence(market='kr')
        intel_report = mi.analyze(
            stock_symbols=symbols,
            stocks_data=results.get('stocks', {}),
            news_data=results.get('news'),
        )
        results['intelligence'] = intel_report
        logger.info(
            f"5-Layer Intelligence: "
            f"score={intel_report['overall']['score']}, "
            f"signal={intel_report['overall']['signal']}"
        )
    except ImportError:
        logger.info("MarketIntelligence not available - skipping")
    except TypeError:
        # market='kr' 파라미터를 지원하지 않는 경우
        logger.info("MarketIntelligence does not support market='kr' - skipping")
    except Exception as e:
        logger.warning(f"Market Intelligence failed (analysis continues): {e}")

    # Step 3: JSON 저장
    json_path = analyzer.save_json(results, output_dir=args.output_dir)
    logger.info(f"JSON 저장 완료: {json_path}")

    # 요약 출력
    summary = results['market_summary']
    logger.info("=" * 60)
    logger.info("한국 시장 분석 결과 요약")
    logger.info(f"  분석 종목: {summary['total_stocks']}개")
    logger.info(
        f"  강세: {summary['bullish_count']}개, "
        f"약세: {summary['bearish_count']}개, "
        f"횡보: {summary['sideways_count']}개"
    )
    logger.info(f"  평균 RSI: {summary['avg_rsi']}")
    logger.info(f"  시장 심리: {summary['market_sentiment']}")
    if summary['notable_events']:
        logger.info("  주목 이벤트:")
        for event in summary['notable_events']:
            logger.info(f"    - {event}")
    logger.info("=" * 60)

    # 종목별 핵심 지표
    for sym, data in results['stocks'].items():
        ind = data['indicators']
        stock_name = data.get('name', sym)
        logger.info(
            f"  {sym}({stock_name}): {data['price']['last']:,.0f}원 | "
            f"RSI={ind['rsi']['value']} ({ind['rsi']['signal']}) | "
            f"MACD={ind['macd']['signal']} | "
            f"레짐={data['regime']['state']}"
        )

    # Step 4: 노션 작성
    if args.skip_notion:
        logger.info("--skip-notion 플래그: 노션 작성 스킵")
        logger.info(f"완료. JSON: {json_path}")
        return

    logger.info("KR Notion Writer (병렬 시스템)로 노션 페이지 작성 중...")
    notion_cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), 'kr_notion_writer.py'),
    ]
    try:
        proc = subprocess.run(
            notion_cmd,
            capture_output=True, text=True, timeout=600,
            env={**os.environ},
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if proc.returncode == 0:
            logger.info("한국 시장 Notion 페이지 작성 완료 (병렬 시스템)")
        else:
            logger.warning(
                f"KR Notion Writer 실패 (code={proc.returncode})"
            )
            if proc.stderr:
                logger.warning(f"stderr: {proc.stderr[:500]}")
    except subprocess.TimeoutExpired:
        logger.error("KR Notion Writer 타임아웃 (600초)")
    except FileNotFoundError:
        logger.warning("kr_notion_writer.py 미발견")

    logger.info(f"완료. JSON: {json_path}")


if __name__ == '__main__':
    main()
