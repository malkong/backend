"""POST /select, GET /profile/me — 카드 선택 기록 및 개인화 프로필 조회.

user_id는 요청 값이 아니라 Authorization 토큰에서 얻는다. 예전에는 클라이언트가
보낸 user_id를 그대로 신뢰해서, 숫자만 바꾸면 남의 프로필을 읽거나 남의 이력에
기록할 수 있었다.

TODO(2차 리팩터링): 이 라우터는 repositories를 직접 호출한다(Controller -> Repository).
    /analyze가 services를 거치는 것과 달리 서비스 계층을 건너뛰고 있는데, 기존
    main.py의 구조를 그대로 옮긴 결과다. 2차에서 services/에 선택 기록·프로필
    조회 유스케이스를 만들어 그쪽을 경유하도록 정리한다.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_current_user
from app.models.user import User
from app.repositories import card_repository, history_repository
from app.schemas.cards import CardListResponse, CatalogCard, ContextsResponse
from app.schemas.schemas import ProfileResponse, SelectRequest, SelectResponse
from app.services import onboarding_service

router = APIRouter(tags=["cards"])


@router.get("/cards/contexts", response_model=ContextsResponse)
def contexts():
    """온보딩 Step 1용 장소 목록. cards 테이블의 실제 값에서 읽는다(하드코딩 아님)."""
    return ContextsResponse(contexts=onboarding_service.list_contexts())


@router.get("/cards", response_model=CardListResponse)
def cards(context: str = Query(..., description="cards.context 값 (예: 병원)")):
    rows = card_repository.get_cards_by_context(context)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"해당 context의 카드가 없습니다: {context}",
        )
    return CardListResponse(
        context=context,
        cards=[
            CatalogCard(
                card_id=r["id"],
                name=r["name"],
                category=r["category"],
                context=r["context"],
                image_url=r.get("image_url"),
            )
            for r in rows
        ],
    )


@router.post("/select", response_model=SelectResponse)
def select(request: SelectRequest, user: User = Depends(get_current_user)):
    # DB 쓰기 실패 시에도 200 + {ok:false, results:[]} (graceful degradation, 500 금지).
    # request.cards는 SelectRequest의 model_validator가 항상 채워둔다(card 단수 호출도 정규화됨).
    ok, results = history_repository.record_selection(
        user.id, request.cards, request.context
    )
    # 하위호환: 카드가 정확히 1장일 때만 new_count를 상위 필드에도 채운다(옛 단일-카드
    # 호출자가 여전히 이 필드를 읽을 수 있게). 여러 장이면 모호하므로 results만 채운다.
    new_count = results[0]["new_count"] if len(results) == 1 else None
    return SelectResponse(ok=ok, new_count=new_count, results=results)


@router.get("/profile/me", response_model=ProfileResponse)
def profile(user: User = Depends(get_current_user)):
    top_cards = history_repository.get_top_cards(user.id)
    return ProfileResponse(user_id=user.id, top_cards=top_cards)
