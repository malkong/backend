from typing import Optional

from pydantic import BaseModel


class SceneResponse(BaseModel):
    """장면 인식 결과.

    context는 /analyze의 place 파라미터로 그대로 넘길 수 있는 한글 값이다
    (cards.context / PLACE_LABELS와 동일 도메인).

    인식에 실패해도 앱이 멈추면 안 되므로 200으로 응답하고 context=null, error에
    사유를 담는다. 앱은 context가 null이면 "장소 직접 선택" 화면으로 넘어간다.
    """

    context: Optional[str] = None
    score: Optional[float] = None
    error: Optional[str] = None


class SceneHealthResponse(BaseModel):
    """AI 서버 연동 상태(데모 전 점검용)."""

    aiServer: str
    reachable: bool
    detail: Optional[str] = None
