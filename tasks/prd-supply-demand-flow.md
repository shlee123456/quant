# PRD: Supply/Demand Flow Data Integration (수급 데이터 통합) v2

> **v2 변경**: 10회 코드 검증 결과 반영. C1~C4 크리티컬 이슈 및 I1~I7 중요 이슈 해결.

## Introduction

5-Layer Market Intelligence 엔진에 수급(flow) 데이터를 추가하여 "누가 사고파는가"를 정량화합니다.
현재 시스템은 가격 파생 지표(RSI, MACD)와 거시 데이터(금리, 크레딧)만 사용하며,
실제 시장 참여자의 포지셔닝 데이터가 없어 기술적 시그널의 확인/부정이 불가능합니다.

US 시장은 CBOE Put/Call Ratio, KR 시장은 외국인/기관 순매수 + 시장 전체 공매도 비율을 수집하여
기존 레이어에 서브메트릭으로 통합합니다.

## Goals

- **[선행] KR SentimentLayer 버그 수정** — KR이 US SentimentLayer를 잘못 사용하는 문제 해결
- US Layer 5(Sentiment)에 CBOE Put/Call Ratio 기반 options_flow 서브메트릭 추가 (±100 범위)
- KR Layer 2(Market Structure)에 외국인/기관 순매수 기반 investor_flow 서브메트릭 추가 (±100 범위)
- KR investor_flow에 시장 전체 공매도 비율을 보조 시그널로 통합
- 일일 시장 분석 JSON에 수급 데이터 섹션 자동 포함
- Notion 리포트 프롬프트에 수급 분석 반영 (US: 데이터 블록 방식, KR: 인라인 f-string 방식)
- 모든 변경은 graceful degradation (데이터 없으면 NaN → weighted_composite 자동 스킵)

## User Stories

### FIX-001: KR SentimentLayer 버그 수정
**Description:** 시스템으로서, KR 마켓이 KRSentimentLayer를 사용하도록 수정하여 VKOSPI/한글뉴스/원달러 기반 분석이 정상 동작하게 한다.

**Acceptance Criteria:**
- [ ] `__init__.py:180`에서 `SentimentLayer()` → `KRSentimentLayer()` 변경
- [ ] `from .kr_layer5_sentiment import KRSentimentLayer` import 추가
- [ ] 기존 전체 테스트 통과 (`pytest tests/test_market_intelligence/ -v`)

### US-001: CBOE Put/Call Ratio 데이터 수집기
**Description:** 개발자로서, CBOE에서 일별 Put/Call Ratio CSV를 다운로드하여 파싱하고 싶다.

**Acceptance Criteria:**
- [ ] `trading_bot/market_intelligence/cboe_fetcher.py` 파일 생성
- [ ] `CBOEFetcher` 클래스: bok_fetcher.py 패턴 (import guard, is_available, try/except)
- [ ] `fetch_equity_pcr(lookback_days=60)` -> Optional[pd.DataFrame]
- [ ] `get_latest()` -> Optional[Dict] (equity_pcr, pcr_5d_avg, pcr_20d_avg, date)
- [ ] Primary URL 실패 시 fallback URL 시도, 둘 다 실패 시 None
- [ ] 인스턴스 레벨 캐싱 (`_cached_df`)
- [ ] `tests/test_market_intelligence/test_cboe_fetcher.py` 작성 및 통과

### US-002: Layer 5 Sentiment에 options_flow 서브메트릭 추가
**Description:** 시스템으로서, PCR을 역발상 스코어(±100)로 변환하여 Layer 5 합성 점수에 반영한다.

**Acceptance Criteria:**
- [ ] SUB_WEIGHTS 재분배: fear_greed=0.25, vix=0.15, news=0.15, smart_money=0.25, options_flow=0.20 (합계 1.0)
- [ ] `_calc_options_flow()`: PCR>=1.5→+100, >=1.2→+60, 1.0~1.2→+20, 0.7~1.0→0, 0.5~0.7→-40, <0.5→-100
- [ ] 5일 MA 보정: pcr_5d > pcr_20d×1.02 → +10, < ×0.98 → -10, 그 외 0
- [ ] pcr_data=None → `(NaN, {'error': ...})` (weighted_composite 자동 스킵)
- [ ] 최종 점수 `max(-100, min(100, score))` 클램핑
- [ ] **기존 테스트 업데이트**: test_weights_sum_to_one, test_metrics_contains_all_sub_scores
- [ ] KR은 KRSentimentLayer 사용이므로 영향 없음 확인

### US-003: MarketIntelligence 오케스트레이터에 PCR 파이프라인 연결
**Description:** 시스템으로서, PCR 데이터가 MarketAnalyzer → MI → Layer 5까지 전달되도록 한다.

**Acceptance Criteria:**
- [ ] `__init__.py` analyze()에 `pcr_data` 파라미터 추가, context에 전달
- [ ] `market_analyzer.py`에 CBOE 수집 블록 추가 (`CBOE_PCR_ENABLED` 환경변수 체크)
- [ ] `scripts/run_market_analysis.py`에서 pcr_data 전달
- [ ] `scheduler/session_manager.py` MI 호출부에서 pcr_data 전달
- [ ] 수집 실패 시 경고 로그, 분석 계속

### US-004: US 프롬프트에 PCR 데이터 블록 추가
**Description:** 리포트 소비자로서, Notion 리포트에서 PCR 데이터와 옵션 플로우 해석을 확인한다.

**Acceptance Criteria:**
- [ ] `prompt_data.py`에서 PCR 데이터 블록 구성 (pcr_block, pcr_summary)
- [ ] `worker_a.md.j2`에 `{% if pcr_block %}` 조건부 삽입 (테이블 행 아님 — 데이터 블록)
- [ ] `worker_b.md.j2` Section 4 뒤에 `{% if pcr_summary %}` 조건부 삽입
- [ ] PCR 데이터 없을 때 블록 자동 생략

### KR-001: pykrx 기반 KR 투자자 수급 수집기
**Description:** 개발자로서, KRX에서 외국인/기관/개인 순매수 데이터를 pykrx로 수집한다.

**Acceptance Criteria:**
- [ ] `requirements.txt`에 `pykrx>=1.0.0` 추가
- [ ] `kr_flow_fetcher.py` 생성: KRFlowFetcher (bok_fetcher.py 패턴, `_has_pykrx` guard)
- [ ] `fetch_market_flow(days=20)`: pykrx YYYYMMDD 형식, KOSPI 투자자별 매매
- [ ] `get_latest_summary()`: foreign_net_today/5d, institutional_net_today/5d, trend, consensus
- [ ] consensus 로직: 양쪽 5일 양수=aligned_buying, 양쪽 음수=aligned_selling, 그 외=divergent
- [ ] 인스턴스 캐싱, graceful degradation
- [ ] `tests/test_market_intelligence/test_kr_flow_fetcher.py` 작성 및 통과

### KR-002: KR Layer 2에 investor_flow 서브메트릭 추가
**Description:** 시스템으로서, 외국인/기관 순매수를 정량 스코어(±100)로 변환하여 KR Layer 2에 반영한다.

**Acceptance Criteria:**
- [ ] KR_STRUCTURE_WEIGHTS 재분배: vkospi=0.20, breadth_50=0.20, breadth_200=0.15, sector=0.15, mcclellan=0.10, investor_flow=0.20 (합계 1.0)
- [ ] `_score_investor_flow()`: aligned_buying→+80, foreign_only→+40, inst_only→+30, divergent→0, foreign_sell→-40, aligned_selling→-80
- [ ] 규모 보너스: 외국인 5일 절대값 > 1조원 → ±20 추가
- [ ] flow_data=None → `(NaN, {'error': ...})`
- [ ] 최종 점수 클램핑 ±100
- [ ] **기존 테스트 업데이트**: 가중치, 메트릭 키 검증
- [ ] docstring 업데이트

### KR-003: MarketIntelligence KR 경로에 flow 전달
**Description:** 시스템으로서, KR 투자자 수급 데이터가 MI를 통해 KR Layer 2까지 전달되도록 한다.

**Acceptance Criteria:**
- [ ] `_init_kr()`에서 KRFlowFetcher lazy 초기화
- [ ] analyze()에서 market=='kr'일 때 context에 kr_flow_data 추가
- [ ] `kr_market_analyzer.py`에 수집 블록 추가 (`KR_INVESTOR_FLOW_ENABLED` 환경변수)
- [ ] `.env.example`에 CBOE_PCR_ENABLED, KR_INVESTOR_FLOW_ENABLED 추가
- [ ] 수집 실패 시 경고 로그, 분석 계속

### KR-004: KR 프롬프트에 투자자 수급 반영
**Description:** 리포트 소비자로서, KR Notion 리포트에서 외국인/기관 순매수 동향을 확인한다.

**Acceptance Criteria:**
- [ ] `_build_kr_investor_flow_block(flow_data)` 함수 (인라인 f-string, Jinja2 아님)
- [ ] flow_data=None → 빈 문자열 (블록 생략)
- [ ] Worker-A 시그니처에 investor_flow_data 추가, 매크로 뒤 삽입
- [ ] Worker-B 시그니처에 investor_flow_summary 추가
- [ ] KRW 형식 (`f"{value:,.0f}원"`)

### KR-005: 시장 전체 공매도 비율 보조 시그널
**Description:** 시스템으로서, 시장 전체 공매도 비율을 investor_flow 스코어의 보조 시그널로 활용한다.

**Acceptance Criteria:**
- [ ] `fetch_market_short_selling(days=20)`: `pykrx.stock.get_shorting_volume_by_date(start, end)` — 시장 전체, 종목 파라미터 없음
- [ ] `get_short_selling_summary()`: short_ratio_today, short_ratio_5d_avg, trend
- [ ] `_score_investor_flow()` 내 조건부 보너스: short≥5%+외국인매도→-5, short감소+외국인매수→+5, 그 외→0
- [ ] 공매도 데이터 없으면 보너스 0 (기존 로직 유지)
- [ ] 최종 점수 클램핑 ±100

### DOC-001: CLAUDE.md 문서 업데이트
**Description:** 개발자로서, 새 fetcher 클래스가 CLAUDE.md에 문서화되어야 한다.

**Acceptance Criteria:**
- [ ] `market_intelligence/CLAUDE.md`에 CBOEFetcher, KRFlowFetcher 추가
- [ ] 데이터 플로우 문서화
- [ ] 환경변수 문서화

## Functional Requirements

- FR-1: CBOEFetcher는 CBOE CSV에서 PCR 데이터를 다운로드/파싱하고 primary/fallback 체인 지원
- FR-2: KRFlowFetcher는 pykrx로 KOSPI 투자자별 매매 데이터를 YYYYMMDD 형식으로 조회
- FR-3: Layer 5 SUB_WEIGHTS 합계 = 1.0, options_flow 스코어 범위 ±100
- FR-4: KR Layer 2 KR_STRUCTURE_WEIGHTS 합계 = 1.0, investor_flow 스코어 범위 ±100
- FR-5: pcr_data/flow_data=None일 때 NaN 반환 → weighted_composite 자동 스킵
- FR-6: KRFlowFetcher는 pykrx 미설치 시 ImportError 없이 graceful 동작
- FR-7: 수급 데이터는 일일 분석 JSON에 포함 (US: `pcr`, KR: `investor_flow`)
- FR-8: KR-005 공매도는 시장 전체 비율만 사용 (종목별 pykrx 미지원)
- FR-9: 수급 수집 실패 시 기존 분석 무영향
- FR-10: KR은 KRSentimentLayer, US는 SentimentLayer 사용 (분리)

## Non-Goals (Out of Scope)

- 실시간(인트라데이) 수급 데이터 수집
- 개별 종목별 Put/Call Ratio
- 개별 종목별 외국인/기관 순매수 (시장 전체만, Phase 1)
- 종목별 공매도 거래량 (pykrx 미지원)
- 유료 데이터 소스 (Bloomberg, OptionMetrics 등)
- KRX 프로그램 매매 데이터
- 대시보드(Streamlit) UI 변경

## Technical Considerations

- CBOE CSV: 무료, 인증 불필요, 장 마감 후 업데이트
- pykrx: KRX 웹 스크래핑, 무료, 인증 불필요, YYYYMMDD 형식
- US 프롬프트: Jinja2 `.md.j2` 템플릿 — 테이블은 `{value}` LLM 채움 방식, PCR은 데이터 블록으로 주입
- KR 프롬프트: 인라인 f-string — `kr_parallel_prompt_builder.py`에서 직접 조합
- Docker: pykrx 추가 시 `docker compose build` 필요
- 환경변수: CBOE_PCR_ENABLED (기본 true), KR_INVESTOR_FLOW_ENABLED (기본 true)

## Success Metrics

- US JSON에 `pcr` 키 포함, KR JSON에 `investor_flow` 키 포함
- Layer 5/Layer 2 가중치 합 각각 1.0
- 수급 데이터 미수집 시 기존 테스트 전체 통과
- Notion 리포트에 수급 분석 표시

## Open Questions (Resolved)

- ~~CBOE CSV URL 변경 감지~~ → fallback + 로그 경고
- ~~pykrx 사이트 변경~~ → graceful degradation
- ~~investor_flow 가중치 최적값~~ → 운영 후 weight_optimizer 조정
- ~~종목별 공매도~~ → **pykrx 미지원 확인, 시장 전체로 재설계 (v2)**
- ~~US/KR SentimentLayer 공유 문제~~ → **KRSentimentLayer 분리 사용 (v2)**
- ~~스코어 범위 ±60 vs ±100~~ → **±100 통일 (v2)**
- ~~pcr_data=None → 0.0 vs NaN~~ → **NaN 사용 (v2)**
