"""카드 후보 생성 — 카탈로그(cards 테이블) 의도/장소 기반 매핑.

기존 Gemini 임시 카드 생성(_generate_llm_cards / LLM FALLBACK_CARDS)을 카탈로그 매핑으로
교체했다. 개인화 가산(count/intent/place 보너스)은 여기가 아니라 personalize.rerank에서 수행한다.
"""
import json
import logging
from pathlib import Path

from app.schemas.schemas import AnalysisResult, Card, PLACE_LABELS
from app.services import storage
from app.services.storage import _normalize_image_url
from app.services.scoring_constants import BASE_RANK_TIERS

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cards_catalog.json"

TOP_N = 8
COMMON_CONTEXT = "공통"

# 상대방 발화 intent -> 응답으로도 적합한 카드 intention 값(들).
# 카탈로그의 intention은 "카드 자체의 발화 유형"이라 intent와 완전일치하는 카드가
# 극히 적은 intent(제안=1장, 인사=0장 등)가 있다. 이 표는 그런 경우에도 "의도만" tier가
# 텅 비지 않도록 직접일치(intention==intent)에 보조로 더하는 curated 확장 매칭이다.
# (직접일치는 그대로 최우선 유지, 이 표는 additive.)
RESPONSE_INTENTION_MAP = {
    "인사": ["확인"],
    "질문": ["질문", "확인"],
    "요청": ["확인"],
    "제안": ["확인"],
    "정보_전달": ["확인"],
    "감정_표현": ["확인"],
    "확인": ["확인"],
    "기타": [],
}


def _load_catalog_cards() -> list[dict]:
    """1차: storage(cards 테이블). 실패/빈 결과 시 2차: cards_catalog.json 직접 로드."""
    cards = storage.get_cards_for_mapping()
    if cards:
        return cards
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            catalog = json.load(f)
        # 파일 폴백은 DB id가 없으므로 card_id=None. image_url은 DB 시딩 경로와
        # 동일하게 정규화(구글드라이브 보기 링크 -> 임베드 가능한 썸네일)해서 반환.
        for c in catalog:
            c.setdefault("id", None)
            c["image_url"] = _normalize_image_url(c.get("image_url"))
        return catalog
    except Exception:
        logger.warning("카탈로그 파일 로드 실패, 빈 후보 반환.", exc_info=True)
        return []


def _tier_for(card: dict, intent, place_active) -> tuple[str, bool]:
    """카드를 4-tier로 분류. (tier_key, included) 반환.

    OR 합집합: card.context==place OR card.intention==intent(또는 RESPONSE_INTENTION_MAP
    보조 매칭), 그리고 context=="공통"은 항상 baseline 포함.
    """
    context = card.get("context")
    intention = card.get("intention")
    place_match = bool(place_active) and context == place_active
    direct_intent_match = intent is not None and intention is not None and intention == intent
    response_intent_match = (
        intent is not None
        and intention is not None
        and intention in RESPONSE_INTENTION_MAP.get(intent, ())
    )
    intent_match = direct_intent_match or response_intent_match
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
