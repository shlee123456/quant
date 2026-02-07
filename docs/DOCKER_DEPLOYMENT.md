# Docker 배포 가이드

멀티-에셋 트레이딩 봇을 Docker 컨테이너로 배포하는 방법을 설명합니다.

---

## 목차

1. [사전 요구사항](#사전-요구사항)
2. [빠른 시작](#빠른-시작)
3. [환경 설정](#환경-설정)
4. [컨테이너 관리](#컨테이너-관리)
5. [실행 모드](#실행-모드)
6. [데이터 관리](#데이터-관리)
7. [트러블슈팅](#트러블슈팅)
8. [고급 설정](#고급-설정)

---

## 사전 요구사항

### 1. Docker 설치

#### macOS
```bash
# Homebrew 사용
brew install --cask docker

# 또는 Docker Desktop 다운로드
# https://www.docker.com/products/docker-desktop
```

#### Linux (Ubuntu/Debian)
```bash
# Docker Engine 설치
sudo apt-get update
sudo apt-get install docker.io docker-compose

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 재로그인 필요
```

#### Windows
```bash
# Docker Desktop for Windows 다운로드
# https://www.docker.com/products/docker-desktop
```

### 2. Docker 버전 확인

```bash
docker --version      # Docker 20.10 이상 권장
docker-compose --version  # Docker Compose 1.29 이상 권장
```

---

## 빠른 시작

### 1. 저장소 클론

```bash
git clone <repository-url>
cd crypto-trading-bot
```

### 2. 환경 변수 설정

```bash
# .env.example을 복사하여 .env 생성
cp .env.example .env

# 텍스트 에디터로 .env 열기
nano .env  # 또는 vi, code, etc.
```

`.env` 파일에서 다음 정보를 입력하세요:
- API 키 (Binance, Korea Investment Securities 등)
- 계좌 정보
- 초기 자본금

### 3. Docker 이미지 빌드

```bash
./scripts/docker-build.sh
```

또는 직접 빌드:
```bash
docker-compose build
```

### 4. 컨테이너 실행

```bash
./scripts/docker-run.sh
```

또는 직접 실행:
```bash
docker-compose up -d
```

### 5. 대시보드 접속

브라우저에서 다음 URL로 접속:
```
http://localhost:8501
```

---

## 환경 설정

### .env 파일 구성

`.env` 파일은 다음과 같은 구조로 되어 있습니다:

#### 암호화폐 브로커 설정
```bash
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

#### 한국투자증권 설정
```bash
KIS_APPKEY=your_appkey
KIS_APPSECRET=your_appsecret
KIS_ACCOUNT=12345678-01
KIS_MOCK=true  # true=모의투자, false=실전
```

#### 애플리케이션 설정
```bash
INITIAL_CAPITAL=10000.0
POSITION_SIZE=0.95
COMMISSION=0.001
LOG_LEVEL=INFO
TIMEZONE=Asia/Seoul
```

### 중요: 보안

- ⚠️ `.env` 파일은 **절대 Git에 커밋하지 마세요**
- ⚠️ API 키는 **읽기 전용 권한**만 부여하세요 (가능한 경우)
- ⚠️ 프로덕션 환경에서는 **출금 권한을 제거**하세요

---

## 컨테이너 관리

### 빌드

```bash
# 일반 빌드
./scripts/docker-build.sh

# 캐시 없이 빌드 (문제 발생 시)
./scripts/docker-build.sh --no-cache
```

### 실행

```bash
# 기본 실행 (대시보드 모드)
./scripts/docker-run.sh

# 백그라운드 실행
docker-compose up -d

# 포그라운드 실행 (로그 확인)
docker-compose up
```

### 중지

```bash
# 컨테이너 중지 (데이터 보존)
./scripts/docker-stop.sh

# 컨테이너 및 볼륨 제거 (데이터 삭제)
./scripts/docker-stop.sh --remove
```

### 로그 확인

```bash
# 최근 100줄 표시
./scripts/docker-logs.sh

# 실시간 로그 추적
./scripts/docker-logs.sh --follow

# 최근 N줄 표시
./scripts/docker-logs.sh --tail 500
```

### 컨테이너 상태 확인

```bash
# 실행 중인 컨테이너 확인
docker-compose ps

# 리소스 사용량 확인
docker stats trading-bot

# 헬스체크 확인
docker inspect --format='{{.State.Health.Status}}' trading-bot
```

---

## 실행 모드

Docker 컨테이너는 여러 모드로 실행할 수 있습니다.

### 1. Dashboard 모드 (기본)

Streamlit 대시보드를 실행합니다.

```bash
./scripts/docker-run.sh dashboard
# 또는
./scripts/docker-run.sh
```

**접속**: `http://localhost:8501`

### 2. Backtester 모드

전략 백테스트를 실행합니다.

```bash
./scripts/docker-run.sh backtester
```

또는 직접 실행:
```bash
docker-compose run --rm trading-bot python examples/run_backtest_example.py
```

### 3. Optimizer 모드

전략 파라미터 최적화를 실행합니다.

```bash
./scripts/docker-run.sh optimizer
```

또는:
```bash
docker-compose run --rm trading-bot python examples/optimize_strategy.py
```

### 4. Shell 모드

컨테이너 내부 쉘에 접속합니다.

```bash
./scripts/docker-run.sh shell
```

또는:
```bash
docker-compose run --rm trading-bot bash
```

**쉘 내부에서 할 수 있는 작업**:
```bash
# Python 인터프리터
python

# 백테스트 실행
python examples/run_backtest_example.py

# 파일 탐색
ls -la
cd trading_bot/
```

### 5. 커스텀 명령 실행

```bash
docker-compose run --rm trading-bot python <your_script>.py
```

---

## 데이터 관리

### 디렉토리 구조

```
crypto-trading-bot/
├── data/              # 데이터 볼륨 (호스트 <-> 컨테이너)
│   ├── historical/    # 과거 OHLCV 데이터
│   ├── backtest_results/  # 백테스트 결과
│   └── paper_trading/     # 페이퍼 트레이딩 기록
│
├── logs/              # 로그 볼륨
│   ├── trading.log    # 거래 로그
│   ├── error.log      # 에러 로그
│   └── dashboard.log  # 대시보드 로그
│
└── config/            # 설정 볼륨 (선택)
    └── strategies.yaml
```

### 데이터 백업

```bash
# 데이터 백업
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ logs/

# 데이터 복원
tar -xzf backup_YYYYMMDD_HHMMSS.tar.gz
```

### 데이터 초기화

```bash
# 주의: 모든 데이터가 삭제됩니다!
rm -rf data/* logs/*

# 또는 컨테이너와 함께 볼륨 제거
./scripts/docker-stop.sh --remove
```

---

## 트러블슈팅

### 문제 1: 포트 충돌

**증상**:
```
Error: Bind for 0.0.0.0:8501 failed: port is already allocated
```

**해결**:
```bash
# 포트를 사용 중인 프로세스 확인
lsof -i :8501

# 프로세스 종료
kill <PID>

# 또는 docker-compose.yml에서 포트 변경
ports:
  - "8502:8501"  # 호스트 포트를 8502로 변경
```

### 문제 2: 볼륨 권한 오류

**증상**:
```
PermissionError: [Errno 13] Permission denied: '/app/data/...'
```

**해결**:
```bash
# 호스트에서 디렉토리 권한 수정
sudo chown -R 1000:1000 data/ logs/

# 또는 Docker 사용자 확인
docker-compose exec trading-bot id
```

### 문제 3: 환경 변수 미적용

**증상**:
```
KeyError: 'BINANCE_API_KEY'
```

**해결**:
```bash
# .env 파일 확인
cat .env | grep BINANCE

# 컨테이너 재시작
docker-compose restart

# 환경 변수 직접 확인
docker-compose exec trading-bot env | grep BINANCE
```

### 문제 4: 이미지 빌드 실패

**증상**:
```
ERROR: failed to solve: process "/bin/sh -c pip install ..." did not complete successfully
```

**해결**:
```bash
# 캐시 없이 재빌드
./scripts/docker-build.sh --no-cache

# Docker BuildKit 비활성화하고 빌드
DOCKER_BUILDKIT=0 docker-compose build

# requirements.txt 확인
cat requirements.txt
```

### 문제 5: 컨테이너가 즉시 종료됨

**증상**:
```bash
docker-compose ps
# STATUS: Exited (1)
```

**해결**:
```bash
# 로그 확인
docker-compose logs

# 이전 컨테이너 로그 확인
docker logs trading-bot

# 인터랙티브 모드로 실행
docker-compose run --rm trading-bot bash
```

### 문제 6: 헬스체크 실패

**증상**:
```
Status: unhealthy
```

**해결**:
```bash
# 헬스체크 로그 확인
docker inspect trading-bot | grep -A 20 Health

# Streamlit 상태 확인
curl http://localhost:8501/_stcore/health

# 컨테이너 재시작
docker-compose restart
```

---

## 고급 설정

### 리소스 제한

`docker-compose.yml`에서 리소스 제한 설정:

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

### 네트워크 설정

#### Reverse Proxy (Nginx)

```nginx
# /etc/nginx/sites-available/trading-bot
server {
    listen 80;
    server_name trading.example.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

#### HTTPS 설정 (Let's Encrypt)

```bash
# Certbot 설치
sudo apt-get install certbot python3-certbot-nginx

# SSL 인증서 발급
sudo certbot --nginx -d trading.example.com
```

### 로깅 설정

`docker-compose.yml`에서 로깅 설정:

```yaml
services:
  trading-bot:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 환경별 설정

#### 개발 환경 (docker-compose.override.yml)

```yaml
version: '3.8'

services:
  trading-bot:
    volumes:
      # 코드 변경 시 자동 반영
      - ./trading_bot:/app/trading_bot:ro
      - ./dashboard:/app/dashboard:ro
    environment:
      - LOG_LEVEL=DEBUG
```

#### 프로덕션 환경 (docker-compose.prod.yml)

```yaml
version: '3.8'

services:
  trading-bot:
    restart: always
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

**사용**:
```bash
# 개발
docker-compose up

# 프로덕션
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 성능 최적화

### 1. 이미지 크기 줄이기

- 멀티 스테이지 빌드 사용 (이미 적용됨)
- 불필요한 파일 제외 (`.dockerignore`)
- Alpine 이미지 고려 (호환성 이슈 주의)

### 2. 빌드 시간 단축

```bash
# Docker BuildKit 사용
DOCKER_BUILDKIT=1 docker-compose build

# 병렬 빌드
docker-compose build --parallel
```

### 3. 실행 성능 향상

- 리소스 제한 적절히 설정
- 불필요한 컨테이너 정리: `docker system prune -a`
- 볼륨 대신 bind mount 사용 (개발 시)

---

## FAQ

### Q1: macOS에서 빌드가 느립니다.

**A**: Docker Desktop의 리소스 설정을 확인하세요.
- Docker Desktop > Preferences > Resources
- CPU: 4+ 코어 권장
- Memory: 4GB+ 권장

### Q2: 컨테이너 내부에서 파일을 수정할 수 있나요?

**A**: 가능하지만 권장하지 않습니다. 호스트에서 파일을 수정하고 재빌드하세요.

```bash
# 호스트에서 수정
vim trading_bot/strategy.py

# 재빌드
./scripts/docker-build.sh

# 재시작
docker-compose restart
```

### Q3: 여러 전략을 동시에 실행할 수 있나요?

**A**: docker-compose를 여러 개 실행하세요.

```yaml
# docker-compose.strategy1.yml
services:
  strategy1:
    extends:
      file: docker-compose.yml
      service: trading-bot
    container_name: trading-bot-strategy1
    command: python examples/strategy1.py
```

### Q4: 클라우드에 배포하려면?

**A**: 향후 클라우드 배포 가이드를 참조하세요. 기본적으로:
- AWS: ECS/Fargate
- GCP: Cloud Run
- Azure: Container Instances

### Q5: 데이터를 외부 DB에 저장하려면?

**A**: PostgreSQL 등을 추가하고 연결하세요.

```yaml
# docker-compose.yml에 추가
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: trading_bot
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## 참고 자료

- [Docker 공식 문서](https://docs.docker.com/)
- [Docker Compose 문서](https://docs.docker.com/compose/)
- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [프로젝트 아키텍처](docker_deployment_plan.md)

---

**작성일**: 2026-02-07
**버전**: 1.0.0
