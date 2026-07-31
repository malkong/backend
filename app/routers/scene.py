import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.scene import SceneHealthResponse, SceneResponse
from app.services import scene_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scene"])

# 글라스 사진이 고해상도일 수 있어 넉넉히 잡되, 무제한 업로드는 막음
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    """업로드를 청크 단위로 읽되 제한을 넘으면 즉시 중단하고 413을 낸다.

    한 번에 read()하면 제한을 넘는 파일도 일단 전부 메모리에 올리게 된다.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"이미지가 너무 큽니다. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB까지 가능합니다.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/scene", response_model=SceneResponse)
async def scene(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """사진에서 장소를 인식한다. 반환하는 context는 /analyze의 place로 그대로 쓸 수 있다.

    AI 서버 장애(미기동/타임아웃/5xx)나 알 수 없는 scene 값이면 500 대신 200 +
    context=null을 반환한다 — 앱은 그 경우 "장소 직접 선택" 화면으로 넘어간다.
    """
    data = await _read_limited(file)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 파일입니다.",
        )
    try:
        result = await scene_service.predict_scene(file.filename, file.content_type, data)
    except scene_service.SceneUpstreamError as e:
        # 415/400은 사용자 입력 문제이므로 그대로 전달한다.
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
    return SceneResponse(**result)


@router.get("/scene/health", response_model=SceneHealthResponse)
async def scene_health():
    """AI 서버 연동 상태 확인(데모 전 점검용). 인증 불필요."""
    return SceneHealthResponse(**await scene_service.check_ai_server())
