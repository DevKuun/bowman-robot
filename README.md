# Bowman Robot

암호화폐 자동 리밸런싱 트레이딩 봇 - 최소 분산 포트폴리오(Minimum Variance Portfolio) 이론 기반

## 개요

Bowman Robot은 최소 분산 포트폴리오 이론을 활용하여 암호화폐 포트폴리오를 자동으로 리밸런싱하는 트레이딩 봇입니다.

### 주요 기능

- **멀티 거래소 지원**: Upbit, Binance, Korbit, Bithumb
- **멀티 유저 동시 처리**: 여러 사용자의 거래를 동시에 실행
- **자동 포트폴리오 최적화**: 주간 단위로 최적 포트폴리오 가중치 계산
- **5단계 리스크 레벨**: 사용자별 리스크 허용도에 따른 포트폴리오 조정
- **참조 가격 검증**: Binance 가격을 참조하여 이상 거래 방지

## 프로젝트 구조

```
bowman-robot/
├── src/
│   ├── core/                    # 핵심 도메인 로직
│   │   ├── models.py           # 도메인 모델
│   │   ├── portfolio.py        # 포트폴리오 최적화
│   │   └── trading.py          # 거래 엔진
│   │
│   ├── exchanges/              # 거래소 어댑터
│   │   ├── base.py             # 추상 인터페이스
│   │   ├── upbit.py            # Upbit 구현
│   │   ├── binance.py          # Binance 구현
│   │   ├── korbit.py           # Korbit 구현
│   │   └── bithumb.py          # Bithumb 구현
│   │
│   ├── infrastructure/         # 인프라 레이어
│   │   ├── database/           # SQLite/PostgreSQL 연결 및 Repository
│   │   ├── messaging/          # Slack 알림
│   │   └── encryption/         # AWS KMS 암호화
│   │
│   ├── workers/                # 워커 프로세스
│   │   ├── user_worker.py      # 사용자별 거래 워커
│   │   ├── portfolio_worker.py # 포트폴리오 최적화 워커
│   │   └── scheduler.py        # 메인 스케줄러
│   │
│   ├── config/                 # 설정
│   │   └── settings.py         # 환경변수 기반 설정
│   │
│   └── main.py                 # 엔트리포인트
│
├── migrations/                 # Alembic DB 마이그레이션
├── tests/                      # 테스트
├── docker-compose.yml          # Docker 오케스트레이션
├── Dockerfile                  # 컨테이너 빌드
├── requirements.txt            # Python 의존성
└── .env.example               # 환경변수 템플릿
```

## 빠른 시작

### 사전 요구사항

- Python 3.9+
- 거래소 API 키
- (선택) Docker & Docker Compose
- (선택) PostgreSQL 15+ (SQLite 사용 시 불필요)
- (선택) AWS 계정 (KMS 암호화 사용 시)

### 1. 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집하여 필요한 값 입력
```

### 2. Docker로 실행

**SQLite 모드 (간단, PostgreSQL 불필요):**
```bash
# Upbit 봇 실행
docker-compose --profile sqlite up -d upbit

# 특정 거래소만 실행
docker-compose --profile sqlite-binance up -d binance
docker-compose --profile sqlite-korbit up -d korbit
docker-compose --profile sqlite-bithumb up -d bithumb
```

**PostgreSQL 모드 (프로덕션/멀티유저):**
```bash
# PostgreSQL + Upbit 봇 실행
docker-compose --profile postgres up -d

# 특정 거래소 추가
docker-compose --profile postgres-binance up -d
```

### 3. 로컬 개발 환경 (SQLite 사용 - 권장)

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r requirements.txt

# .env 파일 생성 (SQLite가 기본값)
cp .env.example .env
# 필요한 값만 수정 (DB 설정 불필요)

# 봇 실행 (테이블 자동 생성)
python -m src.main --exchange upbit
```

### 4. PostgreSQL 사용 시

```bash
# .env 파일에서 DB_TYPE 변경
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bowmandb
DB_USER=postgres
DB_PASSWORD=your_password

# 데이터베이스 초기화
python -m src.main --exchange upbit --init-db
```

## 사용법

### 계정 관리 CLI

거래소 계정을 등록해야 봇이 동작합니다.

```bash
# 계정 추가
python -m src.cli.account add \
  --exchange upbit \
  --access-key "your-api-access-key" \
  --secret-key "your-api-secret-key" \
  --risk-level 2  # 0~4 (0=보수적, 4=공격적)

# 계정 목록 보기
python -m src.cli.account list

# 계정 설정 변경
python -m src.cli.account update <account-id> --risk-level 3

# 계정 검증 (API 키 테스트)
python -m src.cli.account verify <account-id>

# 계정 삭제
python -m src.cli.account delete <account-id>
```

### 봇 실행 CLI

```bash
python -m src.main --help

Options:
  --exchange {upbit,binance,korbit,bithumb}  거래소 선택 (필수)
  --log-level {DEBUG,INFO,WARNING,ERROR}  로그 레벨
  --init-db                          데이터베이스 초기화만 수행
  --optimize-only                    포트폴리오 최적화만 수행
```

### 포트폴리오 최적화만 실행

```bash
python -m src.main --exchange upbit --optimize-only
```

### Paper Trading (시뮬레이션)

실제 거래 없이 가상 잔고로 시뮬레이션:

```bash
# 기본 (100만원 시작)
python -m src.main --exchange upbit --paper

# 초기 잔고 지정
python -m src.main --exchange upbit --paper --initial-balance 5000000

# Ctrl+C로 종료하면 PnL 요약 출력
```

결과는 `data/paper_trading/` 폴더에 JSON으로 저장됩니다.

## 설정

### 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `DB_TYPE` | 데이터베이스 타입 (sqlite/postgresql) | sqlite |
| `DB_PATH` | SQLite 파일 경로 | data/bowman.db |
| `DB_HOST` | PostgreSQL 호스트 | localhost |
| `DB_PORT` | PostgreSQL 포트 | 5432 |
| `DB_NAME` | 데이터베이스 이름 | bowmandb |
| `DB_USER` | 데이터베이스 사용자 | postgres |
| `DB_PASSWORD` | 데이터베이스 비밀번호 | - |
| `AWS_ACCESS_KEY_ID` | AWS 액세스 키 | - |
| `AWS_SECRET_ACCESS_KEY` | AWS 시크릿 키 | - |
| `KMS_KEY_ID` | AWS KMS 키 ID | - |
| `SLACK_TOKEN` | Slack Bot 토큰 | - |
| `SLACK_CHANNEL_ID` | Slack 채널 ID | - |

### 리스크 레벨

| 레벨 | 설명 |
|------|------|
| 0 | 가장 보수적 (스테이블코인 비중 최대) |
| 1 | 보수적 |
| 2 | 중립 |
| 3 | 공격적 |
| 4 | 가장 공격적 (스테이블코인 비중 최소) |

## 아키텍처

### 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                        Scheduler                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ User Worker │  │ User Worker │  │ User Worker │   ...    │
│  │   (User 1)  │  │   (User 2)  │  │   (User N)  │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                  │
│         └────────────────┼────────────────┘                  │
│                          │                                   │
│                   ┌──────▼──────┐                            │
│                   │Trading Engine│                            │
│                   └──────┬──────┘                            │
│                          │                                   │
│         ┌────────────────┼────────────────┐                  │
│         │                │                │                  │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐          │
│  │   Upbit     │  │   Binance   │  │   Korbit    │          │
│  │   Adapter   │  │   Adapter   │  │   Adapter   │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │SQLite/PgSQL │
                   └─────────────┘
```

### 포트폴리오 최적화

1. 2년치 주간 가격 데이터 수집
2. 로그 수익률 계산
3. Ledoit-Wolf 공분산 수축 추정
4. CVXOPT로 2차 계획법 최적화
5. 리스크 레벨별 가중치 생성
6. 데이터베이스에 저장

## 보안

- API 키는 AWS KMS로 암호화되어 저장
- 환경 변수를 통한 민감 정보 관리
- 비root 사용자로 컨테이너 실행
- SQL Injection 방지를 위한 ORM 사용

## 라이선스

Private - All rights reserved

## 기여

내부 프로젝트로 외부 기여는 받지 않습니다.
