"""FastAPI 앱 — 엔드포인트 배선만 담당(비즈니스 로직은 services에 위임).

/health, /analyze(의도분석 + 카탈로그 매핑 + 개인화 재정렬), /select, /profile, /transcribe.
graceful degradation: DB 다운 시에도 /analyze·/select는 500을 내지 않는다.
"""
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.schemas.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ProfileResponse,
    SelectRequest,
    SelectResponse,
    TranscribeResponse,
)
from app.services import personalize, storage
from app.services.card_generator import get_candidate_cards
from app.services.llm import analyze_intent
from app.services.stt import transcribe as transcribe_speech

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AAC Mode 2 Server")
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.on_event("startup")
def _startup() -> None:
    """테이블 생성 + 카탈로그/데모 유저 seed. MySQL 미가용이어도 서버는 계속 기동."""
    try:
        ok = storage.init_db()
        if not ok:
            logger.warning("init_db가 실패했지만 서버는 계속 기동합니다(개인화 비활성).")
    except Exception:
        logger.warning("startup init_db 예외, 서버는 계속 기동합니다.", exc_info=True)


@app.get("/health")
def health():
    return {"status": "ok"}


def _extract_place(visual_context):
    if isinstance(visual_context, dict):
        return visual_context.get("place")
    return None


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    try:
        analysis = analyze_intent(request.speech_text)
        place = _extract_place(request.visual_context)
        cards = get_candidate_cards(analysis, request.user_id, place)
        cards = personalize.rerank(cards, request.user_id, analysis.intent, place)
        return AnalyzeResponse(analysis=analysis, cards=cards)
    except Exception as e:
        # card_generator/personalize가 자체적으로 예외를 삼키므로 여기 도달은 드묾.
        logger.warning("/analyze 처리 중 예외.", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": "분석 처리 중 오류가 발생했습니다.", "detail": str(e)},
        )


@app.post("/select", response_model=SelectResponse)
def select(request: SelectRequest):
    # DB 쓰기 실패 시에도 200 + {ok:false, new_count:0} (graceful degradation, 500 금지).
    ok, new_count = storage.record_selection(request.user_id, request.card, request.context)
    return SelectResponse(ok=ok, new_count=new_count)


@app.get("/profile/{user_id}", response_model=ProfileResponse)
def profile(user_id: int):
    top_cards = storage.get_top_cards(user_id)
    return ProfileResponse(user_id=user_id, top_cards=top_cards)


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe(file: UploadFile = File(...), user_id: str = Form(None)):
    suffix = os.path.splitext(file.filename)[1]
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(file.file.read())
        result = transcribe_speech(tmp_path)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": "음성 인식에 실패했습니다.", "detail": str(e)},
        )
    finally:
        os.remove(tmp_path)
    return TranscribeResponse(**result)
