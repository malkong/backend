import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# AI 서버가 반환하는 영문 라벨 -> 이 백엔드의 한글 place 값. 나중에 백엔드 cards 테이블 context값도 다 영어로 바꾸기...
# ("공통"은 AI가 반환하지 않고 place 매칭에서도 제외되는 baseline이라 매핑 대상이 아니다.) <- 공통 값 어케 처리할지 논의 필요(모든 응답에 공통은 포함시킨다든가........)
SCENE_TO_CONTEXT = {
    "Cafe": "카페",
    "Convenience Store": "편의점",
    "Hospital": "병원",
    "Pharmacy": "약국",
    "Public Transport": "대중교통",
    "Restaurant": "식당",
}

RECOGNITION_FAILED = "장소 인식 실패"


class SceneUpstreamError(Exception):
    """AI 서버가 사용자 입력 문제로 4xx를 반환한 경우(415/400).

    이건 서버 장애가 아니라 앱이 보낸 파일 자체의 문제라, 폴백으로 삼키지 않고
    같은 상태코드로 그대로 전달한다.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def predict_scene(filename: str, content_type: str | None, data: bytes) -> dict:
    """AI 서버 /predict에 이미지를 전달하고 한글 context로 변환해 반환한다.

    반환: {"context": str|None, "score": float|None, "error": str|None}

    아래는 모두 폴백(200 + context=None)으로 처리한다 — AI 서버가 죽어도 앱이
    멈추면 안 되기 때문이다:
      - 연결 실패(서버 미기동), 타임아웃
      - AI 서버 5xx
      - 매핑표에 없는 scene 값
      - 응답 JSON 형식이 예상과 다름
    415/400만 SceneUpstreamError로 올려보내 그대로 전달한다.
    """
    url = settings.AI_SERVER_URL.rstrip("/") + "/predict"
    files = {"file": (filename or "upload", data, content_type or "application/octet-stream")}

    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVER_TIMEOUT) as client:
            resp = await client.post(url, files=files)
    except httpx.TimeoutException:
        logger.warning("AI 서버 타임아웃(%.1fs): %s", settings.AI_SERVER_TIMEOUT, url)
        return _failed()
    except httpx.RequestError as e:
        # 연결 거부, DNS 실패 등 — AI 서버가 안 떠 있는 경우가 대부분.
        logger.warning("AI 서버 연결 실패(%s): %s", type(e).__name__, url)
        return _failed()

    if resp.status_code in (400, 415):
        logger.info("AI 서버가 %s 반환 — 사용자 입력 문제로 그대로 전달.", resp.status_code)
        raise SceneUpstreamError(
            resp.status_code,
            "이미지 형식이 올바르지 않습니다." if resp.status_code == 415 else "이미지 파일이 손상되었습니다.",
        )

    if resp.status_code >= 500:
        logger.warning("AI 서버 5xx(%s).", resp.status_code)
        return _failed()

    if resp.status_code != 200:
        logger.warning("AI 서버 예상 밖 상태코드(%s).", resp.status_code)
        return _failed()

    try:
        body = resp.json()
        scene = body["scene"]
        score = body["score"]
    except Exception:
        logger.warning("AI 서버 응답 파싱 실패.", exc_info=True)
        return _failed()

    context = SCENE_TO_CONTEXT.get(scene)
    if context is None:
        # 매핑표에 없는 값 — AI 모델이 갱신됐거나 오타. 임의로 추측하지 않는다.
        logger.warning("매핑표에 없는 scene 값을 받았습니다: %r", scene)
        return _failed()

    return {"context": context, "score": score, "error": None}


async def check_ai_server() -> dict:
    """AI 서버 /health 호출 결과. 데모 전 연동 점검용."""
    url = settings.AI_SERVER_URL.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVER_TIMEOUT) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return {"aiServer": settings.AI_SERVER_URL, "reachable": False, "detail": "타임아웃"}
    except httpx.RequestError as e:
        return {
            "aiServer": settings.AI_SERVER_URL,
            "reachable": False,
            "detail": f"연결 실패({type(e).__name__})",
        }
    if resp.status_code != 200:
        return {
            "aiServer": settings.AI_SERVER_URL,
            "reachable": False,
            "detail": f"HTTP {resp.status_code}",
        }
    return {"aiServer": settings.AI_SERVER_URL, "reachable": True, "detail": "ok"}


def _failed() -> dict:
    return {"context": None, "score": None, "error": RECOGNITION_FAILED}
