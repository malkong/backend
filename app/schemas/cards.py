from typing import Optional

from pydantic import BaseModel


class CatalogCard(BaseModel):
    """cards 테이블의 카드 한 장 (온보딩 선택지 / 카드 목록 조회용)."""

    card_id: int
    name: str
    category: str
    context: str
    image_url: Optional[str] = None


class ContextsResponse(BaseModel):
    contexts: list[str]


class CardListResponse(BaseModel):
    context: str
    cards: list[CatalogCard]
