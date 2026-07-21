"""Pydantic 요청/응답 모델 (Week 1: /health, /analyze 관련)"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

INTENT_LABELS = ("인사", "질문", "요청", "제안", "정보_전달", "감정_표현", "확인", "기타")


class DialogueTurn(BaseModel):
    speaker: str
    text: str


class AnalyzeRequest(BaseModel):
    user_id: str
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
    """Gemini가 반환하는 카드 원본 형태 (word, category만)"""
    word: str
    category: str


class GeminiCardList(BaseModel):
    """Gemini response_schema용 래퍼"""
    cards: list[CardBase]


class Card(BaseModel):
    """card_generator.py가 id/symbol_id/source/score를 부여한 최종 카드"""
    id: str
    word: str
    category: str
    symbol_id: Optional[str] = None
    source: str
    score: float


class AnalyzeResponse(BaseModel):
    analysis: AnalysisResult
    cards: list[Card]


class TranscribeResponse(BaseModel):
    speech_text: str
    language: str
    duration_sec: float
