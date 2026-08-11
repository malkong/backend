"""Gemini 의도 분석 호출 (llm.py). /transcribe(STT)는 3주차에 추가."""
import logging
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.prompts import ANALYZE_PROMPT, SENTENCE_NO_CONTEXT, SENTENCE_PROMPT
from app.schemas.schemas import AnalysisResult

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.1-flash-lite"

# Gemini API는 10초 미만 deadline을 거부한다:
#   400 INVALID_ARGUMENT "Manually set deadline 1s is too short. Minimum allowed deadline is 10s."
# 즉 SENTENCE_TIMEOUT을 10초 미만으로 두면 타임아웃이 빨라지는 게 아니라 매 호출이
# 400으로 떨어져 항상 나열 문장만 나온다. 앱은 안 죽지만 문장 다듬기가 통째로 꺼진다.
GEMINI_MIN_TIMEOUT_SEC = 10.0

if settings.SENTENCE_TIMEOUT < GEMINI_MIN_TIMEOUT_SEC:
    logger.warning(
        "SENTENCE_TIMEOUT=%.1fs는 Gemini 최소 deadline(%.0fs) 미만이라 /sentence가 "
        "매번 나열 문장으로 폴백합니다. .env를 확인하세요.",
        settings.SENTENCE_TIMEOUT,
        GEMINI_MIN_TIMEOUT_SEC,
    )

FALLBACK_ANALYSIS = AnalysisResult(
    intent="기타",
    intent_detail="분석에 실패해 기본값을 반환합니다.",
    easy_meaning="무슨 말인지 다시 한 번 확인이 필요해요.",
    response_type=["accept", "refuse", "question"],
    confidence=0.0,
)

# Mode 1(사진만 있고 상대방 발화가 없는 경우): 앱이 speech_text=""로 /analyze를 호출한다.
# 실패가 아니라 정상 경로이므로 FALLBACK_ANALYSIS와는 별개 상수를 쓴다.
EMPTY_SPEECH_ANALYSIS = AnalysisResult(
    intent="기타",
    intent_detail="",
    easy_meaning="",
    response_type=[],
    confidence=0.0,
)


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def analyze_intent(speech_text: str) -> AnalysisResult:
    """Gemini 호출 1번: speech_text를 분석해 intent 5필드(AnalysisResult)를 반환.

    speech_text가 비었거나 공백뿐이면(Mode 1: 사진만 있고 상대방 발화가 없는 경우)
    Gemini를 호출하지 않고 EMPTY_SPEECH_ANALYSIS를 즉시 반환한다 — 분석할 발화가
    없는데 매번 10~15초짜리 API 호출을 하는 건 낭비이고, 어차피 결과는 항상
    intent="기타"였다.

    Gemini 호출 실패(키 없음/네트워크 오류/파싱 오류 등) 시에도 서버가 죽지 않도록
    FALLBACK_ANALYSIS를 반환한다.
    """
    if not speech_text or not speech_text.strip():
        return EMPTY_SPEECH_ANALYSIS
    try:
        client = _get_client()
        prompt = ANALYZE_PROMPT.format(speech_text=speech_text)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalysisResult,
            ),
        )
        result = response.parsed
        if result is None:
            logger.warning("Gemini 응답 파싱 결과가 없어 FALLBACK_ANALYSIS를 반환합니다.")
            return FALLBACK_ANALYSIS
        return result
    except Exception:
        logger.warning("의도 분석 중 예외 발생, FALLBACK_ANALYSIS를 반환합니다.", exc_info=True)
        return FALLBACK_ANALYSIS


_HAS_LETTER = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z]")


def _is_bare_number(words: list[str]) -> bool:
    """카드가 딱 하나이고 글자 없이 숫자·기호뿐인가("119", "010-1234-5678").

    이 경우 Gemini를 호출하지 않는다. 프롬프트로 "그대로 두라"고 못박아도 모델이
    존댓말 규칙과 충돌시켜 "119입니다."를 만들어냈다 — 응급 번호에 없던 서술어가
    붙는 건 이 API에서 가장 피해야 할 실패다. 게다가 조합할 게 없어 호출 자체가
    낭비다(analyze_intent가 빈 speech_text에 Gemini를 건너뛰는 것과 같은 이유).
    """
    return len(words) == 1 and not _HAS_LETTER.search(words[0])


def fallback_sentence(words: list[str]) -> str:
    """LLM 없이 만드는 나열 문장. 앱이 지금까지 직접 만들던 형태와 같다."""
    return ". ".join(words)


def _clean_sentence(raw: str, fallback: str) -> str | None:
    """LLM 원문에서 쓸 수 있는 문장만 남긴다. 못 쓰겠으면 None.

    설명이 붙어 오는 경우는 대부분 문장 뒤에 줄바꿈 후 설명이 오는 형태라 첫 줄만 취한다.
    "첫 문장만 취한다"로 자르지 않는 이유: ["봉투에 담아주세요", "얼마예요?"]처럼
    완성 문장 카드가 섞이면 두 문장으로 이어 붙이는 게 오히려 정답이라(프롬프트
    요건), 문장 단위로 자르면 사용자가 고른 카드를 통째로 잃는다. 대신 길이로
    거른다 — 나열 문장보다 지나치게 길면 문장이 아니라 설명이다.
    """
    text = raw.strip()
    if not text:
        return None

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return None

    # 모델이 종종 문장을 따옴표로 감싼다. 짝이 맞을 때만 벗긴다.
    for open_q, close_q in (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」")):
        if len(first_line) >= 2 and first_line.startswith(open_q) and first_line.endswith(close_q):
            first_line = first_line[1:-1].strip()
            break

    if not first_line:
        return None

    # 나열 문장 대비 지나치게 길면 문장이 아니라 설명·부연으로 본다.
    if len(first_line) > max(len(fallback) * 2, len(fallback) + 30):
        return None

    return first_line


def make_sentence(words: list[str], context: str | None = None) -> str:
    """카드 단어들을 자연스러운 한 문장으로 조합한다.

    words는 사용자가 고른 순서 그대로이며, 호출 전에 공백만 있는 원소는 걸러져
    있어야 한다(라우터에서 400으로 막는다).

    카드가 숫자 하나뿐이면("119") Gemini를 호출하지 않고 그대로 반환한다.

    실패하면 예외를 올리지 않고 나열 문장(". ".join(words))을 반환한다 — 이 API가
    죽어도 앱은 쓸 수 있는 문장을 받아야 하기 때문이다. 폴백 대상:
      - GEMINI_API_KEY 없음 / 네트워크 오류 / Gemini 5xx
      - 타임아웃(.env의 SENTENCE_TIMEOUT, 기본 10초)
      - 빈 응답, 설명이 섞여 들어온 응답
    """
    fallback = fallback_sentence(words)
    if _is_bare_number(words):
        return fallback
    try:
        client = _get_client()
        prompt = SENTENCE_PROMPT.format(
            words=", ".join(words),
            context=context.strip() if context and context.strip() else SENTENCE_NO_CONTEXT,
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                # SDK는 밀리초를 받는다. .env는 다른 타임아웃(AI_SERVER_TIMEOUT)과
                # 단위를 맞춰 초로 두고 여기서 변환한다.
                http_options=types.HttpOptions(timeout=int(settings.SENTENCE_TIMEOUT * 1000)),
            ),
        )
        # .text는 응답이 차단되거나 candidate가 비면 예외를 낼 수 있어 try 안에서 읽는다.
        raw = response.text or ""
    except Exception:
        logger.warning("문장 조합 호출 실패, 나열 문장을 반환합니다.", exc_info=True)
        return fallback

    sentence = _clean_sentence(raw, fallback)
    if sentence is None:
        logger.warning("문장 조합 응답을 쓸 수 없어 나열 문장을 반환합니다: %r", raw)
        return fallback
    return sentence
