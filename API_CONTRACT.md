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
  "user_id": 1,
  "speech_text": "오늘 수업 끝나고 같이 카페 갈래?",
  "dialogue_history": [
    { "speaker": "partner", "text": "이전 발화" },
    { "speaker": "user",    "text": "이전 답변" }
  ],
  "visual_context": { "place": "병원" }
}
```

MVP에서는 `speech_text`와 `user_id`(숫자)만 필수.
`dialogue_history`, `visual_context`는 옵션.

**place 고정 라벨 (한글 7종)**
`visual_context.place`는 아래 값 중 하나(옵션). 없거나 인식 불가한 값이면 **조용히 무시**되고 intent+공통 카드만으로 응답한다(에러 없음). `/select`의 `context.place`와 **동일한 도메인**이어야 개인화가 맞물린다:
```
공통, 식당, 병원, 카페, 대중교통, 편의점, 약국
```
(실제 입력 place는 물리적 6종(식당/병원/카페/대중교통/편의점/약국)만 오고, `공통`은 카드 컨텍스트 baseline 전용 값이다.)

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
    { "word": "진통제를 주세요", "category": "의료", "card_id": 61, "image_url": "https://drive.google.com/file/d/.../view", "source": "card_db", "score": 0.70 },
    { "word": "머리가 아파요",   "category": "의료", "card_id": 19, "image_url": "https://drive.google.com/file/d/.../view", "source": "card_db", "score": 0.50 },
    { "word": "궁금해요",       "category": "기타", "card_id":  8, "image_url": "https://drive.google.com/file/d/.../view", "source": "card_db", "score": 0.30 },
    { "word": "네",            "category": "인사", "card_id": 15, "image_url": "https://drive.google.com/file/d/.../view", "source": "card_db", "score": 0.00 }
  ]
}
```

- `cards`는 score 내림차순 정렬되어 반환 (상위 8개)
- `word`: 단어/구 하나 (AAC 카드 하나)
- `card_id`: 카탈로그 카드 고유번호(숫자, **항상 존재**). DB 조회 실패로 카탈로그 파일 폴백을 타도 파일에 심어둔 동일한 id가 반환된다
- `image_url`: 카드 이미지 URL(없으면 `null`)
- `source`: `"card_db"` (카탈로그 매핑)
- 문장 조합은 **앱/다른 팀원 담당**

---

### 4. POST /select ← 카드 단위로 호출

카드 하나 선택할 때마다 호출. 여러 카드 선택 시 여러 번 호출.

```json
요청:
{
  "user_id": 1,
  "card": {
    "word": "진통제를 주세요",
    "category": "의료",
    "card_id": 61
  },
  "context": {
    "intent": "요청",
    "place": "병원"
  }
}

응답:
{ "ok": true, "new_count": 5 }
```

> **`card_id`는 필수(숫자)다.** 카운팅 키가 `(user_id, card_id)`이므로 생략하면 **422**(Pydantic 검증 실패)로 거부된다. `/analyze` 응답의 `card_id`를 그대로 넘기면 된다.
> `word`/`category`는 키가 아니라 표시·디버깅용이며, 선택할 때마다 최신 값으로 갱신된다(카드 이름이 바뀌어도 이력이 끊기지 않는다).
> 개인화 이력은 MySQL에 저장된다: `card_history` 테이블(집계, 카운팅 키 `(user_id, word)`)과 `usage_log` 테이블(선택 시점의 intent/place까지 남기는 이벤트 로그)에 함께 기록된다.
> DB 쓰기 실패 시에도 `/select`는 500을 내지 않고 `{ "ok": false, "new_count": 0 }`을 200으로 반환한다(graceful degradation).
>
> **`context.place`는 옵션**. 앱이 위치를 모르면 생략하면 된다 — 생략/미지원 값이면 place 보너스만 빠지고 `/select`는 실패하지 않는다. 값은 `/analyze`와 **동일한 한글 7종** 도메인만 사용:
> ```
> 공통, 식당, 병원, 카페, 대중교통, 편의점, 약국
> ```
> `place`(및 `intent`)가 이후 선택과 같은 상황이면 `/analyze` 카드 점수에 소액 보너스가 붙는다. `place`/`intent`가 미기록(NULL)인 이력은 매칭 대상에서 제외된다(unknown끼리도 보너스 없음). (상세: `.omc/specs/deep-interview-aac-context-personalization.md`)

---

### 5. GET /profile/{user_id}

```json
응답:
{
  "user_id": 1,
  "top_cards": [
    { "word": "진통제를 주세요", "category": "의료", "count": 31, "card_id": 61 },
    { "word": "머리가 아파요",   "category": "의료", "count": 15, "card_id": 19 },
    { "word": "네",            "category": "인사", "count":  3, "card_id": 15 }
  ]
}
```

> `user_id`, `card_id` 모두 숫자다. `card_id`는 개인화 이력의 카운팅 키라 `null`이 될 수 없다.
> `word`/`category`는 표시용이며 카드 이름이 바뀌면 최신 값으로 갱신된다.

---

## AAC 팀원과의 계약 (내 서버 ↔ AAC 카드 담당자)

> (갱신) 이전에는 별도 카드 후보 API 연동을 팀원과 협의할 예정이었으나, `data/cards_catalog.json`(111장, `name/category/context/intention/image_url/valid_for_intents`)이 이미 AAC 카드 데이터 자체이며 `card_generator.py`가 이를 직접 매핑에 사용한다. 별도의 실시간 카드 후보 API 연동은 필요 없음 — **완료 기준은 이 카탈로그 파일 형식의 합의 유지**로 충분(라이브 통합 테스트는 스코프 밖).
>
> `valid_for_intents`는 카드가 "상대방의 어떤 intent에 대한 응답으로 적절한지"를 태깅한 배열(이 백엔드 로컬 전용 필드, 팀원 DB에는 없음). 매핑은 `intention`이 아니라 이 필드만 사용한다 — `intention`은 카드 자체(사용자)의 발화 유형이라 상대방 intent와 화자가 달라 직접 비교하면 부적절한 응답이 나올 수 있기 때문이다.

**내가 팀원에게 주는 것 (의도 분석 결과):**

```json
{
  "intent": "제안",
  "intent_detail": "수업 후 함께 카페에 가자는 제안",
  "response_type": ["accept", "refuse", "question", "conditional"],
  "context": { "place": "병원" }
}
```

**카드 데이터 출처 (`data/cards_catalog.json`, AAC 카드 담당자 제공)**:

```json
{
  "name": "좋아",
  "category": "수락",
  "context": "공통",
  "intention": "확인",
  "image_url": "https://..."
}
```

> `context`가 place(한글 7종), `intention`이 intent 라벨. `card_generator.py`가 이 필드를 그대로 매핑 tier 산출에 사용하며, 응답의 `card_id`는 `cards` 테이블의 id이며, 카탈로그 파일에도 동일한 id가 `"id"` 필드로 심어져 있어 폴백 시에도 같은 값이 나온다.
