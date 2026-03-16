#!/usr/bin/env python3
"""동일 JSON 데이터로 프롬프트 빌더를 N회 실행하여 결정론적 출력을 검증.

코드 기반 사실(FactSheet, TOP 3 순위, 수치)이 매 실행마다 동일한지 확인합니다.
LLM은 호출하지 않습니다 — 프롬프트 입력의 일관성만 검증합니다.

Usage:
    python scripts/verify_determinism.py --runs 3
    python scripts/verify_determinism.py --runs 5 --json-path data/market_analysis/2026-03-16.json
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.fact_sheet import FactSheetBuilder
from trading_bot.parallel_prompt_builder import build_worker_b_prompt
from trading_bot.prompts.prompt_data import PromptDataBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class DeterminismVerifier:
    """프롬프트 빌더의 결정론적 출력을 검증합니다."""

    def find_latest_json(self) -> Optional[str]:
        """data/market_analysis/에서 최신 JSON 파일을 찾습니다."""
        analysis_dir = PROJECT_ROOT / "data" / "market_analysis"
        json_files = sorted(analysis_dir.glob("*.json"), reverse=True)
        return str(json_files[0]) if json_files else None

    def run_comparison(self, json_path: str, n_runs: int = 3) -> Dict[str, Any]:
        """N회 프롬프트 빌더를 실행하여 결과를 비교합니다.

        Returns:
            {
                'json_path': str,
                'n_runs': int,
                'top3_consistent': bool,
                'prompt_hashes_consistent': bool,
                'fact_sheet_consistent': bool,
                'runs': [
                    {
                        'run': int,
                        'top3': List[str],
                        'prompt_b_hash': str,
                        'fact_sheet_hash': str,
                    }
                ],
                'summary': str,
            }
        """
        # Load JSON data
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        market_data = {
            k: v for k, v in data.items()
            if k not in ('news', 'fear_greed_index', 'macro', 'events',
                         'fundamentals', 'intelligence')
        }
        news_data = data.get('news', {})
        fear_greed_data = data.get('fear_greed_index', {})
        intelligence_data = data.get('intelligence')
        today = Path(json_path).stem  # e.g., "2026-03-16"

        runs = []
        for i in range(n_runs):
            # Build fact sheet
            builder = PromptDataBuilder()
            try:
                fact_sheet = builder.build_fact_sheet(
                    market_data=market_data,
                    today=today,
                    intelligence_data=intelligence_data,
                    fear_greed_data=fear_greed_data,
                )
                fs_builder = FactSheetBuilder()
                fact_sheet_block = fs_builder.to_prompt_block(fact_sheet)
            except Exception as e:
                fact_sheet_block = f"ERROR: {e}"

            # Build worker B prompt (includes TOP 3)
            prompt_b, top3_symbols = build_worker_b_prompt(
                market_data, news_data, fear_greed_data, today,
                intelligence_data=intelligence_data,
            )

            runs.append({
                'run': i + 1,
                'top3': top3_symbols,
                'prompt_b_hash': hashlib.sha256(prompt_b.encode()).hexdigest()[:16],
                'fact_sheet_hash': hashlib.sha256(fact_sheet_block.encode()).hexdigest()[:16],
                'prompt_b_length': len(prompt_b),
            })

        # Compare results
        all_top3 = [r['top3'] for r in runs]
        all_prompt_hashes = [r['prompt_b_hash'] for r in runs]
        all_fs_hashes = [r['fact_sheet_hash'] for r in runs]

        top3_consistent = len(set(str(t) for t in all_top3)) == 1
        prompt_consistent = len(set(all_prompt_hashes)) == 1
        fs_consistent = len(set(all_fs_hashes)) == 1

        # Build summary
        lines = []
        lines.append(
            f"{'PASS' if top3_consistent else 'FAIL'} TOP 3 순서: "
            f"{all_top3[0]} ({'동일' if top3_consistent else '불일치'})"
        )
        lines.append(
            f"{'PASS' if prompt_consistent else 'FAIL'} 프롬프트 해시: "
            f"{all_prompt_hashes[0]} ({'동일' if prompt_consistent else '불일치'})"
        )
        lines.append(
            f"{'PASS' if fs_consistent else 'FAIL'} 팩트시트 해시: "
            f"{all_fs_hashes[0]} ({'동일' if fs_consistent else '불일치'})"
        )

        if top3_consistent and prompt_consistent and fs_consistent:
            lines.append(
                "-> 결론: 코드 기반 사실은 100% 결정론적. "
                "LLM 해석만 차이 발생 가능."
            )
        else:
            lines.append("-> 경고: 비결정적 요소 발견! 코드 검토 필요.")

        return {
            'json_path': json_path,
            'n_runs': n_runs,
            'top3_consistent': top3_consistent,
            'prompt_hashes_consistent': prompt_consistent,
            'fact_sheet_consistent': fs_consistent,
            'runs': runs,
            'summary': '\n'.join(lines),
        }


def main():
    parser = argparse.ArgumentParser(
        description="프롬프트 빌더 결정론적 출력 검증"
    )
    parser.add_argument(
        '--runs', type=int, default=3, help='실행 횟수 (기본: 3)'
    )
    parser.add_argument(
        '--json-path', type=str, default=None,
        help='시장 분석 JSON 경로'
    )
    args = parser.parse_args()

    verifier = DeterminismVerifier()

    json_path = args.json_path or verifier.find_latest_json()
    if not json_path:
        logger.error("JSON 파일을 찾을 수 없습니다.")
        sys.exit(1)

    logger.info(f"검증 시작: {json_path} ({args.runs}회 실행)")
    result = verifier.run_comparison(json_path, args.runs)

    print("\n" + "=" * 50)
    print("비결정성 검증 결과")
    print("=" * 50)
    for run in result['runs']:
        print(
            f"  Run {run['run']}: TOP3={run['top3']}, "
            f"hash={run['prompt_b_hash']}, len={run['prompt_b_length']}"
        )
    print()
    print(result['summary'])
    print("=" * 50)

    sys.exit(
        0 if result['top3_consistent'] and result['prompt_hashes_consistent']
        else 1
    )


if __name__ == '__main__':
    main()
