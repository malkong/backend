"""개인화 점수식 공유 상수 (card_generator.py와 personalize.py가 함께 참조).

두 파일에 흩어진 상수가 프로즈로만 맞물려 향후 한쪽만 수정될 때 조용히 깨지는 위험을
제거하기 위한 단일 소스. rev5 Architect/Critic 합의 산출물.
"""

# base_rank 4-tier (rev5 확정). 개인화 이력이 없을 때의 tie-breaker.
# 냉시작 콜드스타트용 큰 기본값이 아니라, tier 간 상대 순서만 결정한다.
BASE_RANK_TIERS = {
    "공통": 0.0,
    "의도만": 0.30,
    "장소만": 0.50,
    "장소+의도": 0.70,
}

# 개인화 가산 가중치 (rev4에서 변경 없이 재사용).
COUNT_WEIGHT = 0.08
INTENT_WEIGHT = 0.05
PLACE_WEIGHT = 0.05

# count 항 상한 — 전역 인기도(count)만 클램프. intent/place 보너스는 무상한(의도적).
COUNT_BONUS_CAP = 0.64

# ⚠️ 핵심 불변식(load-bearing): 순수 인기도(count만 cap까지 누적)가 장소+의도 tier를
# 절대 역전하지 못하도록 cap < 장소+의도 tier여야 한다. 이 부등식이 personalize.py의
# 상황별 개인화 전체를 지탱한다 — cap을 0.70 이상으로 올리면 rev4가 막으려던 결함이 재발한다.
assert COUNT_BONUS_CAP < BASE_RANK_TIERS["장소+의도"], (
    "COUNT_BONUS_CAP must stay below the 장소+의도 base_rank tier so pure popularity "
    "can never permanently outrank a full context match "
    f"(cap={COUNT_BONUS_CAP}, 장소+의도={BASE_RANK_TIERS['장소+의도']})."
)
