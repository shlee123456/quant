# Docker 배포 계획

## 1. 개요

멀티-에셋 트레이딩 봇을 Docker 컨테이너로 배포하기 위한 아키텍처 설계 문서입니다.

**배포 전략**: 단일 컨테이너로 시작하여 간단하고 빠른 배포를 우선시합니다.

---

## 2. 아키텍처 설계

### 2.1 단일 컨테이너 구조

```
┌─────────────────────────────────────────────────┐
│   Trading Bot Container                          │
│   (python:3.11-slim)                            │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  Application Services                       │ │
│  │                                             │ │
│  │  • Backtester                               │ │
│  │  • Strategy Optimizer                       │ │
│  │  • Dashboard (Streamlit) - Port 8501       │ │
│  │  • Paper Trader (optional)                 │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  Trading Bot Core                           │ │
│  │                                             │ │
│  │  • Brokers (CCXT, Korea Investment)        │ │
│  │  • Strategies (RSI, MACD, MA)              │ │
│  │  • Data Handlers                            │ │
│  │  • Simulation Data Generator                │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  Data Volumes (mounted from host)          │ │
│  │                                             │ │
│  │  /app/data/       ← ./data/                │ │
│  │  /app/logs/       ← ./logs/                │ │
│  │  /app/.env        ← ./.env (read-only)     │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 2.2 설계 결정 및 근거

#### 단일 컨테이너를 선택한 이유
- ✅ **간단한 배포**: docker-compose up 한 번으로 전체 시스템 실행
- ✅ **빠른 시작**: 복잡한 서비스 간 통신 설정 불필요
- ✅ **리소스 효율**: 오버헤드 최소화
- ✅ **개발 편의**: 로컬 개발 환경과 유사
- ✅ **유지보수 용이**: 단순한 구조로 문제 해결 쉬움

#### 향후 멀티 컨테이너 전환 가능
현재 단일 컨테이너로 시작하지만, 필요 시 다음과 같이 분리 가능:
- `backtester`: 배치 작업용 컨테이너
- `dashboard`: Streamlit UI 전용 컨테이너
- `paper-trader`: 실시간 트레이딩 전용 컨테이너

---

## 3. 기술 스택

### 3.1 Base Image
- **선택**: `python:3.11-slim`
- **이유**:
  - Python 3.11 호환성 (프로젝트 요구사항)
  - slim 버전으로 이미지 크기 최소화 (~150MB)
  - 공식 이미지로 보안 업데이트 지원

**대안 검토**:
- ❌ `python:3.11-alpine`: 더 작지만 (50MB), 일부 Python 패키지 빌드 문제 가능
- ❌ `python:3.11`: 너무 큼 (1GB+)

### 3.2 멀티 스테이지 빌드
빌드 효율성을 위해 멀티 스테이지 빌드 적용:

```dockerfile
# Stage 1: Builder - 의존성 컴파일
FROM python:3.11-slim as builder
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - 실행 환경
FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
```

**장점**:
- 최종 이미지에 빌드 도구 미포함 (크기 절감)
- 레이어 캐싱으로 빌드 시간 단축

---

## 4. 데이터 영속성

### 4.1 볼륨 마운트 전략

| Host Path | Container Path | 용도 | 권한 |
|-----------|----------------|------|------|
| `./data/` | `/app/data/` | 과거 데이터, 백테스트 결과 | Read/Write |
| `./logs/` | `/app/logs/` | 애플리케이션 로그 | Read/Write |
| `./.env` | `/app/.env` | 환경 변수 (API 키) | Read-Only |
| `./config/` | `/app/config/` | 전략 설정 파일 | Read-Only |

### 4.2 디렉토리 구조

```
crypto-trading-bot/
├── data/                       # 데이터 볼륨
│   ├── historical/             # 과거 OHLCV 데이터 캐시
│   │   ├── crypto/
│   │   └── stocks/
│   ├── backtest_results/       # 백테스트 결과 저장
│   │   ├── strategies/
│   │   └── optimizations/
│   └── paper_trading/          # 페이퍼 트레이딩 기록
│
├── logs/                       # 로그 볼륨
│   ├── trading.log             # 거래 로그
│   ├── error.log               # 에러 로그
│   └── dashboard.log           # 대시보드 로그
│
├── config/                     # 설정 볼륨 (옵션)
│   ├── strategies.yaml         # 전략 설정
│   └── brokers.yaml            # 브로커 설정
│
└── .env                        # 환경 변수 (Git 제외)
```

### 4.3 데이터 백업 전략

컨테이너 재시작 시에도 데이터 보존:
```bash
# 백업
tar -czf backup_$(date +%Y%m%d).tar.gz data/ logs/

# 복원
tar -xzf backup_YYYYMMDD.tar.gz
```

---

## 5. 환경 변수 관리

### 5.1 .env 파일 구조

```bash
# .env (절대 Git에 커밋하지 않음!)

# ===== Cryptocurrency Brokers =====
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
UPBIT_API_KEY=your_upbit_api_key
UPBIT_API_SECRET=your_upbit_api_secret

# ===== Korea Investment Securities =====
KIS_APPKEY=your_kis_appkey
KIS_APPSECRET=your_kis_appsecret
KIS_ACCOUNT=12345678-01
KIS_MOCK=true                   # true=모의투자, false=실전

# ===== Application Settings =====
INITIAL_CAPITAL=10000.0
POSITION_SIZE=0.95
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
TIMEZONE=Asia/Seoul

# ===== Dashboard Settings =====
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

### 5.2 .env.example 제공

사용자가 쉽게 설정할 수 있도록 템플릿 제공:
```bash
cp .env.example .env
# 편집기로 .env 열어서 실제 API 키 입력
```

### 5.3 보안 고려사항

- ✅ `.env` 파일은 `.gitignore`에 추가
- ✅ 컨테이너 내부에서 read-only로 마운트
- ✅ 환경 변수는 로그에 출력하지 않음
- ✅ 프로덕션 환경에서는 Docker Secrets 사용 권장 (향후)

---

## 6. 네트워크 구성

### 6.1 포트 매핑

| Service | Container Port | Host Port | 용도 |
|---------|----------------|-----------|------|
| Streamlit Dashboard | 8501 | 8501 | 웹 UI 접근 |

**액세스**:
- 로컬: `http://localhost:8501`
- 네트워크: `http://<host-ip>:8501`

### 6.2 헬스체크

Streamlit의 내장 헬스체크 엔드포인트 사용:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## 7. 보안 설계

### 7.1 실행 사용자

보안을 위해 non-root 사용자로 실행:
```dockerfile
# Create non-root user
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app

USER trader
```

### 7.2 파일 시스템 권한

```
/app/                   # 애플리케이션 코드 (read-only)
/app/data/              # 데이터 (read-write, owner: trader)
/app/logs/              # 로그 (read-write, owner: trader)
/app/.env               # 환경 변수 (read-only, owner: root)
```

### 7.3 네트워크 보안

- 대시보드 포트(8501)만 외부 노출
- 필요 시 reverse proxy (Nginx, Traefik) 추가 가능
- HTTPS는 reverse proxy 레벨에서 처리

---

## 8. 이미지 최적화

### 8.1 이미지 크기 최적화

**목표 크기**: 500-700MB

**최적화 기법**:
1. **멀티 스테이지 빌드**: 빌드 도구 제외
2. **레이어 캐싱**: 자주 변경되지 않는 레이어 먼저 배치
3. **불필요한 파일 제외**: `.dockerignore` 사용
4. **APT 캐시 정리**: `rm -rf /var/lib/apt/lists/*`
5. **pip 캐시 비활성화**: `--no-cache-dir`

### 8.2 .dockerignore

```
# Git
.git
.gitignore
.gitmodules

# Python
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.egg-info
dist/
build/

# Virtual environments
venv/
env/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo

# Tests
tests/
.pytest_cache/
.coverage
htmlcov/

# Documentation
docs/
*.md
!README.md

# Data (should be mounted as volume)
data/
logs/

# Environment
.env
.env.local

# OS
.DS_Store
Thumbs.db

# CI/CD (not needed)
.github/

# Docker
Dockerfile
docker-compose.yml
.dockerignore
```

### 8.3 빌드 시간 최적화

**레이어 순서** (변경 빈도 낮은 것부터):
1. System dependencies (거의 안 바뀜)
2. requirements.txt (가끔 바뀜)
3. Application code (자주 바뀜)

```dockerfile
# ❌ 비효율적 (매번 전체 재빌드)
COPY . .
RUN pip install -r requirements.txt

# ✅ 효율적 (requirements.txt 변경 시만 재빌드)
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

---

## 9. 실행 모드

### 9.1 지원 모드

단일 컨테이너로 다양한 실행 모드 지원:

#### 1) Dashboard 모드 (기본)
```bash
docker-compose up
# 대시보드 실행: http://localhost:8501
```

#### 2) Backtester 모드
```bash
docker-compose run --rm trading-bot python examples/run_backtest_example.py
```

#### 3) Optimizer 모드
```bash
docker-compose run --rm trading-bot python examples/optimize_strategy.py
```

#### 4) Paper Trading 모드
```bash
docker-compose run --rm trading-bot python -m trading_bot.paper_trader
```

#### 5) Interactive Shell 모드
```bash
docker-compose run --rm trading-bot bash
# 컨테이너 내부에서 직접 명령 실행
```

### 9.2 docker-compose.yml 오버라이드

다양한 실행 모드를 위해 오버라이드 파일 사용:

**docker-compose.yml** (기본 - Dashboard)
```yaml
version: '3.8'

services:
  trading-bot:
    build: .
    command: streamlit run dashboard/app.py --server.address 0.0.0.0
    ...
```

**docker-compose.backtester.yml** (Backtester)
```yaml
version: '3.8'

services:
  trading-bot:
    command: python examples/run_backtest_example.py
```

**사용**:
```bash
docker-compose -f docker-compose.yml -f docker-compose.backtester.yml up
```

---

## 10. 리소스 관리

### 10.1 리소스 제한

컨테이너 리소스 사용량 제한:
```yaml
services:
  trading-bot:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 10.2 예상 리소스 사용량

| 모드 | CPU | 메모리 | 디스크 I/O |
|------|-----|--------|-----------|
| Dashboard | 낮음 (5-10%) | 200-300MB | 낮음 |
| Backtester | 중간 (30-60%) | 500MB-1GB | 중간 |
| Optimizer | 높음 (80-100%) | 1-2GB | 높음 |
| Paper Trading | 낮음 (10-20%) | 300-500MB | 중간 |

### 10.3 모니터링

리소스 사용량 모니터링:
```bash
# 실시간 모니터링
docker stats trading-bot

# 로그 확인
docker logs -f trading-bot
```

---

## 11. 로컬 개발 워크플로우

### 11.1 개발 환경 설정

```bash
# 1. 저장소 클론
git clone <repo-url>
cd crypto-trading-bot

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일 편집 (API 키 입력)

# 3. Docker 이미지 빌드
docker-compose build

# 4. 컨테이너 실행
docker-compose up -d

# 5. 로그 확인
docker-compose logs -f
```

### 11.2 개발 중 코드 변경

**옵션 1: 볼륨 마운트로 실시간 반영** (개발 시)
```yaml
services:
  trading-bot:
    volumes:
      - ./trading_bot:/app/trading_bot:ro
      - ./dashboard:/app/dashboard:ro
```

**옵션 2: 이미지 재빌드** (프로덕션)
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### 11.3 디버깅

```bash
# 컨테이너 내부 접속
docker-compose exec trading-bot bash

# Python 인터프리터 실행
docker-compose exec trading-bot python

# 특정 스크립트 실행
docker-compose exec trading-bot python -m trading_bot.backtester
```

---

## 12. 트러블슈팅

### 12.1 일반적인 문제

#### 문제 1: 포트 충돌
```
Error: Bind for 0.0.0.0:8501 failed: port is already allocated
```

**해결**:
```bash
# 포트를 사용 중인 프로세스 확인
lsof -i :8501

# 프로세스 종료 또는 다른 포트 사용
docker-compose down
# docker-compose.yml에서 포트 변경: "8502:8501"
docker-compose up -d
```

#### 문제 2: 볼륨 권한 오류
```
PermissionError: [Errno 13] Permission denied: '/app/data/...'
```

**해결**:
```bash
# 호스트에서 디렉토리 권한 수정
sudo chown -R 1000:1000 data/ logs/

# 또는 컨테이너 재빌드
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### 문제 3: 환경 변수 미적용
```
KeyError: 'BINANCE_API_KEY'
```

**해결**:
```bash
# .env 파일 확인
cat .env

# 컨테이너 재시작
docker-compose restart

# 환경 변수 직접 확인
docker-compose exec trading-bot env | grep BINANCE
```

### 12.2 로그 확인

```bash
# 전체 로그
docker-compose logs

# 실시간 로그
docker-compose logs -f

# 최근 100줄
docker-compose logs --tail=100

# 특정 서비스 로그
docker-compose logs trading-bot
```

---

## 13. 성능 최적화

### 13.1 캐싱 전략

1. **Docker 레이어 캐싱**: 자주 변경되지 않는 레이어 먼저 배치
2. **pip 패키지 캐싱**: requirements.txt 변경 시에만 재설치
3. **데이터 캐싱**: 과거 데이터를 볼륨에 저장하여 재사용

### 13.2 빌드 속도 향상

```bash
# 병렬 빌드 (Docker BuildKit)
DOCKER_BUILDKIT=1 docker-compose build

# 특정 스테이지까지만 빌드
docker build --target builder .
```

### 13.3 실행 속도 향상

```bash
# 불필요한 컨테이너 정리
docker system prune -a

# 이미지 레이어 압축
docker-compose build --compress
```

---

## 14. 향후 확장 계획

### 14.1 Phase 1: 단일 컨테이너 (현재)
- ✅ 로컬 개발 및 테스트
- ✅ 간단한 배포
- ✅ Dashboard, Backtester, Optimizer 통합

### 14.2 Phase 2: 멀티 컨테이너 (필요 시)
- 서비스별 독립 컨테이너
- 독립적 스케일링
- 장애 격리

### 14.3 Phase 3: 클라우드 배포 (향후)
- AWS ECS/Fargate
- Google Cloud Run
- Azure Container Instances
- Kubernetes 클러스터

### 14.4 Phase 4: 고급 기능 (선택)
- 메시지 큐 (Redis, RabbitMQ)
- 데이터베이스 (PostgreSQL, TimescaleDB)
- 모니터링 (Prometheus, Grafana)
- 로그 수집 (ELK Stack)

---

## 15. 체크리스트

### 배포 전 체크리스트
- [ ] Docker Desktop 설치 및 실행 확인
- [ ] `.env` 파일 생성 및 API 키 설정
- [ ] `data/`, `logs/` 디렉토리 생성
- [ ] `.gitignore`에 `.env`, `data/`, `logs/` 추가 확인
- [ ] requirements.txt 최신 상태 확인
- [ ] Dockerfile 작성 완료
- [ ] docker-compose.yml 작성 완료
- [ ] .dockerignore 작성 완료

### 배포 후 체크리스트
- [ ] 이미지 빌드 성공 확인
- [ ] 컨테이너 실행 확인
- [ ] 대시보드 접근 확인 (http://localhost:8501)
- [ ] 볼륨 마운트 확인 (데이터 저장 테스트)
- [ ] 로그 정상 출력 확인
- [ ] 백테스트 실행 테스트
- [ ] 환경 변수 적용 확인

---

## 16. 참고 자료

### Docker 공식 문서
- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)

### Python Docker 이미지
- [Python Official Images](https://hub.docker.com/_/python)

### 보안
- [Docker Security](https://docs.docker.com/engine/security/)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)

---

**작성일**: 2026-02-07
**버전**: 1.0.0
**다음 단계**: Dockerfile 및 docker-compose.yml 구현
