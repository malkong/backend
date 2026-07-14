"""카드 후보 생성 (LLM fallback / 최종적으로 AAC 모듈로 교체될 지점).

교체 범위: 이 파일 내부만 바꾸면 됨 (main.py, schemas.py는 변경 없음).
"""
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import CARD_GENERATION_PROMPT
from schemas import AnalysisResult, Card, GeminiCardList

load_dotenv()

MODEL_NAME = "gemini-3.1-flash-lite"

BASE_RANKS = {0: 1.0, 1: 0.75, 2: 0.5, 3: 0.25, 4: 0.1, 5: 0.05}

FALLBACK_CARDS = [
    Card(id="f1", word="좋아", category="수락", symbol_id=None, source="fallback", score=1.0),
    Card(id="f2", word="싫어", category="거절", symbol_id=None, source="fallback", score=0.75),
    Card(id="f3", word="나중에", category="거절", symbol_id=None, source="fallback", score=0.5),
    Card(id="f4", word="시간", category="질문", symbol_id=None, source="fallback", score=0.25),
    Card(id="f5", word="어디", category="질문", symbol_id=None, source="fallback", score=0.1),
    Card(id="f6", word="응", category="수락", symbol_id=None, source="fallback", score=0.05),
]


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def _generate_llm_cards(analysis: AnalysisResult) -> list[Card]:
    """MVP: Gemini 호출 2번 — {word, category} 리스트를 받아 base_rank 기반 score 부여."""
    client = _get_client()
    prompt = CARD_GENERATION_PROMPT.format(
        intent=analysis.intent,
        intent_detail=analysis.intent_detail,
        easy_meaning=analysis.easy_meaning,
        response_type=analysis.response_type,
    )
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiCardList,
        ),
    )
    result: GeminiCardList = response.parsed
    if result is None or not result.cards:
        return []

    cards: list[Card] = []
    for i, card_base in enumerate(result.cards):
        cards.append(
            Card(
                id=f"c{i + 1}",
                word=card_base.word,
                category=card_base.category,
                symbol_id=None,
                source="llm_fallback",
                score=BASE_RANKS.get(i, 0.05),
            )
        )
    return cards


def get_candidate_cards(analysis: AnalysisResult, user_id: str) -> list[Card]:
    """카드 후보 생성 진입점.

    MVP: LLM 임시 생성 (_generate_llm_cards)
    Final: AAC 팀원 모듈 HTTP 조회로 교체 (이 함수 내부만 변경)

    Exception 발생 또는 빈 배열 반환 시 FALLBACK_CARDS를 반환한다.
    """
    try:
        cards = _generate_llm_cards(analysis)
        if not cards:
            return FALLBACK_CARDS
        return cards
    except Exception:
        return FALLBACK_CARDS
