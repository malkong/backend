from pydantic import BaseModel


class OnboardingAnswer(BaseModel):
    context: str
    # "각 context마다 최소 1개" 검증은 onboarding_service에서 수행한다.
    # Pydantic의 min_length에 맡기면 422가 나가는데, 명세상 이 경우는 400이어야 한다.
    cardIds: list[int]


class OnboardingRequest(BaseModel):
    answers: list[OnboardingAnswer]


class OnboardingResponse(BaseModel):
    ok: bool
    isOnboarded: bool
    # 중복 제거 후 실제로 기록된 카드 수
    savedCards: int
