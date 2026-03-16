"""
Jinja2 기반 프롬프트 렌더링 엔진.

템플릿 파일을 로드하고 컨텍스트 딕셔너리를 주입하여
최종 프롬프트 문자열을 생성합니다.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jinja2

logger = logging.getLogger(__name__)

# 기본 템플릿 디렉토리 (이 파일 기준 상대 경로)
_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptEngine:
    """Jinja2 렌더링 엔진.

    Args:
        templates_dir: 템플릿 파일 디렉토리 경로.
            ``None`` 이면 ``prompts/templates/`` 를 사용합니다.
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        tdir = Path(templates_dir) if templates_dir else _DEFAULT_TEMPLATES_DIR
        self.templates_dir = tdir

        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(tdir)),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
            keep_trailing_newline=True,
        )

        # 커스텀 필터 등록
        self.env.filters["format_price"] = self._filter_format_price
        self.env.filters["format_pct"] = self._filter_format_pct
        self.env.filters["color_pct"] = self._filter_color_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # 템플릿별 필수 컨텍스트 변수
    _REQUIRED_CONTEXT: Dict[str, List[str]] = {
        "worker_a.md.j2": ["today", "json_str", "section_spec"],
        "worker_b.md.j2": ["today", "stocks_json"],
        "worker_c.md.j2": ["today", "has_sessions", "stocks_json"],
        "notion_writer.md.j2": ["assembled_content", "today", "parent_page_id"],
    }

    def render(self, template_name: str, context: dict) -> str:
        """템플릿을 렌더링합니다.

        Args:
            template_name: 템플릿 파일명 (예: ``worker_a.md.j2``)
            context: 템플릿에 주입할 변수 딕셔너리

        Returns:
            렌더링된 문자열

        Raises:
            ValueError: 필수 컨텍스트 변수가 누락된 경우
        """
        required = self._REQUIRED_CONTEXT.get(template_name, [])
        missing = [k for k in required if k not in context]
        if missing:
            raise ValueError(
                f"템플릿 '{template_name}' 필수 변수 누락: {missing}"
            )
        template = self.env.get_template(template_name)
        return template.render(**context)

    # ------------------------------------------------------------------
    # Format validation / auto-correction (assemble 단계에서 사용)
    # ------------------------------------------------------------------

    @staticmethod
    def validate_format_rules(content: str) -> List[str]:
        """Notion Enhanced Markdown 포맷 규칙 위반을 감지합니다.

        Returns:
            발견된 위반 사항 리스트 (빈 리스트면 문제 없음)
        """
        warnings: List[str] = []

        callout_opens = len(re.findall(r"^::: callout", content, re.MULTILINE))
        callout_closes = content.count("\n:::\n") + (
            1 if content.rstrip().endswith(":::") else 0
        )
        if callout_opens != callout_closes:
            warnings.append(
                f"callout 블록 불일치: 열기 {callout_opens}개, 닫기 {callout_closes}개"
            )

        table_opens = len(re.findall(r"<table\b", content))
        table_closes = content.count("</table>")
        if table_opens != table_closes:
            warnings.append(
                f"table 태그 불일치: <table> {table_opens}개, </table> {table_closes}개"
            )

        bad_colors = re.findall(r'\{color=([^"}\s][^}]*)\}', content)
        if bad_colors:
            warnings.append(f"color 속성 따옴표 누락: {bad_colors[:3]}")

        empty_rows = len(re.findall(r"<tr[^>]*>\s*</tr>", content))
        if empty_rows:
            warnings.append(f"빈 테이블 행 {empty_rows}개 감지")

        code_blocks = len(re.findall(r"```\w+", content))
        if code_blocks:
            warnings.append(
                f"코드블록 {code_blocks}개 감지 (Notion Enhanced MD에서 비권장)"
            )

        return warnings

    @staticmethod
    def auto_correct_format(content: str) -> Tuple[str, List[str]]:
        """LLM 이 자주 범하는 포맷 실수를 자동 교정합니다.

        Returns:
            (교정된 콘텐츠, 교정 내역 리스트)
        """
        corrections: List[str] = []
        result = content

        # span color 작은따옴표 → 큰따옴표
        pattern = r"<span color='([^']+)'>"
        if re.search(pattern, result):
            result = re.sub(pattern, r'<span color="\1">', result)
            corrections.append("span color 속성의 작은따옴표를 큰따옴표로 교정")

        # callout 닫기 태그 누락 보완
        callout_opens = len(re.findall(r"^::: callout", result, re.MULTILINE))
        callout_closes = result.count("\n:::\n") + (
            1 if result.rstrip().endswith(":::") else 0
        )
        if callout_opens > callout_closes:
            missing = callout_opens - callout_closes
            result = result.rstrip() + "\n" + ":::\n" * missing
            corrections.append(f"callout 닫기 태그 {missing}개 보완")

        # 이중 구분선 정리
        while "\n---\n---" in result:
            result = result.replace("\n---\n---", "\n---")
            if "이중 구분선 정리" not in corrections:
                corrections.append("이중 구분선 정리")

        return result, corrections

    # ------------------------------------------------------------------
    # Custom Jinja2 filters
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_format_price(value: object) -> str:
        """숫자를 ``$1,234.56`` 형태로 포맷합니다."""
        if value is None:
            return "N/A"
        try:
            v = float(value)
            return f"${v:,.2f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _filter_format_pct(value: object, decimals: int = 2) -> str:
        """숫자를 ``+1.23%`` / ``-0.45%`` 형태로 포맷합니다."""
        if value is None:
            return "N/A"
        try:
            v = float(value)
            sign = "+" if v > 0 else ""
            return f"{sign}{v:.{decimals}f}%"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _filter_color_pct(value: object, decimals: int = 2) -> str:
        """퍼센트 변화를 Notion span color 로 래핑합니다.

        양수 → ``<span color="green">+X.XX%</span>``
        음수 → ``<span color="red">-X.XX%</span>``
        """
        if value is None:
            return "N/A"
        try:
            v = float(value)
            sign = "+" if v > 0 else ""
            color = "green" if v >= 0 else "red"
            return f'<span color="{color}">{sign}{v:.{decimals}f}%</span>'
        except (TypeError, ValueError):
            return str(value)
