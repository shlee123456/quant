# trading_bot/prompts/ - Jinja2 프롬프트 렌더링 모듈

> **상위 문서**: [루트 CLAUDE.md](../../CLAUDE.md)를 먼저 참조하세요.

---

## 목적

`parallel_prompt_builder.py`의 54K 프롬프트 텍스트를 3개 계층으로 분리:
1. **prompt_engine.py**: Jinja2 렌더링 엔진 + 포맷 검증/교정
2. **prompt_data.py**: 데이터 가공 함수 + PromptDataBuilder 클래스
3. **templates/**: `.md.j2` Jinja2 템플릿 파일

## 디렉토리 구조

```
prompts/
├── __init__.py            # PromptEngine, PromptDataBuilder 공개
├── prompt_engine.py       # Jinja2 Environment + 커스텀 필터
├── prompt_data.py         # 데이터 가공 함수 + PromptDataBuilder
├── CLAUDE.md              # 이 파일
└── templates/
    ├── format_rules.md.j2           # 공통 포맷 규칙 (include용)
    ├── footer.md.j2                 # 페이지 하단 푸터
    ├── worker_a.md.j2               # Worker A 프롬프트
    ├── worker_b.md.j2               # Worker B 프롬프트
    ├── worker_c.md.j2               # Worker C 프롬프트 (분기 포함)
    ├── worker_c_sessions.md.j2      # Worker C - 세션 있을 때 구조
    ├── worker_c_no_sessions.md.j2   # Worker C - 세션 없을 때 구조
    └── notion_writer.md.j2          # Notion Writer 프롬프트
```

## 커스텀 Jinja2 필터

| 필터명 | 입력 | 출력 예시 |
|--------|------|----------|
| `format_price` | 1234.5 | `$1,234.50` |
| `format_pct` | 1.234 | `+1.23%` |
| `color_pct` | 2.5 | `<span color="green">+2.50%</span>` |

## 하위 호환성

`parallel_prompt_builder.py`는 기존 API를 유지합니다:
- `build_worker_a_prompt()`, `build_worker_b_prompt()` 등 함수 시그니처 동일
- `notion_writer.py`가 import하는 모든 이름이 re-export됨
- `WORKER_MODELS`, `FOOTER_TEMPLATE`, `_FORMAT_RULES` 상수 유지
