"""개인화 재정렬 (선택 이력 기반 점수 가산).

점수식: score = base_rank + min(COUNT_WEIGHT×count, COUNT_BONUS_CAP)
                 + INTENT_WEIGHT×intent_match_count + PLACE_WEIGHT×place_match_count
가중치/상한/tier 값은 scoring_constants.py 단일 소스에서 import(하드코딩 금지).

graceful degradation: storage 조회 실패 시 모든 보너스 0 → 원본 base_rank 순서 유지, 예외 전파 금지.
"""
import logging

from app.schemas.schemas import Card, PLACE_LABELS
from app.services import storage
from app.services.scoring_constants import (
    COUNT_BONUS_CAP,
    COUNT_WEIGHT,
    INTENT_WEIGHT,
    PLACE_WEIGHT,
)

logger = logging.getLogger(__name__)

COMMON_CONTEXT = "공통"


def rerank(cards: list[Card], user_id: int, intent=None, place=None) -> list[Card]:
    """개인화 점수로 카드를 재정렬. 입력 card.score를 base_rank로 취급한다.

    - place가 None/한글 7종 밖/'공통'이면 place 보너스 미적용(unknown끼리 매칭 금지).
    - storage 실패 시 보너스 0으로 원본 순서 유지, 500 없이 원본 반환.
    """
    if not cards:
        return cards
    place_active = place if (place in PLACE_LABELS and place != COMMON_CONTEXT) else None
    try:
        scored: list[tuple[float, object, str, Card]] = []
        for card in cards:
            base_rank = card.score  # card_generator가 base_rank로 세팅
            counts = storage.get_usage_counts(user_id, card.word, intent, place_active)
            count = counts.get("count", 0)
            intent_match = counts.get("intent_match_count", 0)
            place_match = counts.get("place_match_count", 0)

            score = (
                base_rank
                + min(COUNT_WEIGHT * count, COUNT_BONUS_CAP)
                + INTENT_WEIGHT * intent_match
                + PLACE_WEIGHT * place_match
            )
            card.score = score
            # 결정론적 2차 정렬 키: card_id(없으면 inf), 그다음 word.
            sort_id = card.card_id if card.card_id is not None else float("inf")
            scored.append((score, sort_id, card.word or "", card))

        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        return [t[3] for t in scored]
    except Exception:
        logger.warning(
            "rerank 실패, 개인화 생략하고 원본 순서 반환. user_id=%s", user_id, exc_info=True
        )
        return cards
