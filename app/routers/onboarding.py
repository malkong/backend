from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.services import onboarding_service

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding", response_model=OnboardingResponse)
def onboarding(request: OnboardingRequest, user: User = Depends(get_current_user)):
    try:
        saved = onboarding_service.submit(user, request)
    except onboarding_service.AlreadyOnboardedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 온보딩을 완료한 계정입니다.",
        ) from None
    except onboarding_service.InvalidAnswerError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    return OnboardingResponse(ok=True, isOnboarded=True, savedCards=saved)
