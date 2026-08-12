"""POST /transcribe — 업로드된 음성/영상 파일을 텍스트로 변환(STT)."""
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.schemas import TranscribeResponse
from app.services.stt import transcribe as transcribe_speech

router = APIRouter(tags=["transcribe"])


@router.post("/transcribe", response_model=TranscribeResponse)
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
