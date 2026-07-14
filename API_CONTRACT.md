# 팀 API 계약서

> PLAN_v1.md의 "팀 API 계약서" 섹션을 별도 파일로 추출한 문서입니다.

**공통 규칙**

- Base URL(로컬): `http://localhost:8000`
- Base URL(팀 공유): `http://<서버IP>:8000`
- 요청/응답: JSON (파일 업로드만 multipart/form-data)
- 인코딩: UTF-8
- 응답 속도 목표: **3초 이내** (Gemini API 호출 포함)
- 에러 응답:

```json
{ "error": true, "message": "사람이 읽을 설명", "detail": "원인(옵션)" }
```

## API 목록

| 번호 | 메서드 | 경로                 | 역할                                     |
| ---- | ------ | -------------------- | ---------------------------------------- |
| 1    | GET    | `/health`            | 서버 생존 확인                           |
| 2    | POST   | `/transcribe`        | 영상/오디오 → speech_text (STT)          |
| 3    | POST   | `/analyze`           | 의도 분석 + 개인화 카드 추천 (핵심)      |
| 4    | POST   | `/select`            | 고른 카드 기록 → 개인화 학습 (카드 단위) |
| 5    | GET    | `/profile/{user_id}` | 발표용: 사용자 선호 카드 확인            |

---

### 1. GET /health

```json
응답: { "status": "ok" }
```

---

### 2. POST /transcribe

요청: `multipart/form-data`

- `file`: 영상/오디오 파일 (mp4, m4a, wav, mov 등 — Gemini 지원 형식)
- `user_id`: 문자열 (옵션)

```json
응답:
{
  "speech_text": "오늘 수업 끝나고 같이 카페 갈래?",
  "language": "ko",
  "duration_sec": 3.2
}
```

> MVP: 사용자가 상대방 말만 담긴 짧은 클립을 녹화해서 업로드.
> "어떤 문장이 대답 대상인지" 선택은 앱 담당.

---

### 3. POST /analyze ← 핵심

```json
요청:
{
  "user_id": "user_123",
  "speech_text": "오늘 수업 끝나고 같이 카페 갈래?",
  "dialogue_history": [
    { "speaker": "partner", "text": "이전 발화" },
    { "speaker": "user",    "text": "이전 답변" }
  ],
  "visual_context": { "place": "classroom" }
}
```

MVP에서는 `speech_text`와 `user_id`만 필수.
`dialogue_history`, `visual_context`는 옵션.

**intent 고정 라벨 (확정)**
`analysis.intent`는 아래 8개 값 중 하나로만 반환 (자유 텍스트 금지):

```
INTENT_LABELS = ["인사", "질문", "요청", "제안", "정보_전달", "감정_표현", "확인", "기타"]
```

```json
응답:
{
  "analysis": {
    "intent": "제안",
    "intent_detail": "수업이 끝난 뒤 함께 카페에 가자고 제안함",
    "easy_meaning": "수업 끝나고 같이 카페 가자는 말이야.",
    "response_type": ["accept", "refuse", "question", "conditional"],
    "confidence": 0.86
  },
  "cards": [
    { "id": "c1", "word": "좋아",   "category": "수락", "symbol_id": null, "source": "llm_fallback", "score": 0.91 },
    { "id": "c2", "word": "싫어",   "category": "거절", "symbol_id": null, "source": "llm_fallback", "score": 0.62 },
    { "id": "c3", "word": "시간",   "category": "질문", "symbol_id": null, "source": "llm_fallback", "score": 0.55 },
    { "id": "c4", "word": "어디",   "category": "질문", "symbol_id": null, "source": "llm_fallback", "score": 0.48 },
    { "id": "c5", "word": "오늘",   "category": "시간", "symbol_id": null, "source": "llm_fallback", "score": 0.40 },
    { "id": "c6", "word": "나중에", "category": "거절", "symbol_id": null, "source": "llm_fallback", "score": 0.35 }
  ]
}
```

- `cards`는 score 내림차순 정렬되어 반환
- `word`: 단어 하나 (AAC 카드 하나)
- `symbol_id`: null(MVP) → AAC 팀원 모듈 연동 시 실제 상징 ID 채워짐
- `source`: `"llm_fallback"` (MVP) → `"aac_module"` 또는 `"card_db"` (최종)
- 문장 조합은 **앱/다른 팀원 담당**

---

### 4. POST /select ← 카드 단위로 호출

카드 하나 선택할 때마다 호출. 여러 카드 선택 시 여러 번 호출.

```json
요청:
{
  "user_id": "user_123",
  "card": {
    "word": "좋아",
    "category": "수락",
    "card_id": "sym_042"
  },
  "context": {
    "intent": "제안"
  }
}

응답:
{ "ok": true, "new_count": 5 }
```

> `card_id`는 옵션. AAC 팀원 모듈 연동 전(MVP)에는 서버가 자동으로 더미 값(`tmp_<word>`)을 채워 저장한다.
> 개인화 이력은 MySQL(`card_history` 테이블)에 저장되며, 카운팅 키는 `(user_id, word)`다. `card_id`는 나중에 실제 값이 들어오면 자동으로 교체된다.

---

### 5. GET /profile/{user_id}

```json
응답:
{
  "user_id": "user_123",
  "top_cards": [
    { "word": "좋아",   "category": "수락", "count": 31, "card_id": "tmp_좋아" },
    { "word": "시간",   "category": "질문", "count": 15, "card_id": "tmp_시간" },
    { "word": "싫어",   "category": "거절", "count":  3, "card_id": "tmp_싫어" }
  ]
}
```

---

## AAC 팀원과의 계약 (내 서버 ↔ AAC 카드 담당자)

이 부분은 팀원과 이번 주에 확정해야 함.

**내가 팀원에게 주는 것 (의도 분석 결과):**

```json
{
  "intent": "제안",
  "intent_detail": "수업 후 함께 카페에 가자는 제안",
  "response_type": ["accept", "refuse", "question", "conditional"],
  "context": { "place": "classroom" }
}
```

**팀원이 나에게 주는 것 (카드 후보, 확정 전):**

```json
{
  "cards": [
    {
      "id": "card_001",
      "word": "좋아",
      "category": "수락",
      "symbol_id": "sym_042"
    },
    {
      "id": "card_002",
      "word": "싫어",
      "category": "거절",
      "symbol_id": "sym_018"
    }
  ]
}
```

> LLM fallback 카드와 AAC 모듈 카드는 **동일한 형식**이어야 함.
> 형식 유지 시 교체 후 `personalize.py`, `main.py` 수정 불필요.
