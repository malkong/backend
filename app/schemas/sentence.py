"""POST /sentence 요청/응답 모델."""
from typing import Optional

from pydantic import BaseModel


class SentenceRequest(BaseModel):
    """카드 단어들을 문장으로 조합해 달라는 요청.

    words 검증(빈 배열/공백뿐/개수 초과)은 라우터에서 한다 — 여기서 Field 제약으로
    막으면 FastAPI가 400이 아니라 422를 반환하는데, 앱과의 계약은 400이다.
    """

    words: list[str]
    # 장소(예: "약국"). 없을 수 있고, PLACE_LABELS에 없는 값이 와도 막지 않는다
    # (참고 정보로만 프롬프트에 넣기 때문에 422로 요청을 깨뜨릴 이유가 없다).
    context: Optional[str] = None


class SentenceResponse(BaseModel):
    """항상 200 + 쓸 수 있는 문장. LLM이 실패하면 나열 문장이 담긴다."""

    sentence: str
