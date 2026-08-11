"""Gemini 의도 분석 호출 (llm.py). /transcribe(STT)는 3주차에 추가."""
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.core.prompts import ANALYZE_PROMPT
from app.schemas.schemas import AnalysisResult

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.1-flash-lite"

FALLBACK_ANALYSIS = AnalysisResult(
    intent="기타",
    intent_detail="분석에 실패해 기본값을 반환합니다.",
    easy_meaning="무슨 말인지 다시 한 번 확인이 필요해요.",
    response_type=["accept", "refuse", "question"],
    confidence=0.0,
)

# Mode 1(사진만 있고 상대방 발화가 없는 경우): 앱이 speech_text=""로 /analyze를 호출한다.
# 실패가 아니라 정상 경로이므로 FALLBACK_ANALYSIS와는 별개 상수를 쓴다.
EMPTY_SPEECH_ANALYSIS = AnalysisResult(
    intent="기타",
    intent_detail="",
    easy_meaning="",
    response_type=[],
    confidence=0.0,
)


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def analyze_intent(speech_text: str) -> AnalysisResult:
    """Gemini 호출 1번: speech_text를 분석해 intent 5필드(AnalysisResult)를 반환.

    speech_text가 비었거나 공백뿐이면(Mode 1: 사진만 있고 상대방 발화가 없는 경우)
    Gemini를 호출하지 않고 EMPTY_SPEECH_ANALYSIS를 즉시 반환한다 — 분석할 발화가
    없는데 매번 10~15초짜리 API 호출을 하는 건 낭비이고, 어차피 결과는 항상
    intent="기타"였다.

    Gemini 호출 실패(키 없음/네트워크 오류/파싱 오류 등) 시에도 서버가 죽지 않도록
    FALLBACK_ANALYSIS를 반환한다.
    """
    if not speech_text or not speech_text.strip():
        return EMPTY_SPEECH_ANALYSIS
    try:
        client = _get_client()
        prompt = ANALYZE_PROMPT.format(speech_text=speech_text)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalysisResult,
            ),
        )
        result = response.parsed
        if result is None:
            logger.warning("Gemini 응답 파싱 결과가 없어 FALLBACK_ANALYSIS를 반환합니다.")
            return FALLBACK_ANALYSIS
        return result
    except Exception:
        logger.warning("의도 분석 중 예외 발생, FALLBACK_ANALYSIS를 반환합니다.", exc_info=True)
        return FALLBACK_ANALYSIS
