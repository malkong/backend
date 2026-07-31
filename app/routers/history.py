from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from app.models.user import User
from app.repositories import history_repository
from app.schemas.history import HistoryItem, HistoryResponse

router = APIRouter(tags=["history"])


@router.get("/history/me", response_model=HistoryResponse)
def history_me(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """내 사용 이력을 최신순으로 반환한다. 온보딩으로 심어진 행은 제외된다."""
    rows = history_repository.get_history(user.id, limit=limit, offset=offset)
    return HistoryResponse(
        items=[
            HistoryItem(
                word=r["word"],
                place=r.get("place"),
                cardId=r["card_id"],
                imageUrl=r.get("image_url"),
                selectedAt=r.get("selected_at"),
            )
            for r in rows
        ]
    )
