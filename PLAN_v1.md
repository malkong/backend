# AAC 보조 시스템 — Mode 2 MVP 계획 v1
> Deep Interview 검증 완료 (ambiguity 15.2%, threshold 20% 이하 통과)

## 프로젝트 한 줄 요약
상대방 발화를 AI가 분석해 맞춤 AAC 단어 카드를 추천하는 FastAPI 서버 모듈.
팀 전체 Android 앱에서 API로 호출 가능한 실제 서버이며, 경진대회 MVP 목표.

---

## 이 서버의 정체 (중요)
이 서버는 **웹 데모 앱이 아니라 팀 전체 앱의 백엔드 모듈**이다.
- 팀원 앱(Android), Mode 1 담당자, AAC 카드 담당자 모두 이 서버의 API를 HTTP로 호출
- `web/index.html`은 팀원 앱 연동이 늦어질 때를 대비한 **발표용 백업 화면**일 뿐
- 실제 목표: `http://<서버IP>:8000` 에 뜨는 FastAPI 서버가 팀 전체 앱과 연동됨

---

## AAC 카드 개념 (중요)
AAC 카드는 **단어 또는 AAC 상징 하나**다. 문장이 아님.
- 예: "좋아", "싫어", "시간", "어디", "오늘", "어려워"
- 사용자가 카드를 하나씩 선택 → 앱(다른 팀원)이 선택된 카드들을 자연어 문장으로 조합
- 조합된 문장이 TTS로 상대방에게 출력
- **개인화 카운팅은 카드(단어) 단위**: "오늘은 어려워."가 아니라 "오늘" +1, "어려워" +1

---

## 내 담당 범위 (확정)
- Mode 1(시각만 인식) → 다른 팀원 담당. 이 코드에서 완전 제외
- 문장 조합(카드들 → 자연어 문장) → 앱/다른 팀원 담당. 내 범위 아님
- `/transcribe` 결과에서 "어떤 문장이 대답 대상인지" 선택 → 앱 팀원 담당 (MVP는 사용자가 상대방 말만 담긴 짧은 클립 녹화로 단순화)

**내 담당 Mode 2 파이프라인:**
1. 영상/오디오 파일 → STT → `speech_text`
2. `speech_text` → Gemini 의도 분석 → intent 5필드
3. intent 기반 단어 카드 후보 생성 (MVP: LLM 임시 생성 / 최종: AAC 팀원 모듈)
4. 사용자 이력 기반 개인화 점수 계산 + 카드 재정렬
5. 사용자가 고른 카드 단어를 각각 기록 → 다음 추천에 반영

---

## 두 구조 병렬 유지 전략 (핵심 설계)
```
MVP 구조 (지금):
speech_text → LLM 의도 분석 → [card_generator.py: LLM 임시 카드 생성] → 개인화 → 최종 카드

최종 구조 (팀원 모듈 완성 후):
speech_text → LLM 의도 분석 → [card_generator.py: AAC 모듈/DB 조회] → 개인화 → 최종 카드
```
**교체 범위: `card_generator.py` 내부만 바꾸면 됨.**
`main.py`, `personalize.py`, `schemas.py`, 앱 쪽 코드는 변경 없음.

---

## 최종 파일 구조 (3주차 완성 시)
```
IT_3/
├── main.py              # FastAPI 앱 + 모든 엔드포인트
├── llm.py               # Gemini API 호출 (의도분석 프롬프트)
├── stt.py               # Faster-Whisper 기반 STT (영상/오디오 → speech_text, CPU)
├── card_generator.py    # 카드 후보 생성 (LLM fallback / AAC 모듈 교체 지점)
├── personalize.py       # 카드 개인화 점수 계산 + 정렬
├── storage.py           # MySQL 접속/쿼리 (사용자 카드 선택 이력, card_history 테이블)
├── schemas.py           # Pydantic 요청/응답 모델
├── prompts.py           # LLM에 넣는 고정 프롬프트
├── data/
│   └── seed_demo.sql    # 데모용 미리 데이터 INSERT 스크립트 (history.json 대체)
├── web/
│   └── index.html       # 발표용 백업 웹 화면 (팀원 앱 연동 실패 시)
├── .env                 # GEMINI_API_KEY (절대 커밋 금지)
├── .env.example         # 팀원 공유용 키 형식 예시
├── .gitignore
├── requirements.txt
├── API_CONTRACT.md      # 팀 전체 API 명세서 (앱↔서버 + 내 서버↔AAC팀원)
└── PLAN_v1.md           # 이 파일
```

---

## 팀 API 계약서 (전체 팀 공유)

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

### API 목록

| 번호 | 메서드 | 경로 | 역할 |
|------|--------|------|------|
| 1 | GET | `/health` | 서버 생존 확인 |
| 2 | POST | `/transcribe` | 영상/오디오 → speech_text (STT) |
| 3 | POST | `/analyze` | 의도 분석 + 개인화 카드 추천 (핵심) |
| 4 | POST | `/select` | 고른 카드 기록 → 개인화 학습 (카드 단위) |
| 5 | GET | `/profile/{user_id}` | 발표용: 사용자 선호 카드 확인 |

---

### 1. GET /health
```json
응답: { "status": "ok" }
```

---

### 2. POST /transcribe
요청: `multipart/form-data`
- `file`: 영상/오디오 파일 (mp4, m4a, wav, mov 등 — ffmpeg으로 오디오 정규화 후 Faster-Whisper 처리)
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
- `prompts.py`의 `ANALYZE_PROMPT`에 이 8개 목록을 명시하고 이 중 하나만 고르도록 지시
- `schemas.py`의 `AnalysisResult.intent`는 이 8개 값만 허용하는 타입(Literal)으로 제한
- Gemini 실패 시 `FALLBACK_ANALYSIS.intent`는 목록에 없는 `"알수없음"` 대신 `"기타"` 사용

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
- cards제시, 문장 조합은 **앱/다른 팀원 담당**
- cards는 개인화 구현을 위한 임시 출력. 추후에는 다른 팀원의 AAC 카드 후보로 대체할 것임.

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
> `card_id`는 옵션. AAC 팀원 모듈 연동 전(MVP)에는 서버가 자동으로 더미 값(`tmp_<word>`)을 채워 MySQL에 저장한다.
> 카운팅 키는 `(user_id, word)` — `card_id`는 나중에 실제 값이 들어오면 자동으로 교체된다.

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
    { "id": "card_001", "word": "좋아",   "category": "수락", "symbol_id":"sym_042"},
    { "id": "card_002", "word": "싫어",   "category": "거절", "symbol_id":"sym_043"}
  ]
}

```
> LLM fallback 카드와 AAC 모듈 카드는 **동일한 형식**이어야 함.
> 형식 유지 시 교체 후 `personalize.py`, `main.py` 수정 불필요.

---

## 데이터 구조 (MySQL, card_history 테이블) — 카드 단위
개인화 이력은 `data/history.json` 대신 **MySQL**에 저장한다 (내 프로젝트 전용 DB, 직접 관리).
카운팅 키는 `(user_id, word)`. `card_id`는 별도 컬럼으로 저장하며, MVP에서는 더미 값(`tmp_<word>`)을 채우고
AAC 팀원 모듈 연동 후 실제 카드 고유번호로 자동 교체한다.

```sql
CREATE TABLE IF NOT EXISTS card_history (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id   VARCHAR(64)  NOT NULL,
  word      VARCHAR(64)  NOT NULL,
  card_id   VARCHAR(64)  NULL,        -- MVP: 더미(tmp_<word>), 나중에 AAC 실제 id로 교체
  category  VARCHAR(32)  NOT NULL,
  count     INT          NOT NULL DEFAULT 0,
  last_used DATETIME     NOT NULL,
  UNIQUE KEY uq_user_word (user_id, word)
) CHARACTER SET utf8mb4;
```

**카드 선택 시 UPSERT (count++ 한 번에 처리):**
```sql
INSERT INTO card_history (user_id, word, card_id, category, count, last_used)
VALUES (%s, %s, %s, %s, 1, NOW())
ON DUPLICATE KEY UPDATE
  count     = count + 1,
  last_used = NOW(),
  card_id   = COALESCE(VALUES(card_id), card_id);  -- 실제 card_id 오면 자동으로 채움
```

**DB 접속 정보 (.env):**
```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=aac
```

---

## 개인화 점수 공식 (MVP, 수정됨)
```
score = base_rank + (0.08 × count)
```
- `base_rank`: LLM이 준 카드 순서 → 1번=1.0, 2번=0.75, 3번=0.5, 4번=0.25, 5번=0.1, 6번=0.05
- `count`: history.json에서 해당 단어 카드 선택 횟수
- recency_bonus 제거 → **3~4번 선택 후 순위 변화** (데모 시연에 적합)

**검증:**
- 카드A (1위, count=0): score = 1.0
- 카드B (2위, count=4): score = 0.75 + 0.32 = 1.07 → 1위 역전 ✓
- 카드B (2위, count=3): score = 0.75 + 0.24 = 0.99 → 아직 2위 (한 번 더 필요)

**데모 시나리오:**
- 옵션 A: 실시간으로 "좋아" 4~5번 클릭 → 순위 변화 확인
- 옵션 B: `data/seed_demo.sql`을 MySQL에 미리 실행해두고 "이 사용자는 이런 패턴" 시연 (통합 데모용)
- 두 옵션 모두 준비할 것

**API 실패 시 fallback 카드 (하드코딩):**
```python
FALLBACK_CARDS = [
  {"id":"f1","word":"좋아",  "category":"수락","symbol_id":None,"source":"fallback","score":1.0},
  {"id":"f2","word":"싫어",  "category":"거절","symbol_id":None,"source":"fallback","score":0.75},
  {"id":"f3","word":"나중에","category":"거절","symbol_id":None,"source":"fallback","score":0.5},
  {"id":"f4","word":"시간",  "category":"질문","symbol_id":None,"source":"fallback","score":0.25},
  {"id":"f5","word":"어디",  "category":"질문","symbol_id":None,"source":"fallback","score":0.1},
  {"id":"f6","word":"응",    "category":"수락","symbol_id":None,"source":"fallback","score":0.05},
]
```

---

## 사용 기술
- **서버**: FastAPI + Python
- **LLM : Gemini API (gemini-3.1-flash-lite, 확정)
- STT**: Faster-Whisper
      - [영상 파일 (.wav/.mp3)] 
         │
         ▼
 1. 백엔드 서버 (FastAPI + Python)
         │
         ▼
 2. STT 엔진 (글자 변환 + 타임스탬프)
    - 추천: Faster-Whisper (자체 서버 구축 시 비용 0원)         │
         ▼
 3. LLM 의도 분석 엔진 (프롬프팅을 통한 정제)
    - 확정: Gemini API (gemini-3.1-flash-lite)
         ▼
[최종 가공된 의도 분석 JSON 데이터 반환]
- **개인화 저장**: MySQL (내 프로젝트 전용 DB, `card_history` 테이블, PyMySQL로 접속)
- **응답 속도 목표**: 3초 이내
- **패키지**: fastapi, uvicorn, google-genai, Faster-Whisper, python-dotenv, pydantic, python-multipart, PyMySQL

---

## 위험 요소 & 대응
| 위험 | 대응 |
|------|------|
| API 키 코드에 직접 기입 | .env에만, .gitignore에 추가 |
| Gemini JSON 깨짐 | structured output + FALLBACK_CARDS 하드코딩 |
| 앱에서 CORS 차단 | FastAPI CORSMiddleware 2줄 미리 설정 |
| 로컬 서버 외부 접근 불가 | 같은 와이파이 IP 또는 ngrok |
| 앱 연동 안 될 때 발표 | web/index.html 백업 (항상 준비) |
| AAC 팀원 모듈 늦어짐 | LLM fallback으로 card_generator.py가 혼자 돌아감 |
| 1번 클릭에 순위 바뀜 | 공식을 0.08×count로 조정 (recency_bonus 제거) |
| Gemini 3초 초과 | 데모용으로는 짧은 문장만 입력, 팀원에게 미리 알림 |
| MySQL 연결 실패 | personalize.py가 get_counts 실패 시 개인화만 생략하고 원본 카드 순서 반환 (/analyze는 죽지 않음). /select는 팀 에러 형식으로 응답 |

---

## 발표 3분 시연 순서 (확정)
```
1. 상황 설정
   "메타글라스 착용 사용자가 상대방과 대화. 녹화 버튼 눌러 상대방 발화 캡처."

2. STT (POST /transcribe 또는 텍스트 직접 입력)
   입력: 음성/영상 파일
   출력: speech_text = "오늘 수업 끝나고 같이 카페 갈래?"

3. easy_meaning 출력 (메타글라스 음성으로 역할)
   "수업 끝나고 같이 카페 가자는 말이야."
   → "AI가 어려운 말을 쉽게 풀어준다"

4. 의도 분석  (POST /analyze)
   intent: 제안 | confidence: 0.86
   → "AI가 의도를 분석한다"

5. AAC 카드 1차 추천 (개인화 전)
   [좋아] [싫어] [시간] [어디] [나중에]
   → "AAC 카드가 자동 추천된다"

6. 개인화 적용 후 2차 정렬
   → "이 사용자는 평소 '좋아'를 자주 썼기 때문에 더 위에 뜬다"
   → "AI가 사용자를 기억한다"

7. 카드 선택 + 저장 (POST /select)
   "좋아" 클릭 → 저장됨

8. 재분석 → 순위 변화 확인
   → "쓸수록 사용자에게 맞춰진다"
```

---

## 주차별 작업 분리 (터미널 3개 운영 기준)

### 1주차 지시문 (터미널 1에 복사)
```
이 폴더의 PLAN_v1.md를 먼저 읽어줘.
그 다음 1주차 코드를 짜줘.

1주차에 만들 파일:
- requirements.txt
- .gitignore
- .env.example
- schemas.py       (Card에 symbol_id, source 필드 포함)
- prompts.py       (의도분석 + 임시 카드 생성 고정 프롬프트)
- llm.py           (Gemini 의도분석 호출, /transcribe는 3주차)
- card_generator.py (LLM fallback 카드 생성 함수 + get_candidate_cards 진입점)
- main.py          (GET /health, POST /analyze 만)
- data/history.json (빈 파일: {})
- API_CONTRACT.md  (PLAN_v1.md의 팀 API 계약서 섹션을 별도 파일로 저장)

1주차 완료 기준:
1. pip install -r requirements.txt 성공
2. uvicorn app.main:app --reload 실행
3. http://localhost:8000/docs 에서 /analyze 테스트
4. 입력: {"user_id":"test","speech_text":"오늘 수업 끝나고 같이 카페 갈래?"}
5. 출력: analysis(5필드) + cards(단어 카드 4~6개, symbol_id/source 포함) JSON 정상 반환
```

---

### 2주차 지시문 (터미널 2에 복사)
```
이 폴더의 PLAN_v1.md를 먼저 읽어줘.
그 다음 이미 있는 파일들(main.py, llm.py, schemas.py 등)을 읽어봐.
그 다음 2주차 코드를 짜줘.

2주차에 만들 파일:
- storage.py       (MySQL 접속/쿼리, card_history 테이블 UPSERT로 카드 단위 count++)
- personalize.py   (score = base_rank + 0.08×count 공식, 카드 재정렬, DB 실패 시 개인화 생략하고 원본 반환)
- data/seed_demo.sql (데모용 미리 데이터 INSERT 스크립트)

2주차에 수정할 파일:
- main.py          (startup에서 storage.init_db() 호출로 테이블 자동 생성, POST /select, GET /profile/{user_id} 추가)
- llm.py           (/analyze가 personalize.py 연동해서 정렬된 카드 반환)
- schemas.py       (SelectRequest/SelectCard에 card_id 옵션 필드, SelectResponse, ProfileResponse 추가)
- requirements.txt (PyMySQL 추가)
- .env / .env.example (DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 추가)

개인화 공식 주의:
score = base_rank + (0.08 × count)  ← recency_bonus 없음
base_rank: 1번=1.0, 2번=0.75, 3번=0.5, 4번=0.25, 5번=0.1, 6번=0.05

card_id 처리 주의:
- 카운팅 키는 어디까지나 (user_id, word). card_id는 참고용 별도 컬럼.
- POST /select 요청에 card_id가 없으면 서버가 더미 값 `tmp_<word>`을 채워 저장.
- 나중에 AAC 팀원 모듈에서 실제 card_id가 오면 UPSERT의 COALESCE로 자동 교체 (기존 값은 덮어쓰지 않되, NULL/더미는 갱신).

2주차 완료 기준:
1. MySQL에 `aac` 데이터베이스 생성 후 .env 설정, uvicorn 기동 시 card_history 테이블 자동 생성 확인
2. POST /select 로 "좋아" 카드를 4번 기록
3. POST /analyze 재호출 시 "좋아" 카드 score = 0.75 + 0.08×4 = 1.07 → 1위로 올라옴
4. MySQL card_history 테이블에 카드 이력 및 card_id(더미) 저장 확인
5. GET /profile/user_123 → top_cards 확인
6. MySQL 중지 후 POST /analyze 호출 → 500 없이 개인화 생략된 카드 반환 확인 (graceful degradation)
```

---

### 3주차 지시문 (터미널 3에 복사)
```
이 폴더의 PLAN_v1.md를 먼저 읽어줘.
그 다음 이미 있는 파일들(main.py, llm.py, schemas.py 등)을 읽어봐.
그 다음 3주차 코드를 짜줘.

3주차에 만들 파일:
- stt.py           (Faster-Whisper 기반 STT: ffmpeg으로 오디오 정규화 후 CPU 추론)
- web/index.html   (발표용 백업 웹 화면)

3주차에 수정할 파일:
- main.py          (POST /transcribe 엔드포인트 추가, 실패 시 팀 에러 형식 준수)
- schemas.py       (TranscribeResponse 추가)
- requirements.txt (faster-whisper 추가)

STT 엔진 결정 (확정): Gemini가 아니라 Faster-Whisper(CPU) 사용.
이유: 영상 입력이라 Gemini 멀티모달도 가능했지만, 짧은 클립(10초 이내) +
Gemini 왕복 2회(STT+의도분석) 대비 지연시간 이득, 엔진 분리로 실패 지점 구분 용이.

web/index.html 요구사항:
- 영상/오디오 파일 업로드 → /transcribe 호출 → speech_text 자동 채움
- speech_text 입력창 + "분석" 버튼
- /analyze 호출 → easy_meaning 표시 + 카드 그리드 표시
- 카드 클릭 → 하이라이트만 (POST /select 연동은 2주차 완료 후 추가 예정)
- "다시 분석" 버튼 → 같은 speech_text로 /analyze 재호출

3주차 완료 기준:
1. POST /transcribe + 한국어 음성/영상 파일 → speech_text 정상 반환
2. web/index.html 브라우저 열기 → 파일 업로드 STT → 카드 표시 → 클릭 시 하이라이트 확인
3. 2주차(/select, personalize.py) 완료 후 web/index.html에 저장·순위 변화 연동 추가
```

---

### 로컬 CPU 검증 지시문 (터미널 4에 복사)
```
이 폴더의 PLAN_v1.md를 먼저 읽어줘.
그 다음 stt.py, main.py, requirements.txt를 읽어봐.

이 프로젝트를 로컬 Windows PC(CPU)에서 STT를 실제로 검증해줘.
GPU 없이 CPU만으로 동작하는 것이 확정된 구성이야.

확인할 것:
1. ffmpeg 설치 여부 확인 (없으면 설치)
2. pip install -r requirements.txt (faster-whisper==1.0.3 포함) 정상 설치되는지
3. stt.py의 WhisperModel(device="cpu", compute_type="int8")이 정상 로드되는지
4. uvicorn app.main:app --port 8000 실행 후 실제 한국어 영상/음성 파일로 POST /transcribe 테스트
5. web/index.html 열어서 파일 업로드 → STT → /analyze 전체 흐름 확인
6. 응답 속도가 목표(3초 이내)를 만족하는지 확인 (CPU라 모델 크기에 따라 초과 가능, 초과 시 STT_MODEL_SIZE를 더 작은 값으로 조정 검토)

완료 기준: POST /transcribe가 CPU에서 정확한 한국어 speech_text를 반환
```

---

## 검증 방법 (end-to-end)
1. MySQL에 `aac` 데이터베이스 생성, `.env`에 DB 접속정보 입력
2. `uvicorn app.main:app --reload` → `http://localhost:8000/docs` (startup 시 card_history 테이블 자동 생성)
3. `GET /health` → `{"status":"ok"}`
4. `POST /analyze` → analysis 5필드 + cards(symbol_id/source 포함) 반환
5. `POST /select` "좋아" 4번 → `POST /analyze` 재호출 → "좋아" score 1위 확인
6. MySQL `card_history` 테이블에서 카드 이력 및 card_id(더미) 저장 확인
7. `POST /transcribe` + 한국어 음성/영상 → speech_text 반환 (ffmpeg + Faster-Whisper, CPU)
8. `web/index.html` → STT 업로드 + 카드 표시 + 클릭 하이라이트 확인 (순위 변화는 2주차 완료 후)
