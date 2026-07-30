"""카드 후보 생성 — 카탈로그(cards 테이블) 의도/장소 기반 매핑.

기존 Gemini 임시 카드 생성(_generate_llm_cards / LLM FALLBACK_CARDS)을 카탈로그 매핑으로
교체했다. 개인화 가산(count/intent/place 보너스)은 여기가 아니라 personalize.rerank에서 수행한다.
"""
import json
import logging
from pathlib import Path

from app.core.utils import normalize_image_url
from app.repositories import card_repository
from app.schemas.schemas import AnalysisResult, Card, PLACE_LABELS
from app.services.scoring_constants import BASE_RANK_TIERS

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cards_catalog.json"

TOP_N = 8
COMMON_CONTEXT = "공통"


def _load_catalog_cards() -> list[dict]:
    """1차: card_repository(cards 테이블). 실패/빈 결과 시 2차: cards_catalog.json 직접 로드."""
    cards = card_repository.get_cards_for_mapping()
    if cards:
        return cards
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            catalog = json.load(f)
        # 파일 폴백은 DB id가 없으므로 card_id=None. image_url은 DB 시딩 경로와
        # 동일하게 정규화(구글드라이브 보기 링크 -> 임베드 가능한 썸네일)해서 반환.
        for c in catalog:
            c.setdefault("id", None)
            c["image_url"] = normalize_image_url(c.get("image_url"))
        return catalog
    except Exception:
        logger.warning("카탈로그 파일 로드 실패, 빈 후보 반환.", exc_info=True)
        return []


def _tier_for(card: dict, intent, place_active) -> tuple[str, bool]:
    """카드를 4-tier로 분류. (tier_key, included) 반환.

    OR 합집합: card.context==place OR intent in card.valid_for_intents,
    그리고 context=="공통"은 항상 baseline 포함.

    valid_for_intents는 "이 카드가 상대방의 어떤 intent에 대한 응답으로 적절한가"를
    카드마다 직접 태깅한 리스트다. 카탈로그의 intention 필드(카드 자체의 발화 유형 —
    화자가 사용자 자신)와는 축이 다르므로 매칭에 intention을 쓰지 않는다
    (intention==intent로 직접 비교하면 화자가 뒤바뀌어 "되묻는" 카드가 뜨는 문제가 있었음).
    """
    context = card.get("context")
    valid_for_intents = card.get("valid_for_intents") or []
    place_match = bool(place_active) and context == place_active
    intent_match = intent is not None and intent in valid_for_intents
    is_common = context == COMMON_CONTEXT

    if not (place_match or intent_match or is_common):
        return "", False
    if place_match and intent_match:
        return "장소+의도", True
    if place_match:
        return "장소만", True
    if intent_match:
        return "의도만", True
    return "공통", True


def get_candidate_cards(analysis: AnalysisResult, user_id: int, place=None) -> list[Card]:
    """의도/장소 기반 카탈로그 매핑으로 상위 8개 후보 카드를 반환.

    - place가 None/한글 7종 밖/'공통'이면 place 매칭을 조용히 무시(intent+공통만).
    - 조회 실패/빈 결과 시 안전 폴백(빈 리스트) — 예외 전파 금지, /analyze 500 금지.
    - 반환 Card.score = base_rank (개인화 가산은 personalize.rerank에서).
    """
    try:
        intent = analysis.intent if analysis is not None else None
        # 입력 place는 물리적 장소만 유효. '공통'은 baseline 전용 값이라 place 매칭에서 제외.
        place_active = place if (place in PLACE_LABELS and place != COMMON_CONTEXT) else None

        rows = _load_catalog_cards()
        candidates: list[tuple[float, object, str, Card]] = []
        for row in rows:
            tier, included = _tier_for(row, intent, place_active)
            if not included:
                continue
            base_rank = BASE_RANK_TIERS[tier]
            card_id = row.get("id")
            word = row.get("name")
            card = Card(
                word=word,
                category=row.get("category") or "",
                card_id=card_id,
                image_url=row.get("image_url"),
                source="card_db",
                score=base_rank,
            )
            # 정렬 키: base_rank desc, 그다음 결정론적 tie-break(card_id, word).
            sort_id = card_id if card_id is not None else float("inf")
            candidates.append((base_rank, sort_id, word or "", card))

        candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
        return [c[3] for c in candidates[:TOP_N]]
    except Exception:
        logger.warning("get_candidate_cards 실패, 빈 후보 반환. user_id=%s", user_id, exc_info=True)
        return []
