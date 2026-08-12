from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HistoryItem(BaseModel):
    """사용 이력 한 줄 = 카드 한 장을 고른 사건 하나."""

    word: str
    place: Optional[str] = None
    cardId: int
    imageUrl: Optional[str] = None
    selectedAt: Optional[datetime] = None


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
