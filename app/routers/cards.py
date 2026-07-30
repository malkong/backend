"""POST /select, GET /profile/me — 카드 선택 기록 및 개인화 프로필 조회.

user_id는 요청 값이 아니라 Authorization 토큰에서 얻는다. 예전에는 클라이언트가
보낸 user_id를 그대로 신뢰해서, 숫자만 바꾸면 남의 프로필을 읽거나 남의 이력에
기록할 수 있었다.

TODO(2차 리팩터링): 이 라우터는 repositories를 직접 호출한다(Controller -> Repository).
    /analyze가 services를 거치는 것과 달리 서비스 계층을 건너뛰고 있는데, 기존
    main.py의 구조를 그대로 옮긴 결과다. 2차에서 services/에 선택 기록·프로필
    조회 유스케이스를 만들어 그쪽을 경유하도록 정리한다.
"""
from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.user import User
from app.repositories import history_repository
from app.schemas.schemas import ProfileResponse, SelectRequest, SelectResponse

router = APIRouter(tags=["cards"])


@router.post("/select", response_model=SelectResponse)
def select(request: SelectRequest, user: User = Depends(get_current_user)):
    # DB 쓰기 실패 시에도 200 + {ok:false, new_count:0} (graceful degradation, 500 금지).
    ok, new_count = history_repository.record_selection(
        user.id, request.card, request.context
    )
    return SelectResponse(ok=ok, new_count=new_count)


@router.get("/profile/me", response_model=ProfileResponse)
def profile(user: User = Depends(get_current_user)):
    top_cards = history_repository.get_top_cards(user.id)
    return ProfileResponse(user_id=user.id, top_cards=top_cards)
