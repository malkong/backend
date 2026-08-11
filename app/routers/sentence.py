"""POST /sentence — 고른 카드 단어들을 자연스러운 한국어 문장으로 조합.

앱은 지금까지 카드 이름을 ". "로 이어 붙여 "소화제. 얼마예요?"처럼 읽어줬다.
이 엔드포인트는 그걸 "소화제는 얼마예요?"로 다듬어 준다.

graceful degradation: LLM이 죽어도 500을 내지 않고 200 + 나열 문장을 반환한다
(/scene이 AI 서버 장애 때 200 + context=null을 반환하는 것과 같은 원칙).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.sentence import SentenceRequest, SentenceResponse
from app.services.llm import make_sentence

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sentence"])

# 프롬프트 남용 방지. AAC 한 문장에 카드 20장을 고르는 경우는 없다.
MAX_WORDS = 20


@router.post("/sentence", response_model=SentenceResponse)
def sentence(request: SentenceRequest, user: User = Depends(get_current_user)):
    """words(고른 순서 그대로)를 한 문장으로 만들어 반환한다.

    400은 입력 자체가 문장이 될 수 없는 경우뿐이다. LLM 실패는 400도 500도 아닌
    200 + 나열 문장이다.
    """
    if not request.words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="words는 1개 이상이어야 합니다.",
        )
    if len(request.words) > MAX_WORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"단어는 최대 {MAX_WORDS}개까지 가능합니다.",
        )

    words = [w.strip() for w in request.words if w and w.strip()]
    if not words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="words에 빈 문자열만 있습니다.",
        )

    return SentenceResponse(sentence=make_sentence(words, request.context))
