"""FastAPI 앱 — 앱 초기화와 라우터 등록만 담당.

엔드포인트 구현은 routers/ 아래로 분리했다(비즈니스 로직은 services/, DB 접근은
repositories/). 라우트별 위치:
    /health                 routers/health.py
    /analyze                routers/analyze.py
    /select, /profile/{id}  routers/cards.py
    /transcribe             routers/transcribe.py
    /scene                  routers/scene.py
    /sentence               routers/sentence.py

graceful degradation: DB 다운 시에도 /analyze·/select는 500을 내지 않는다.
장면 인식도 마찬가지 — AI 서버가 죽어도 /scene은 200 + context=null을 반환한다.
/sentence도 Gemini가 죽으면 200 + 나열 문장을 반환한다.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.seed import init_db
from app.routers import (
    analyze,
    auth,
    cards,
    health,
    history,
    onboarding,
    scene,
    sentence,
    transcribe,
)

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AAC Mode 2 Server")
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(cards.router)
app.include_router(transcribe.router)
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(history.router)
app.include_router(scene.router)
app.include_router(sentence.router)


@app.on_event("startup")
def _startup() -> None:
    """테이블 생성 + 카탈로그/데모 유저 seed. MySQL 미가용이어도 서버는 계속 기동."""
    try:
        ok = init_db()
        if not ok:
            logger.warning("init_db가 실패했지만 서버는 계속 기동합니다(개인화 비활성).")
    except Exception:
        logger.warning("startup init_db 예외, 서버는 계속 기동합니다.", exc_info=True)
