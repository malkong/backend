"""DB 연결 계층 — SQLAlchemy 엔진/세션 + (임시) PyMySQL 커넥션.

=============================================================================
이 파일에는 지금 DB 접속 경로가 두 개 있음.

  (1) SQLAlchemy — engine / SessionLocal / Base / get_db()
      앞으로 쓸 정식 경로. 새 코드는 반드시 이쪽만 사용할 것.

  (2) get_legacy_connection() — PyMySQL 직접 커넥션
      구조 리팩터링 1단계에서 기존 services/storage.py의 생 SQL을 그대로
      옮기기 위해 임시로 남겨둔 것이다. 2차 리팩터링에서 repositories/를
      SQLAlchemy 세션 기반으로 전환하면서 (2)와 그 호출부를 전부 삭제한다.

  두 경로 모두 settings.DATABASE_URL 하나만 바라보므로 접속 대상은 동일하다
  (1단계 이전에는 storage.py가 .env에 없는 DB_HOST를 읽어 기본값 127.0.0.1로
   붙으려다 조용히 실패했다. 그 버그는 여기서 해소됨).
=============================================================================
"""
import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# (1) SQLAlchemy — 정식 경로
# ---------------------------------------------------------------------------
# pool_pre_ping: 커넥션을 꺼내 쓰기 직전에 살아있는지 확인한다. RDS/MySQL은
# wait_timeout이 지나면 유휴 커넥션을 끊는데, 이 옵션이 없으면 그 끊긴 커넥션이
# 풀에 남아 있다가 "MySQL server has gone away"로 터진다.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# TODO(2차 리팩터링): models/ 아래 SQLAlchemy 모델들이 이 Base를 상속하게 된다.
Base = declarative_base()


def get_db():
    """FastAPI 의존성. 라우터에서 `db: Session = Depends(get_db)`로 주입받는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# (2) PyMySQL — 임시 경로 (2차 리팩터링에서 삭제 예정)
# ---------------------------------------------------------------------------
# pymysql 미설치 환경에서도 import가 깨지지 않도록 lazy-safe import (기존 동작 유지).
try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:  # pragma: no cover - 설치 안 된 환경 방어
    pymysql = None
    DictCursor = None


def _legacy_db_params(with_db: bool = True) -> dict:
    """DATABASE_URL을 PyMySQL이 받는 개별 인자로 분해한다."""
    url = make_url(settings.DATABASE_URL)
    params = {
        "host": url.host,
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password or "",
        "charset": "utf8mb4",
    }
    if with_db:
        params["database"] = url.database
    return params


def get_legacy_connection(with_db: bool = True):
    """PyMySQL 커넥션 반환. 실패 시 예외를 던진다(호출자가 잡아 폴백)."""
    if pymysql is None:
        raise RuntimeError("PyMySQL이 설치되어 있지 않습니다.")
    return pymysql.connect(**_legacy_db_params(with_db))


def get_legacy_db_name() -> str:
    """DATABASE_URL에 지정된 데이터베이스 이름."""
    return make_url(settings.DATABASE_URL).database
