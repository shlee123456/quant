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
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_bot.market_analyzer import MarketAnalyzer
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


def _run_legacy_notion(json_path: str, session_reports_dir: str = None):
    """레거시 단일 프롬프트 Notion 작성 (폴백용)."""
    try:
        from trading_bot.market_analysis_prompt import build_analysis_prompt
        prompt = build_analysis_prompt(json_path, session_reports_dir)
        proc = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--allowedTools", "mcp__claude_ai_Notion__*,Read,WebSearch"],
            input=prompt, capture_output=True, text=True, timeout=300,
            env={**os.environ},
        )
        if proc.returncode == 0:
            logger.info("레거시 Notion 작성 완료")
        else:
            logger.error(f"레거시 Notion 작성 실패 (code={proc.returncode})")
    except Exception as e:
        logger.error(f"레거시 Notion 작성 에러: {e}")


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

    # Step 2.5: 매크로 시장 환경 분석 (yfinance 기반)
    try:
        macro_result = analyzer.analyze_macro()
        if macro_result:
            results['macro'] = macro_result
            logger.info(
                f"매크로 분석 완료: "
                f"지수 {len(macro_result.get('indices', {}))}개, "
                f"섹터 {len(macro_result.get('sectors', {}))}개"
            )
        else:
            logger.info("매크로 분석 건너뜀 (yfinance 미설치 또는 데이터 없음)")
    except Exception as e:
        logger.warning(f"매크로 분석 실패 (개별 종목 분석은 정상): {e}")

    # Step 2.7: 5-Layer Market Intelligence
    try:
        from trading_bot.market_intelligence import MarketIntelligence
        mi = MarketIntelligence()
        intel_report = mi.analyze(
            stock_symbols=symbols,
            stocks_data=results.get('stocks', {}),
            news_data=results.get('news'),
            fear_greed_data=results.get('fear_greed_index'),
        )
        results['intelligence'] = intel_report
        logger.info(
            f"5-Layer Intelligence: "
            f"score={intel_report['overall']['score']}, "
            f"signal={intel_report['overall']['signal']}"
        )
    except ImportError:
        logger.info("MarketIntelligence not available - skipping")
    except Exception as e:
        logger.warning(f"Market Intelligence failed (analysis continues): {e}")

    # Step 2.8: 시그널 성과 추적
    tracker = None
    if os.getenv('SIGNAL_TRACKING_ENABLED', 'true').lower() == 'true':
        try:
            from trading_bot.signal_tracker import SignalTracker
            today = datetime.now().strftime('%Y-%m-%d') if 'today' not in dir() else today
            tracker = SignalTracker()
            count = tracker.log_daily_signals(results)
            logger.info(f"시그널 기록: {count}건")
            updated = tracker.update_pending_outcomes()
            logger.info(f"과거 시그널 성과 측정: {updated}건 업데이트")
            tracker.calculate_accuracy_stats(
                results.get('date', datetime.now().strftime('%Y-%m-%d'))
            )
        except Exception as e:
            logger.warning(f"시그널 추적 실패 (분석 계속): {e}")

    # Step 2.9: 멀티데이 트렌드 분석
    try:
        from trading_bot.trend_reader import TrendReader
        reader = TrendReader(analysis_dir=args.output_dir)
        trend_data = reader.analyze_trends(n_days=5)
        results['trend'] = trend_data
        logger.info(f"트렌드 분석 완료: {trend_data['period']['start']}~{trend_data['period']['end']}")
    except Exception as e:
        logger.warning(f"트렌드 분석 실패 (분석 계속): {e}")

    # Step 2.10: 시그널 성적표
    if tracker is not None:
        try:
            scorecard = tracker.generate_scorecard(
                results.get('date', datetime.now().strftime('%Y-%m-%d'))
            )
            results['scorecard'] = scorecard
            coverage = scorecard.get('data_coverage', {})
            logger.info(f"성적표: {coverage.get('with_outcomes', 0)}/{coverage.get('total_signals', 0)}건 채점완료, sufficient={coverage.get('sufficient', False)}")
        except Exception as e:
            logger.warning(f"성적표 생성 실패 (분석 계속): {e}")

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

    logger.info("Notion Writer (병렬 시스템)로 노션 페이지 작성 중...")
    notion_cmd = [
        sys.executable, os.path.join(os.path.dirname(__file__), 'notion_writer.py'),
    ]
    try:
        proc = subprocess.run(
            notion_cmd,
            capture_output=True, text=True, timeout=600,
            env={**os.environ},
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if proc.returncode == 0:
            logger.info("Notion 페이지 작성 완료 (병렬 시스템)")
        else:
            logger.warning(f"Notion Writer 실패 (code={proc.returncode}), 레거시 폴백 시도...")
            logger.warning(f"stderr: {proc.stderr[:500] if proc.stderr else 'N/A'}")
            # Legacy fallback
            _run_legacy_notion(json_path, session_reports_dir=None)
    except subprocess.TimeoutExpired:
        logger.error("Notion Writer 타임아웃 (600초)")
        _run_legacy_notion(json_path, session_reports_dir=None)
    except FileNotFoundError:
        logger.warning("notion_writer.py 미발견, 레거시 폴백...")
        _run_legacy_notion(json_path, session_reports_dir=None)

    logger.info(f"완료. JSON: {json_path}")


if __name__ == '__main__':
    main()
