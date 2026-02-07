# 키움증권 OpenAPI 조사 보고서

## 1. 개요

키움증권 OpenAPI+는 고객이 직접 프로그래밍한 투자전략을 키움증권이 제공하는 모듈에 연결하여 시세조회, 잔고조회, 주문 등을 자동으로 실행할 수 있도록 제공하는 서비스입니다.

- **공식 명칭**: 키움 OpenAPI+ (KOA Studio)
- **타입**: ActiveX Control (OCX) 기반 OLE 컨트롤
- **개발 지원**: VB, 엑셀, 웹기반, MFC 등
- **공식 문서**: [키움 OpenAPI+ 개발가이드](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf)

## 2. Python 연동 방법

### 2.1 기본 요구사항

키움 OpenAPI+를 Python에서 사용하기 위해서는 다음 요구사항을 충족해야 합니다:

- **운영체제**: Windows 전용 (ActiveX/COM 기반)
- **Python 아키텍처**: 32-bit 필수 (64-bit Python에서는 작동하지 않음)
- **GUI 프레임워크**: PyQt5 또는 PySide2 필요

### 2.2 32-bit Python 환경 구성

Anaconda 64-bit에서 32-bit 가상환경 생성 방법:

```bash
# 1. 32-bit 가상환경 생성
conda create -n kiwoom_32bit

# 2. 가상환경 활성화
conda activate kiwoom_32bit

# 3. 32-bit 설정
conda config --env --set subdir win-32

# 4. Python 3.8/3.9/3.10/3.11 설치
conda install python=3.9
```

### 2.3 주요 Python 라이브러리

#### 1) pykiwoom (sharebook-kr)

- **GitHub**: [sharebook-kr/pykiwoom](https://github.com/sharebook-kr/pykiwoom)
- **특징**:
  - 기본적인 Python 문법만으로 자동매매 프로그램 작성 가능
  - KiwoomManager를 통한 독립 프로세스 실행 지원
  - 초보자 친화적
- **설치**:
  ```bash
  pip install pykiwoom
  ```

#### 2) kiwoom (breadum)

- **GitHub**: [breadum/kiwoom](https://github.com/breadum/kiwoom)
- **특징**:
  - PyQt5를 직접 사용하는 심플 라이브러리
  - 부가 기능 최소화
  - 커스터마이징이 필요한 개발자에게 적합
- **설치**:
  ```bash
  pip install kiwoom
  ```

#### 3) KOAPY (elbakramer)

- **GitHub**: [elbakramer/koapy](https://github.com/elbakramer/koapy)
- **특징**:
  - 가장 포괄적이고 강력한 라이브러리
  - PySide2 기본, PyQt5 대안 지원 (qtpy 통해)
  - 고급 기능 및 유틸리티 제공
- **설치**:
  ```bash
  pip install koapy
  ```

### 2.4 로그인 및 인증

#### 로그인 방법

```python
# 수동 로그인 (기본 방식)
# CommConnect() 함수 호출
# OnEventConnect 이벤트로 성공 여부 확인
# 반환값: 0 = 성공, 기타 = 실패 (오류코드 참조)
```

- **실서버 접속**: 일반 로그인
- **모의투자 접속**: 로그인창에서 '모의투자 접속' 체크박스 선택

## 3. 주요 API 기능

### 3.1 실시간 시세 수신

- **함수**: `SetRealReg()`
- **기능**: 실시간 데이터 등록 및 이벤트 수신
- **개선사항**: OpenAPI+는 기존 API 대비 실시간 데이터 수신 속도가 개선됨
- **특징**:
  - 실시간 조건검색 제공
  - 실시간 등록/해지 기능
  - 이벤트 기반 데이터 전달

### 3.2 과거 데이터 조회

#### 일봉 데이터
- **조회 범위**: 제한 없음 (과거 전체 데이터 조회 가능)
- **기능**: 종목별 일별 OHLCV 데이터

#### 분봉 데이터
- **조회 범위**: 약 160일 전까지
- **데이터량**: 최대 약 60,000분의 데이터
- **기준**: 조회 시점 기준

#### 데이터 연속 조회
- 1초에 5회 호출 제한이 있으므로, 연속 조회 시 주의 필요
- 대량 데이터 조회 시 호출 간격 조절 필요

### 3.3 주문 실행 (매수/매도)

#### 지원 주문 유형
- 신규매수
- 신규매도
- 매수취소
- 매도취소
- 매수정정
- 매도정정

#### 호가 구분
- 지정가
- 시장가
- 조건부지정가
- 기타 다양한 주문 방식

#### 신용 주문
- **함수**: `SendOrderCredit()`
- **지원**: 대주를 제외한 신용주문 가능

### 3.4 계좌 정보 조회

- **전제 조건**: 로그인 필수
- **기능**:
  - 계좌 잔고 조회
  - 보유 종목 조회
  - 매수/매도 가능 금액 조회
  - 체결 내역 조회
  - 미체결 주문 조회
- **인자값**: 다양한 인자값으로 세부 정보 조회 가능

## 4. 지원 범위

### 4.1 국내 주식

- **완전 지원**: 국내주식 전면 지원
- **시장**:
  - 코스피 (KOSPI)
  - 코스닥 (KOSDAQ)
  - 코넥스 (KONEX)
- **파생상품**:
  - 코스피200 지수선물/옵션
  - 주식선물

### 4.2 해외 주식

- **해외주식**: 별도 API 없음 (키움증권 HTS/MTS 이용)
- **해외파생**: 별도의 "해외파생 OpenAPI-W" 제공
  - 전용 API로 분리됨
  - 별도 개발가이드 제공: [해외파생 OpenAPI-W 개발가이드](https://download.kiwoom.com/web/openapi/kiwoom_openapi_w_devguide_ver_1.0.pdf)

**참고**: 본 프로젝트에서 해외주식 거래가 필요하다면, 한국투자증권이나 이베스트투자증권 등 REST API를 제공하는 다른 증권사 고려 필요

## 5. 제약사항 및 한계점

### 5.1 플랫폼 제약

#### Windows 전용
- **이유**: ActiveX Control (OCX) 기반
- **영향**:
  - macOS, Linux 사용 불가
  - 서버 배포 시 Windows 서버 필요
  - 컨테이너(Docker) 환경 구축 복잡

#### 32-bit 전용
- **제약**: 64-bit Python에서 작동 불가
- **영향**:
  - 메모리 제약 (최대 4GB)
  - 최신 라이브러리 호환성 이슈 가능
  - 가상환경 구성 복잡도 증가

### 5.2 API 호출 제한

#### 일반 조회 제한
- **1초당**: 최대 5회 호출
- **1시간당**: 약 1,000회 호출 (경험적 제한)
- **영향**:
  - 대량 데이터 수집 시 시간 소요
  - 고빈도 트레이딩(HFT) 불가능
  - 백테스팅용 과거 데이터 수집 시 수 시간 소요 가능

#### 조건검색 제한
- **첫 번째 제한**: 1초당 5회
- **두 번째 제한**: 조건별 1분당 1회
- **실시간 조건검색**:
  - 검색 결과 100종목 이상 시 실행 불가
  - 최대 10개 조건식만 사용 가능

#### 중복 로그인 제한
- **모의투자 서버**: 중복 로그인 제한
- **이유**: 서버 부하 예방
- **영향**: 동일 계정으로 여러 프로그램 동시 실행 불가

### 5.3 인증 방법

#### 수동 로그인
- **방식**: ID/PW 직접 입력
- **제약**:
  - 완전 자동화 어려움
  - 프로그램 시작 시 수동 개입 필요
- **보안**:
  - 공인인증서 또는 간편인증
  - 2FA(Two-Factor Authentication) 적용

#### 자동 로그인
- **제약**: 보안상 제한적
- **대안**:
  - 세션 유지를 통한 재연결
  - 로그인 상태 모니터링

### 5.4 개발 환경 제약

#### OCX 등록 필요
- Windows 시스템에 OCX 컨트롤 등록 필수
- 개발 환경마다 재설치 필요

#### GUI 프레임워크 의존성
- PyQt5 또는 PySide2 필수
- 이벤트 루프 관리 필요
- 멀티스레딩 구현 복잡도 증가

### 5.5 데이터 제약

#### 과거 데이터 제한
- **분봉**: 약 160일 (60,000분)
- **틱**: 실시간만 제공, 과거 틱 데이터 미제공

#### 실시간 데이터
- 장중에만 수신 가능
- 장외 시간에는 실시간 데이터 없음

## 6. 수수료 구조

### 6.1 국내주식 거래 수수료

#### 매매 수수료
- **매수**: 0.015%
- **매도**: 0.015%

#### 세금 (매도 시)
- **코스피**:
  - 증권거래세: 0.05%
  - 농어촌특별세: 0.15%
  - **합계**: 0.20%
- **코스닥**:
  - 거래세: 0.20%

#### 총 비용 (매도 시)
- 수수료 (0.015%) + 세금 (0.20%) = **0.215%**

### 6.2 해외주식 거래 수수료

#### 미국 주식
- **온라인 거래** (HTS/MTS): 0.25% + 기타 거래세

**참고**:
- 비대면 계좌 개설 이벤트 등으로 우대 수수료 적용 가능
- 거래량에 따라 수수료 협의 가능
- 자세한 내용은 [키움증권 공식 홈페이지](https://www.kiwoom.com) 참조

### 6.3 프로그램 매매 시 고려사항

- **슬리피지**: 주문 시점과 체결 시점의 가격 차이
- **시장 충격**: 대량 주문 시 호가 변동
- **최소 거래단위**: 1주 이상
- **호가 단위**: 가격대별 호가 단위 상이

## 7. KOA Studio 활용

### 7.1 개요

KOA Studio는 키움증권이 제공하는 OpenAPI+ 개발 도구입니다.

### 7.2 주요 기능

- **TR 목록 확인**: 사용 가능한 모든 Transaction 조회
- **TR 정보 확인**: 각 TR의 입력/출력 필드 명세
- **테스트 실행**: 실제 데이터로 TR 테스트
- **개발 편의성**: API 개발 전 기능 검증 가능

### 7.3 사용 방법

1. **다운로드**:
   - 키움증권 홈페이지 > 고객서비스 > 다운로드 > Open API
   - KOAStudioSA.zip 다운로드

2. **모의투자 신청**:
   - KOA Studio 사용 전 필수
   - 키움증권 홈페이지에서 상시 모의투자 신청

3. **설치 및 실행**:
   - 다운로드한 파일 압축 해제
   - KOA Studio 실행
   - 모의투자 계정으로 로그인

## 8. 개발 워크플로우

### 8.1 권장 개발 순서

```
1. 키움증권 계좌 개설
   ↓
2. OpenAPI+ 사용 등록
   ↓
3. 모의투자 신청
   ↓
4. 32-bit Python 환경 구성
   ↓
5. 라이브러리 선택 및 설치 (pykiwoom/kiwoom/koapy)
   ↓
6. KOA Studio로 API 기능 학습
   ↓
7. 로그인 테스트
   ↓
8. 시세 조회 구현
   ↓
9. 계좌 조회 구현
   ↓
10. 모의투자에서 주문 테스트
   ↓
11. 백테스팅 및 전략 검증
   ↓
12. 실전 투자 (신중하게!)
```

### 8.2 모의투자 활용

- **목적**: 실제 환경 적용 전 충분한 테스트
- **접속 방법**: 로그인창에서 '모의투자 접속' 체크
- **장점**:
  - 실제 데이터 사용
  - 리스크 없이 전략 검증
  - 디버깅 및 오류 수정
- **제약**:
  - 중복 로그인 제한
  - 실서버와 일부 차이 가능

## 9. 프로젝트 통합 시 고려사항

### 9.1 아키텍처 통합

현재 프로젝트는 CCXT 기반 암호화폐 거래 봇이므로, 키움 OpenAPI+ 통합 시 다음을 고려해야 합니다:

#### 브로커 추상화 계층
```
Broker Interface (Abstract)
    ├── CCXT Broker (암호화폐)
    └── Kiwoom Broker (국내주식)
```

#### 데이터 핸들러 통합
```
Data Handler Interface
    ├── CCXT Data Handler (암호화폐)
    └── Kiwoom Data Handler (국내주식)
```

### 9.2 Windows 환경 이슈

- **개발 환경**: Windows 필수
- **배포**:
  - Windows 서버 또는 Windows VPS 필요
  - Docker 사용 시 Windows Container 필요
  - Linux 기반 배포 불가

### 9.3 크로스 플랫폼 전략

#### Option 1: 분리된 서비스
- 암호화폐 봇: Linux/macOS/Windows
- 주식 봇: Windows 전용
- 통신: REST API 또는 메시지 큐

#### Option 2: 하이브리드 접근
- 공통 전략 로직: 플랫폼 독립적
- 실행 계층: 플랫폼별 구현
- 데이터 수집: 별도 서비스

### 9.4 대안 검토

국내 주식 거래를 위한 다른 API 옵션:

#### 한국투자증권 OpenAPI
- **장점**:
  - REST API (HTTP 기반)
  - 플랫폼 독립적 (Windows/Linux/macOS)
  - 해외주식 지원
- **단점**:
  - 신규 플랫폼 (안정성 검증 필요)
  - 자료 및 커뮤니티 상대적으로 적음

#### 이베스트투자증권 xingAPI
- **장점**:
  - 다양한 언어 지원
  - 풍부한 기능
- **단점**:
  - 여전히 Windows 기반
  - 학습 곡선

## 10. 학습 리소스

### 10.1 공식 문서
- [키움증권 OpenAPI+ 홈페이지](https://www.kiwoom.com/h/customer/download/VOpenApiInfoView)
- [키움 OpenAPI+ 개발가이드 PDF](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf)
- [키움증권 OpenAPI Q&A 게시판](https://bbn.kiwoom.com/bbn.openAPIQnaBbsList.do)

### 10.2 커뮤니티 리소스
- [퀀트투자를 위한 키움증권 API (파이썬 버전) - WikiDocs](https://wikidocs.net/book/1173)
- [파이썬으로 배우는 알고리즘 트레이딩 - WikiDocs](https://wikidocs.net/2872)
- [키움 OpenAPI+ 파이썬 개발가이드 - WikiDocs](https://wikidocs.net/169005)

### 10.3 GitHub 저장소
- [sharebook-kr/pykiwoom](https://github.com/sharebook-kr/pykiwoom) - 초보자 친화적
- [breadum/kiwoom](https://github.com/breadum/kiwoom) - 심플 라이브러리
- [elbakramer/koapy](https://github.com/elbakramer/koapy) - 고급 기능
- [me2nuk/stockOpenAPI](https://github.com/me2nuk/stockOpenAPI) - 예제 코드
- [gyusu/Kiwoom_datareader](https://github.com/gyusu/Kiwoom_datareader) - 데이터 수집 예제

## 11. 결론 및 권장사항

### 11.1 키움 OpenAPI+ 평가

#### 장점
- ✅ 국내주식 거래에 가장 널리 사용됨
- ✅ 풍부한 기능 (실시간 시세, 과거 데이터, 주문 실행)
- ✅ 활발한 커뮤니티 및 다양한 Python 라이브러리
- ✅ 무료 제공
- ✅ 모의투자 지원으로 안전한 테스트 가능

#### 단점
- ❌ Windows 전용 (크로스 플랫폼 불가)
- ❌ 32-bit Python 전용 (메모리 제약)
- ❌ ActiveX/COM 기반 (현대적이지 않은 기술)
- ❌ 엄격한 호출 제한 (1초당 5회)
- ❌ 해외주식 미지원 (별도 API)

### 11.2 프로젝트 통합 권장사항

#### 단기 (Phase 1)
1. **학습 및 프로토타입**:
   - Windows 개발 환경 구축
   - pykiwoom으로 기본 기능 테스트
   - 모의투자에서 간단한 전략 실행

2. **브로커 추상화 설계**:
   - 공통 인터페이스 정의
   - CCXT와 유사한 구조로 키움 어댑터 설계

#### 중기 (Phase 2)
3. **국내주식 전용 봇 개발**:
   - 키움 OpenAPI+ 완전 통합
   - 기존 전략을 국내주식에 적용
   - 백테스팅 프레임워크 확장

4. **멀티 에셋 지원**:
   - 암호화폐 + 국내주식 동시 거래
   - 통합 대시보드

#### 장기 (Phase 3)
5. **크로스 플랫폼 고려**:
   - 한국투자증권 REST API 평가
   - Windows 의존성 최소화
   - 클라우드 배포 전략 수립

### 11.3 최종 의견

키움 OpenAPI+는 국내주식 자동매매를 위한 **사실상의 표준**이지만, Windows/32-bit 제약은 프로젝트 확장성에 영향을 미칠 수 있습니다.

**권장 접근 방식**:
- 국내주식 거래가 핵심 요구사항이면 → 키움 OpenAPI+ 채택
- 크로스 플랫폼 확장성이 중요하면 → 한국투자증권 REST API 평가 병행
- 두 가지 모두 고려하면 → 브로커 추상화 계층으로 유연성 확보

---

## Sources

- [키움증권 OpenAPI+ 홈페이지](https://www.kiwoom.com/h/customer/download/VOpenApiInfoView)
- [키움 OpenAPI+ 개발가이드 PDF](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf)
- [sharebook-kr/pykiwoom GitHub](https://github.com/sharebook-kr/pykiwoom)
- [breadum/kiwoom GitHub](https://github.com/breadum/kiwoom)
- [elbakramer/koapy GitHub](https://github.com/elbakramer/koapy)
- [퀀트투자를 위한 키움증권 API (파이썬 버전) - WikiDocs](https://wikidocs.net/book/1173)
- [퀀티랩 블로그 - 증권사 API 장단점 비교](https://blog.quantylab.com/htsapi.html)
- [한국투자증권 오픈API 개발자센터](https://apiportal.koreainvestment.com/intro)
- [키움증권 수수료 정보](https://stockstalker.co.kr/kiwoom-fee/)

**작성일**: 2026-02-07
**작성자**: kiwoom-researcher (trading-dev team)
