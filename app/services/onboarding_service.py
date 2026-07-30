import logging

from app.models.user import User
from app.repositories import card_repository, history_repository
from app.schemas.onboarding import OnboardingRequest

logger = logging.getLogger(__name__)

# cards.context에는 있지만 "자주 가는 곳" 선택지로는 부적절한 값.
# personalize.rerank도 "공통"은 place 매칭에서 제외하므로 온보딩해도 place 보너스가 없다.
COMMON_CONTEXT = "공통"


class OnboardingError(Exception):
    """온보딩 도메인 예외의 베이스."""


class AlreadyOnboardedError(OnboardingError):
    """이미 온보딩을 마친 유저가 재실행을 시도한 경우."""


class InvalidAnswerError(OnboardingError):
    """context 값이 유효하지 않거나 존재하지 않는 card_id가 포함된 경우."""


def list_contexts() -> list[str]:
    """온보딩 Step 1에서 고를 수 있는 장소 목록. '공통'은 장소가 아니라 제외한다."""
    return [c for c in card_repository.get_contexts() if c != COMMON_CONTEXT]


def submit(user: User, request: OnboardingRequest) -> int:
    """온보딩 답변을 저장하고 기록된 카드 수를 반환한다.

    - 이미 온보딩된 유저면 AlreadyOnboardedError.
    - context가 선택 가능한 장소 목록에 없거나, 존재하지 않는 card_id가 있으면 InvalidAnswerError.
    - card_id 중복은 제거한다(요청 전체 기준, 처음 나온 context를 place로 쓴다).
      같은 카드를 두 번 세면 count가 8이 되어 의도한 "초기값 4"가 깨지기 때문이다.
    """
    if user.is_onboarded:
        raise AlreadyOnboardedError(user.id)

    if not request.answers:
        raise InvalidAnswerError("answers가 비어 있습니다.")
    empty = [a.context for a in request.answers if not a.cardIds]
    if empty:
        raise InvalidAnswerError(f"cardIds가 비어 있는 context: {sorted(set(empty))}")

    valid_contexts = set(list_contexts())
    if not valid_contexts:
        # cards 조회 자체가 실패한 상황 — 검증할 기준이 없으므로 저장하지 않는다.
        raise InvalidAnswerError("선택 가능한 장소 목록을 불러오지 못했습니다.")

    # context 검증
    bad_contexts = [a.context for a in request.answers if a.context not in valid_contexts]
    if bad_contexts:
        raise InvalidAnswerError(f"유효하지 않은 context: {sorted(set(bad_contexts))}")

    # card_id 중복 제거 — 처음 등장한 context를 place로 사용
    place_by_card: dict[int, str] = {}
    for answer in request.answers:
        for card_id in answer.cardIds:
            place_by_card.setdefault(card_id, answer.context)

    requested_ids = list(place_by_card)
    found = {c["id"]: c for c in card_repository.get_cards_by_ids(requested_ids)}
    unknown = [cid for cid in requested_ids if cid not in found]
    if unknown:
        raise InvalidAnswerError(f"존재하지 않는 card_id: {sorted(unknown)}")

    items = [
        {
            "card_id": cid,
            "word": found[cid]["name"],
            "category": found[cid]["category"],
            "place": place_by_card[cid],
        }
        for cid in requested_ids
    ]

    ok = history_repository.record_onboarding(user.id, items)
    if not ok:
        # is_onboarded 가드에 걸렸거나(동시 요청) DB 연결 실패.
        raise AlreadyOnboardedError(user.id)

    logger.info("온보딩 완료: user_id=%s, 카드 %d장", user.id, len(items))
    return len(items)
