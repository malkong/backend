"""FastAPI 앱 (Week 1: GET /health, POST /analyze / Week 3: POST /transcribe). 엔드포인트만 담당, 비즈니스 로직 없음."""
import os
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.services.card_generator import get_candidate_cards
from app.services.llm import analyze_intent
from app.schemas.schemas import AnalyzeRequest, AnalyzeResponse, TranscribeResponse
from app.services.stt import transcribe as transcribe_speech

app = FastAPI(title="AAC Mode 2 Server")
app.mount("/web", StaticFiles(directory="web", html=True), name="web")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    analysis = analyze_intent(request.speech_text)
    cards = get_candidate_cards(analysis, request.user_id)
    return AnalyzeResponse(analysis=analysis, cards=cards)


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
