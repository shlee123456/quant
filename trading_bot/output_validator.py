"""Post-validation of LLM output against code-computed facts.

Validates that the LLM's markdown output respects the immutable facts
computed by code (ranking order, short eligibility, direction consistency).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """LLM 출력 검증 결과."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class OutputValidator:
    """Validates LLM markdown output against the fact sheet."""

    def validate_worker_b(
        self, output: str, fact_sheet: Dict[str, Any]
    ) -> ValidationResult:
        """Validate Worker B output.

        Checks:
        1. TOP 3 order matches fact_sheet ranking
        2. Short eligibility: non-eligible stocks not recommended as short
        3. Direction consistency: overall tone vs intelligence signal

        Args:
            output: Worker B의 마크다운 출력
            fact_sheet: FactSheetBuilder.build() 반환값

        Returns:
            ValidationResult with errors and warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not output or not output.strip():
            return ValidationResult(
                is_valid=False,
                errors=["Worker B 출력이 비어있습니다."],
            )

        ranking = fact_sheet.get("ranking")
        if ranking is None:
            warnings.append("fact_sheet에 ranking 데이터가 없어 순위 검증 스킵")
        else:
            # 1. TOP 3 order check
            expected_top3 = ranking.ranked_symbols[:3] if hasattr(ranking, "ranked_symbols") else ranking.get("ranked_symbols", [])[:3]
            extracted_top3 = self._extract_top3_symbols(output)

            if extracted_top3 and expected_top3:
                if extracted_top3 != expected_top3:
                    errors.append(
                        f"TOP 3 순위 불일치: 기대 {expected_top3}, 출력 {extracted_top3}"
                    )

            # 2. Short eligibility check
            short_errors = self._check_short_eligibility(output, fact_sheet)
            errors.extend(short_errors)

        # 3. Direction consistency (warning only)
        market = fact_sheet.get("market")
        if market is not None:
            signal = market.intelligence_signal if hasattr(market, "intelligence_signal") else market.get("intelligence_signal", "neutral")
            tone_warning = self._check_direction_consistency(output, signal)
            if tone_warning:
                warnings.append(tone_warning)

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
        )

    def validate_worker_a(
        self, output: str, fact_sheet: Dict[str, Any]
    ) -> ValidationResult:
        """Validate Worker A output - lighter checks.

        Checks:
        1. All symbols appear in output
        2. Non-empty output

        Args:
            output: Worker A의 마크다운 출력
            fact_sheet: FactSheetBuilder.build() 반환값

        Returns:
            ValidationResult with errors and warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not output or not output.strip():
            return ValidationResult(
                is_valid=False,
                errors=["Worker A 출력이 비어있습니다."],
            )

        market = fact_sheet.get("market")
        if market is not None:
            symbols = market.symbols_list if hasattr(market, "symbols_list") else market.get("symbols_list", [])
            missing = [s for s in symbols if s not in output]
            if missing:
                warnings.append(f"출력에서 누락된 종목: {missing}")

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
        )

    def _extract_top3_symbols(self, output: str) -> List[str]:
        """Extract stock symbols from markdown TOP 3 headers using regex.

        Looks for patterns like:
        - '### 1. AAPL' or '### 2. **MSFT**'
        - '## 1위: AAPL' or '## 2위: **MSFT**'
        - '1위: AAPL', '2위: MSFT', '3위: GOOGL'

        Returns:
            List of up to 3 extracted symbols
        """
        symbols: List[str] = []

        # Pattern 1: numbered header with optional bold
        # e.g., "### 1. AAPL", "### 1. **AAPL**", "## 1위: AAPL"
        patterns = [
            # "## ... 1위: SYMBOL" or "## ... 1위: **SYMBOL**"
            r"#{1,3}\s+.*?[1-3]위[:\s]+\*{0,2}([A-Z][A-Z0-9.]{0,5})\*{0,2}",
            # "### 1. SYMBOL" or "### 1. **SYMBOL**"
            r"#{1,3}\s+[1-3]\.\s+\*{0,2}([A-Z][A-Z0-9.]{0,5})\*{0,2}",
            # Medal emoji patterns
            r"[🥇🥈🥉]\s+\*{0,2}([A-Z][A-Z0-9.]{0,5})\*{0,2}",
            # Broader: numbered with colon
            r"[1-3]위[:\s]+\*{0,2}([A-Z][A-Z0-9.]{0,5})\*{0,2}",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output)
            if len(matches) >= 3:
                symbols = matches[:3]
                break
            elif matches and not symbols:
                symbols = matches[:3]

        # Deduplicate while preserving order
        seen = set()
        unique_symbols: List[str] = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                unique_symbols.append(s)

        return unique_symbols[:3]

    def _check_short_eligibility(
        self, output: str, fact_sheet: Dict[str, Any]
    ) -> List[str]:
        """Check if any non-eligible stocks are recommended for short.

        Args:
            output: LLM 출력 텍스트
            fact_sheet: 팩트 시트

        Returns:
            에러 메시지 리스트
        """
        errors: List[str] = []
        stocks = fact_sheet.get("stocks", [])

        for stock_fact in stocks:
            symbol = stock_fact.symbol if hasattr(stock_fact, "symbol") else stock_fact.get("symbol", "")
            short_eligible = stock_fact.short_eligible if hasattr(stock_fact, "short_eligible") else stock_fact.get("short_eligible", False)

            if short_eligible:
                continue

            # Check if the output recommends shorting this non-eligible stock
            short_patterns = [
                rf"\b{re.escape(symbol)}\b[^.{{0,200}}]*\b(?:숏|short|매도|공매도)\b",
                rf"\b(?:숏|short|매도|공매도)\b[^.{{0,200}}]*\b{re.escape(symbol)}\b",
            ]
            for pattern in short_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    errors.append(
                        f"{symbol}: 숏 적격=False인데 숏 추천 감지"
                    )
                    break

        return errors

    def _check_direction_consistency(
        self, output: str, intelligence_signal: str
    ) -> str:
        """Check if overall output tone is consistent with intelligence signal.

        Returns:
            경고 메시지 또는 빈 문자열
        """
        if intelligence_signal == "neutral":
            return ""

        output_lower = output.lower()

        bullish_keywords = ["강세", "bullish", "상승", "긍정"]
        bearish_keywords = ["약세", "bearish", "하락", "부정"]

        bullish_count = sum(1 for kw in bullish_keywords if kw in output_lower)
        bearish_count = sum(1 for kw in bearish_keywords if kw in output_lower)

        if intelligence_signal == "bullish" and bearish_count > bullish_count * 2:
            return (
                f"방향 불일치 경고: Intelligence는 bullish이나 "
                f"출력은 bearish 키워드 우세 (강세:{bullish_count}, 약세:{bearish_count})"
            )
        elif intelligence_signal == "bearish" and bullish_count > bearish_count * 2:
            return (
                f"방향 불일치 경고: Intelligence는 bearish이나 "
                f"출력은 bullish 키워드 우세 (강세:{bullish_count}, 약세:{bearish_count})"
            )

        return ""
