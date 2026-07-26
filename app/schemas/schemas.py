"""Pydantic 요청/응답 모델 (/health, /analyze, /select, /profile 관련)"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

INTENT_LABELS = ("인사", "질문", "요청", "제안", "정보_전달", "감정_표현", "확인", "기타")

# place 라벨 = 한글 7종. cards.context / usage_log.place / visual_context.place 공통 도메인.
# (입력 place로는 실측상 물리적 6종만 오지만, "공통"은 카드 컨텍스트 baseline 값이므로 도메인에 포함.)
PLACE_LABELS = ("공통", "식당", "병원", "카페", "대중교통", "편의점", "약국")
PlaceLabel = Literal["공통", "식당", "병원", "카페", "대중교통", "편의점", "약국"]


class DialogueTurn(BaseModel):
    speaker: str
    text: str


class AnalyzeRequest(BaseModel):
    user_id: int
    speech_text: str
    dialogue_history: Optional[list[DialogueTurn]] = None
    visual_context: Optional[dict] = None


class AnalysisResult(BaseModel):
    intent: Literal["인사", "질문", "요청", "제안", "정보_전달", "감정_표현", "확인", "기타"]
    intent_detail: str
    easy_meaning: str
    response_type: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class CardBase(BaseModel):
    """Gemini가 반환하는 카드 원본 형태 (word, category만) — 의도 분석 프롬프트 잔여 스키마."""
    word: str
    category: str


class GeminiCardList(BaseModel):
    """Gemini response_schema용 래퍼 (현재 미사용, 하위호환 유지)."""
    cards: list[CardBase]


class Card(BaseModel):
    """카탈로그 매핑 + 개인화가 부여한 최종 카드.

    score는 card_generator 단계에서 base_rank로 세팅되고, personalize.rerank에서
    개인화 가산 점수로 덮어써진다(rerank는 입력 score를 base_rank로 취급).
    """
    word: str
    category: str
    card_id: Optional[int] = None
    image_url: Optional[str] = None
    source: str
    score: float


class AnalyzeResponse(BaseModel):
    analysis: AnalysisResult
    cards: list[Card]


class TranscribeResponse(BaseModel):
    speech_text: str
    language: str
    duration_sec: float


# ---- /select ----
class SelectCard(BaseModel):
    word: str
    category: Optional[str] = None
    card_id: Optional[int] = None  # 없으면 NULL 저장 (문자열 더미 금지)


class SelectContext(BaseModel):
    intent: Optional[str] = None
    place: Optional[PlaceLabel] = None  # 한글 7종, 미지원/미기록이면 생략


class SelectRequest(BaseModel):
    user_id: int
    card: SelectCard
    context: Optional[SelectContext] = None


class SelectResponse(BaseModel):
    ok: bool
    new_count: int


# ---- /profile ----
class ProfileCard(BaseModel):
    word: str
    category: Optional[str] = None
    count: int
    card_id: Optional[int] = None  # nullable


class ProfileResponse(BaseModel):
    user_id: int
    top_cards: list[ProfileCard]
