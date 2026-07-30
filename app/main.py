"""FastAPI 앱 — 앱 초기화와 라우터 등록만 담당.

엔드포인트 구현은 routers/ 아래로 분리했다(비즈니스 로직은 services/, DB 접근은
repositories/). 라우트별 위치:
    /health                 routers/health.py
    /analyze                routers/analyze.py
    /select, /profile/{id}  routers/cards.py
    /transcribe             routers/transcribe.py

graceful degradation: DB 다운 시에도 /analyze·/select는 500을 내지 않는다.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.seed import init_db
from app.routers import analyze, cards, health, transcribe

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AAC Mode 2 Server")
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(cards.router)
app.include_router(transcribe.router)


@app.on_event("startup")
def _startup() -> None:
    """테이블 생성 + 카탈로그/데모 유저 seed. MySQL 미가용이어도 서버는 계속 기동."""
    try:
        ok = init_db()
        if not ok:
            logger.warning("init_db가 실패했지만 서버는 계속 기동합니다(개인화 비활성).")
    except Exception:
        logger.warning("startup init_db 예외, 서버는 계속 기동합니다.", exc_info=True)
