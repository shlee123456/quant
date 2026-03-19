"""
Notion API Writer — Python notion-client로 직접 Notion 페이지를 생성합니다.

Claude CLI의 MCP 도구 의존성을 제거하고, Notion Enhanced Markdown을
Notion API 블록으로 변환하여 페이지를 생성합니다.

Usage:
    writer = NotionPageWriter(token="ntn_xxx", parent_page_id="xxx")
    url = writer.create_report("📊 시장 분석 | 2026-03-19", content, month_name="2026년 3월")
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from notion_client import Client

logger = logging.getLogger(__name__)

# Notion API 블록 제한
MAX_BLOCKS_PER_REQUEST = 100
MAX_RICH_TEXT_LENGTH = 2000

# Notion 색상 매핑 (enhanced markdown → API)
_BG_COLOR_MAP = {
    "blue_bg": "blue_background",
    "green_bg": "green_background",
    "red_bg": "red_background",
    "yellow_bg": "yellow_background",
    "orange_bg": "orange_background",
    "gray_bg": "gray_background",
    "purple_bg": "purple_background",
    "pink_bg": "pink_background",
    "brown_bg": "brown_background",
}

_INLINE_COLOR_MAP = {
    "green": "green",
    "red": "red",
    "blue": "blue",
    "orange": "orange",
    "yellow": "yellow",
    "gray": "gray",
    "purple": "purple",
    "pink": "pink",
    "brown": "brown",
}


# ──────────────────────────────────────────────
#  Rich Text 파싱 (인라인 마크다운 → Notion rich_text)
# ──────────────────────────────────────────────

def _parse_rich_text(text: str) -> List[Dict[str, Any]]:
    """마크다운 인라인 서식을 Notion rich_text 배열로 변환합니다."""
    if not text or not text.strip():
        return [{"type": "text", "text": {"content": text or ""}}]

    # 이스케이프된 파이프 복원
    text = text.replace("\\|", "|")

    segments: List[Dict[str, Any]] = []
    # 패턴: <span color="...">, **bold**, *italic*, `code`, [text](url)
    pattern = re.compile(
        r'<span\s+color="([^"]+)">(.*?)</span>'  # colored span
        r'|(\*\*)(.*?)\3'  # bold
        r'|(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)'  # italic
        r'|`([^`]+)`'  # code
        r'|\[([^\]]+)\]\(([^)]+)\)'  # link
    )

    pos = 0
    for m in pattern.finditer(text):
        # 매치 전 텍스트
        if m.start() > pos:
            _append_text(segments, text[pos:m.start()])

        if m.group(1) is not None:  # <span color="...">
            color = _INLINE_COLOR_MAP.get(m.group(1), m.group(1))
            _append_text(segments, m.group(2), color=color)
        elif m.group(4) is not None:  # **bold**
            _append_text(segments, m.group(4), bold=True)
        elif m.group(5) is not None:  # *italic*
            _append_text(segments, m.group(5), italic=True)
        elif m.group(6) is not None:  # `code`
            _append_text(segments, m.group(6), code=True)
        elif m.group(7) is not None:  # [text](url)
            _append_text(segments, m.group(7), link=m.group(8))

        pos = m.end()

    # 나머지 텍스트
    if pos < len(text):
        _append_text(segments, text[pos:])

    return segments if segments else [{"type": "text", "text": {"content": ""}}]


def _append_text(
    segments: list,
    content: str,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    color: str = "default",
    link: Optional[str] = None,
):
    """rich_text 세그먼트를 추가합니다."""
    if not content:
        return
    # 2000자 제한 분할
    for i in range(0, len(content), MAX_RICH_TEXT_LENGTH):
        chunk = content[i:i + MAX_RICH_TEXT_LENGTH]
        seg: Dict[str, Any] = {
            "type": "text",
            "text": {"content": chunk},
            "annotations": {
                "bold": bold,
                "italic": italic,
                "code": code,
                "color": color,
            },
        }
        if link:
            seg["text"]["link"] = {"url": link}
        segments.append(seg)


# ──────────────────────────────────────────────
#  블록 파싱 (Notion Enhanced Markdown → Notion blocks)
# ──────────────────────────────────────────────

def parse_markdown_to_blocks(content: str) -> List[Dict[str, Any]]:
    """Notion Enhanced Markdown을 Notion API 블록 배열로 변환합니다."""
    lines = content.split("\n")
    blocks: List[Dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 빈 줄 건너뛰기
        if not stripped:
            i += 1
            continue

        # table_of_contents
        if stripped == "<table_of_contents/>":
            blocks.append({"type": "table_of_contents", "table_of_contents": {"color": "default"}})
            i += 1
            continue

        # 수평선
        if stripped == "---" or stripped == "***":
            blocks.append({"type": "divider", "divider": {}})
            i += 1
            continue

        # callout ::: callout {icon="..." color="..."}
        if stripped.startswith("::: callout"):
            block, i = _parse_callout(lines, i)
            blocks.append(block)
            continue

        # table <table ...>
        if stripped.startswith("<table"):
            block, i = _parse_table(lines, i)
            if block:
                blocks.append(block)
            continue

        # details/summary → toggle
        if stripped.startswith("<details>"):
            block, i = _parse_toggle(lines, i)
            if block:
                blocks.append(block)
            continue

        # heading # {color="..."}
        heading_match = re.match(r'^(#{1,3})\s+(.+?)(?:\s*\{color="([^"]+)"\})?\s*$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            color = _BG_COLOR_MAP.get(heading_match.group(3), heading_match.group(3)) if heading_match.group(3) else "default"
            htype = f"heading_{min(level, 3)}"
            blocks.append({
                "type": htype,
                htype: {
                    "rich_text": _parse_rich_text(text),
                    "color": color or "default",
                    "is_toggleable": False,
                },
            })
            i += 1
            continue

        # blockquote >
        if stripped.startswith("> "):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:])
                i += 1
            blocks.append({
                "type": "quote",
                "quote": {"rich_text": _parse_rich_text("\n".join(quote_lines)), "color": "default"},
            })
            continue

        # code block ```
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                    "language": lang or "plain text",
                },
            })
            continue

        # numbered list
        num_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_match:
            blocks.append({
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _parse_rich_text(num_match.group(2)), "color": "default"},
            })
            i += 1
            continue

        # bulleted list
        if stripped.startswith("- ") or stripped.startswith("• "):
            text = stripped[2:]
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _parse_rich_text(text), "color": "default"},
            })
            i += 1
            continue

        # 일반 텍스트 (paragraph)
        # HTML 태그(닫는 태그 등) 건너뛰기
        if stripped.startswith("</") or stripped == ":::":
            i += 1
            continue

        blocks.append({
            "type": "paragraph",
            "paragraph": {"rich_text": _parse_rich_text(stripped), "color": "default"},
        })
        i += 1

    return blocks


def _parse_callout(lines: List[str], start: int) -> Tuple[Dict, int]:
    """callout 블록을 파싱합니다."""
    header = lines[start].strip()
    # ::: callout {icon="📅" color="gray_bg"}
    icon_match = re.search(r'icon="([^"]*)"', header)
    color_match = re.search(r'color="([^"]*)"', header)

    icon = icon_match.group(1) if icon_match else "💡"
    color = _BG_COLOR_MAP.get(color_match.group(1), "default") if color_match else "default"

    content_lines = []
    i = start + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == ":::":
            i += 1
            break
        content_lines.append(stripped.lstrip("\t"))
        i += 1

    text = "\n".join(content_lines)

    block = {
        "type": "callout",
        "callout": {
            "rich_text": _parse_rich_text(text),
            "icon": {"type": "emoji", "emoji": icon},
            "color": color,
        },
    }
    return block, i


def _parse_table(lines: List[str], start: int) -> Tuple[Optional[Dict], int]:
    """<table> 블록을 파싱합니다."""
    header_line = lines[start].strip()
    has_header = "header-row" in header_line
    has_col_header = "header-column" in header_line

    rows: List[List[str]] = []
    row_colors: List[Optional[str]] = []
    i = start + 1

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("</table"):
            i += 1
            break

        # <tr> 또는 <tr color="...">
        if stripped.startswith("<tr"):
            color_match = re.search(r'color="([^"]*)"', stripped)
            row_color = color_match.group(1) if color_match else None
            cells = []
            i += 1
            while i < len(lines):
                cell_line = lines[i].strip()
                if cell_line.startswith("</tr"):
                    i += 1
                    break
                # <td>content</td> 또는 <td color="...">content</td>
                td_match = re.match(r'<td(?:\s+[^>]*)?>(.+?)</td>', cell_line)
                if td_match:
                    cells.append(td_match.group(1))
                elif cell_line.startswith("<td"):
                    # 빈 셀 등
                    cells.append("")
                i += 1
            rows.append(cells)
            row_colors.append(row_color)
        else:
            i += 1

    if not rows:
        return None, i

    # 열 수 통일
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    # table 블록 생성
    table_block = {
        "type": "table",
        "table": {
            "table_width": max_cols,
            "has_column_header": has_col_header,
            "has_row_header": has_header,
            "children": [],
        },
    }

    for row in rows:
        table_row = {
            "type": "table_row",
            "table_row": {
                "cells": [_parse_rich_text(cell) for cell in row],
            },
        }
        table_block["table"]["children"].append(table_row)

    return table_block, i


def _parse_toggle(lines: List[str], start: int) -> Tuple[Optional[Dict], int]:
    """<details><summary> → toggle 블록으로 변환합니다."""
    i = start + 1  # skip <details>
    summary_text = ""
    content_lines = []

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("<summary>"):
            summary_match = re.match(r'<summary>(.*?)</summary>', stripped)
            if summary_match:
                summary_text = summary_match.group(1)
            i += 1
            continue
        if stripped == "</details>":
            i += 1
            break
        content_lines.append(lines[i])
        i += 1

    # toggle 내부 콘텐츠를 블록으로 변환
    inner_blocks = parse_markdown_to_blocks("\n".join(content_lines))

    block = {
        "type": "toggle",
        "toggle": {
            "rich_text": _parse_rich_text(summary_text),
            "color": "default",
            "children": inner_blocks[:MAX_BLOCKS_PER_REQUEST],
        },
    }
    return block, i


# ──────────────────────────────────────────────
#  Notion API Writer
# ──────────────────────────────────────────────

class NotionPageWriter:
    """Notion API를 사용하여 시장 분석 페이지를 생성합니다."""

    def __init__(self, token: Optional[str] = None, parent_page_id: Optional[str] = None):
        self.token = token or os.getenv("NOTION_API_TOKEN", "")
        if not self.token:
            raise ValueError("NOTION_API_TOKEN이 설정되지 않았습니다.")
        self.parent_page_id = parent_page_id or os.getenv(
            "NOTION_MARKET_ANALYSIS_PAGE_ID", "30dd62f0-dffd-80a6-b624-e5a061ed26a9"
        )
        self.client = Client(auth=self.token)

    def find_or_create_month_folder(self, month_name: str) -> str:
        """월별 폴더 페이지를 찾거나 생성합니다.

        Args:
            month_name: 예) "2026년 3월" 또는 "26-03월"

        Returns:
            월별 폴더 페이지 ID
        """
        # 1. 검색으로 찾기
        try:
            results = self.client.search(
                query=month_name,
                filter={"property": "object", "value": "page"},
                page_size=10,
            )
            for page in results.get("results", []):
                title = _extract_page_title(page)
                if month_name in title:
                    page_id = page["id"]
                    logger.info(f"월별 폴더 발견: {title} ({page_id})")
                    return page_id
        except Exception as e:
            logger.warning(f"월별 폴더 검색 실패: {e}")

        # 2. 없으면 생성
        logger.info(f"월별 폴더 생성: {month_name}")
        new_page = self.client.pages.create(
            parent={"page_id": self.parent_page_id},
            properties={"title": [{"type": "text", "text": {"content": month_name}}]},
        )
        page_id = new_page["id"]
        logger.info(f"월별 폴더 생성 완료: {page_id}")
        return page_id

    def create_report(
        self,
        title: str,
        content: str,
        month_name: str,
    ) -> Optional[str]:
        """시장 분석 리포트 페이지를 생성합니다.

        Args:
            title: 페이지 제목 (예: "📊 시장 분석 | 2026-03-19")
            content: Notion Enhanced Markdown 콘텐츠
            month_name: 월별 폴더 이름 (예: "26-03월")

        Returns:
            생성된 페이지 URL 또는 None
        """
        # 1. 월별 폴더 찾기/생성
        folder_id = self.find_or_create_month_folder(month_name)

        # 2. 콘텐츠 → 블록 변환
        blocks = parse_markdown_to_blocks(content)
        logger.info(f"블록 변환 완료: {len(blocks)}개 블록")

        # 3. 첫 100개 블록으로 페이지 생성
        first_batch = blocks[:MAX_BLOCKS_PER_REQUEST]
        remaining = blocks[MAX_BLOCKS_PER_REQUEST:]

        try:
            page = self.client.pages.create(
                parent={"page_id": folder_id},
                properties={"title": [{"type": "text", "text": {"content": title}}]},
                children=first_batch,
            )
        except Exception as e:
            logger.error(f"페이지 생성 실패: {e}")
            return None

        page_id = page["id"]
        page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")
        logger.info(f"페이지 생성: {title} → {page_url}")

        # 4. 나머지 블록 추가 (100개씩 배치)
        for batch_idx in range(0, len(remaining), MAX_BLOCKS_PER_REQUEST):
            batch = remaining[batch_idx:batch_idx + MAX_BLOCKS_PER_REQUEST]
            try:
                self.client.blocks.children.append(block_id=page_id, children=batch)
                logger.info(f"  블록 추가: {len(batch)}개 (배치 {batch_idx // MAX_BLOCKS_PER_REQUEST + 2})")
            except Exception as e:
                logger.error(f"  블록 추가 실패 (배치 {batch_idx // MAX_BLOCKS_PER_REQUEST + 2}): {e}")
                # Rate limit 대응
                if "rate_limited" in str(e).lower():
                    time.sleep(1)
                    try:
                        self.client.blocks.children.append(block_id=page_id, children=batch)
                    except Exception as e2:
                        logger.error(f"  재시도 실패: {e2}")

        return page_url


def _extract_page_title(page: dict) -> str:
    """Notion 페이지 객체에서 제목을 추출합니다."""
    props = page.get("properties", {})
    title_prop = props.get("title", {})
    if isinstance(title_prop, dict):
        title_arr = title_prop.get("title", [])
    else:
        title_arr = []
    return "".join(t.get("plain_text", "") for t in title_arr)
