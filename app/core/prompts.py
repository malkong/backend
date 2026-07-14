"""LLM에 넣는 고정 프롬프트 (의도 분석 + 임시 카드 생성)"""
from app.schemas.schemas import INTENT_LABELS

_INTENT_LABELS_TEXT = ", ".join(INTENT_LABELS)

ANALYZE_PROMPT = """당신은 청각/의사소통 보조가 필요한 사용자를 돕는 AI입니다.
아래는 상대방이 사용자에게 한 말입니다. 이 발화를 분석해 다음 5가지 정보를 JSON으로 반환하세요.

상대방 발화: "{speech_text}"

분석 항목:
- intent: 발화의 핵심 의도. 반드시 다음 8개 중 하나만 선택: """ + _INTENT_LABELS_TEXT + """
- intent_detail: 의도에 대한 한 문장 설명
- easy_meaning: 발화를 가장 쉬운 말로 풀어쓴 한 문장 (사용자가 바로 이해할 수 있도록)
- response_type: 사용자가 할 수 있는 응답 유형 리스트 (예: ["accept", "refuse", "question", "conditional"])
- confidence: 분석 확신도 (0.0~1.0 사이 숫자)

반드시 지정된 JSON 스키마 형식으로만 응답하세요.
"""

CARD_GENERATION_PROMPT = """당신은 AAC(보완대체의사소통) 카드 추천 AI입니다.
아래 의도 분석 결과를 참고해, 사용자가 답변으로 고를 수 있는 AAC 단어 카드 후보를 4~6개 생성하세요.

의도: {intent}
의도 상세: {intent_detail}
쉬운 의미: {easy_meaning}
가능한 응답 유형: {response_type}

규칙:
- 각 카드는 "단어 하나"여야 합니다 (문장 금지). 예: "좋아", "싫어", "시간", "어디", "오늘", "나중에"
- category는 카드의 의미 분류입니다 (예: "수락", "거절", "질문", "시간")
- 가장 자연스럽고 우선순위 높은 카드를 앞쪽에 배치하세요 (순서가 중요합니다)
- word와 category만 반환하세요. 다른 필드(id, score 등)는 포함하지 마세요.

반드시 지정된 JSON 스키마 형식으로만 응답하세요.
"""
