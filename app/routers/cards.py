"""POST /select, GET /profile/{user_id} — 카드 선택 기록 및 개인화 프로필 조회.

TODO(2차 리팩터링): 이 라우터는 repositories를 직접 호출한다(Controller -> Repository).
    /analyze가 services를 거치는 것과 달리 서비스 계층을 건너뛰고 있는데, 기존
    main.py의 구조를 그대로 옮긴 결과다. 2차에서 services/에 선택 기록·프로필
    조회 유스케이스를 만들어 그쪽을 경유하도록 정리한다.
"""
from fastapi import APIRouter

from app.repositories import history_repository
from app.schemas.schemas import ProfileResponse, SelectRequest, SelectResponse

router = APIRouter(tags=["cards"])


@router.post("/select", response_model=SelectResponse)
def select(request: SelectRequest):
    # DB 쓰기 실패 시에도 200 + {ok:false, new_count:0} (graceful degradation, 500 금지).
    ok, new_count = history_repository.record_selection(
        request.user_id, request.card, request.context
    )
    return SelectResponse(ok=ok, new_count=new_count)


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def profile(user_id: int):
    top_cards = history_repository.get_top_cards(user_id)
    return ProfileResponse(user_id=user_id, top_cards=top_cards)
