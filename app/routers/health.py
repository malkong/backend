"""GET /health — 서버 및 DB 연결 상태 확인."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """SELECT 1로 DB 연결을 확인한다.

    DB가 죽어도 200 + db="disconnected"를 반환한다(503이 아님). 이 서버는
    DB 없이도 /analyze·/transcribe가 동작하는 graceful degradation 설계이고,
    기존 /health가 항상 200 {"status":"ok"}를 반환하던 계약도 유지하기 위함이다.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception:
        logger.warning("/health: DB 연결 확인 실패.", exc_info=True)
        return {"status": "ok", "db": "disconnected"}
