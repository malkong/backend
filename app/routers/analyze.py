"""POST /analyze — 의도분석 + 카탈로그 매핑 + 개인화 재정렬."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import personalize
from app.services.card_generator import get_candidate_cards
from app.services.llm import analyze_intent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])


def _extract_place(visual_context):
    if isinstance(visual_context, dict):
        return visual_context.get("place")
    return None


@router.post("/analyze", response_model=AnalyzeResponse)
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
