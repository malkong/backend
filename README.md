# 말콩(malkong) 백엔드 — AAC 통합 서버

상대방의 발화와 주변 상황(장소)을 분석해 맞춤 AAC 카드를 추천하고, 사용자가 고른
카드를 자연스러운 문장으로 조합해주는 FastAPI 서버입니다. 청각/의사소통 보조가
필요한 사용자가 상대방의 말을 쉽게 이해하고, 개인화된 카드로 빠르게 응답할 수
있도록 돕습니다.

이 저장소는 팀 전체 Flutter 앱(`malkong/frontend`)의 백엔드 모듈이며, 장소 인식은
별도 AI 서버(`malkong/ai`, CLIP 파인튜닝 모델)와 연동합니다. `web/index.html`은
앱 연동이 늦어질 경우를 대비한 발표용 백업 화면입니다.

## 핵심 기능

| 기능 | 설명 | 담당 API |
|---|---|---|
| 회원가입/로그인 | JWT 기반 인증. 개인화 관련 API는 전부 토큰 필요 | `POST /auth/signup`, `POST /auth/login` |
| 의도 분석 | 상대방 발화를 Gemini로 분석해 8종 의도 라벨 중 하나로 분류 | `POST /analyze` |
| 장소 인식 | 사진을 AI 서버(`malkong/ai`)에 보내 장소 인식, 실패 시 사용자가 직접 선택 | `POST /scene` |
| AAC 카드 매칭 | 의도 + 장소를 카탈로그 111장과 대조해 4단계 우선순위로 후보 카드 추천 | `POST /analyze` (cards) |
| 개인화 | 사용자의 과거 선택 이력(전체/같은 상황)을 반영해 카드 순위 재조정 | `POST /analyze` (rerank) |
| 온보딩 | 신규 사용자의 콜드 스타트 보정(자주 가는 장소·카드 미리 선택) | `POST /onboarding` |
| 카드 선택 기록 | 고른 카드(들)를 개인화 이력에 반영 | `POST /select` |
| 문장 조합 | 고른 카드 단어들을 Gemini로 자연스러운 한 문장으로 다듬음 | `POST /sentence` |
| STT | 영상/음성 파일을 Faster-Whisper로 텍스트 변환 | `POST /transcribe` |
| 이력/프로필 조회 | 선택 이력, 선호 카드 확인 | `GET /history/me`, `GET /profile/me` |

## 의도 분석 (Intent Analysis)

`POST /analyze`가 상대방 발화(`speech_text`)를 Gemini API(`gemini-3.1-flash-lite`)에
전달해 아래 5개 필드로 구조화된 결과를 받습니다.

| 필드 | 설명 |
|------|------|
| `intent` | 발화의 핵심 의도. 아래 8개 라벨 중 하나로 고정 |
| `intent_detail` | 의도에 대한 한 문장 설명 |
| `easy_meaning` | 발화를 가장 쉬운 말로 풀어쓴 한 문장 |
| `response_type` | 사용자가 할 수 있는 응답 유형 목록 (예: `accept`, `refuse`, `question`, `conditional`) |
| `confidence` | 분석 확신도 (0.0~1.0) |

### intent 고정 라벨

자유 텍스트가 아니라 아래 8개 값 중 하나만 반환하도록 프롬프트와 스키마 양쪽에서 강제합니다.

```
인사, 질문, 요청, 제안, 정보_전달, 감정_표현, 확인, 기타
```

- `prompts.py`의 `ANALYZE_PROMPT`가 이 8개 목록을 명시하고 하나만 고르도록 지시
- `schemas.py`의 `AnalysisResult.intent`는 `Literal`로 8개 값만 허용 — null이 될 수 없다
- `speech_text`가 비어있으면(Mode 1: 사진/장소만 있는 경우) Gemini를 호출하지 않고
  `intent="기타"` 고정값을 즉시 반환 (응답속도 최적화)
- Gemini 호출 실패 시 `FALLBACK_ANALYSIS`가 `"기타"` intent로 대체 응답 (서버가 죽지 않음)

### 처리 흐름

```
speech_text(옵션) + visual_context.place(옵션)
  → llm.py: analyze_intent()  ─┐  speech_text 있으면 Gemini 구조화 출력
                                │  없으면 Gemini 생략, intent="기타" 즉시 반환
  → card_generator.py: get_candidate_cards()
        ─ intent + place를 카탈로그 111장과 대조해 4단계 우선순위로 후보 8장 추출
        ─ 카드는 LLM이 생성하는 게 아니라 AAC 카드 담당자가 제공한 실제 카탈로그에서 나옴 (DB `cards` 테이블 우선 조회, 실패 시 `cards_catalog.json` fallback)
  → personalize.py: rerank()
        ─ 사용자의 과거 선택 이력(전체 횟수 + 같은 intent/place 상황 횟수)을 가산해 재정렬
  → AnalyzeResponse { analysis, cards }
```

카드를 고르면 `POST /select`로 기록되고, 이 기록이 다음 `/analyze` 호출의 개인화
재정렬에 반영됩니다 — 쓸수록 그 사용자에게 맞춰지는 구조입니다.

## API 개요

전체 API 명세는 [`API_CONTRACT.md`](API_CONTRACT.md) 참고.

| 메서드 | 경로 | 역할 |
|------|------|------|
| GET | `/health` | 서버 생존 확인 |
| POST | `/auth/signup` | 회원가입 |
| POST | `/auth/login` | 로그인, JWT 토큰 발급 |
| POST | `/transcribe` | 영상/오디오 → speech_text (Faster-Whisper STT). 다른 Mode 2 API와 달리 인증 불필요 |
| POST | `/scene` | 사진 → 장소 인식 (AI 서버 경유, 실패 시 200 + context=null) |
| GET | `/scene/health` | AI 서버 연동 상태 확인 |
| GET | `/cards/contexts` | 온보딩용 장소 목록 |
| GET | `/cards` | 특정 장소의 카탈로그 카드 목록 |
| POST | `/onboarding` | 신규 사용자 콜드 스타트 보정 |
| POST | `/analyze` | **의도 분석 + 개인화 카드 추천 (핵심)** |
| POST | `/select` | 고른 카드(들) 기록 → 개인화 학습 |
| POST | `/sentence` | 고른 카드 단어들 → 자연스러운 한 문장 |
| GET | `/history/me` | 사용 이력 조회 (최신순) |
| GET | `/profile/me` | 선호 카드 확인 (집계) |

## 실행 방법

```bash
pip install -r requirements.txt
```

`.env` 파일 작성 (`.env.example` 참고):
```
GEMINI_API_KEY=...
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/<database>
JWT_SECRET_KEY=...
AI_SERVER_URL=http://localhost:8001   # malkong/ai, 없어도 서버는 기동됨(장소 인식만 실패)
AI_SERVER_TIMEOUT=10
SENTENCE_TIMEOUT=10
```

```bash
uvicorn app.main:app --reload
# http://localhost:8000/docs 에서 API 테스트
```

MySQL이 없어도 서버는 기동되며(개인화·문장기록만 생략), Gemini 키가 없으면 의도
분석은 고정 fallback으로, `AI_SERVER_URL`에 아무것도 안 떠 있으면 장소 인식만
실패하고 나머지는 정상 동작합니다(graceful degradation).

## 기술 스택

- **서버**: FastAPI + Python, SQLAlchemy(신규 코드) / PyMySQL(레거시 쿼리)
- **의도 분석 · 문장 조합 LLM**: Gemini API (`gemini-3.1-flash-lite`)
- **장소 인식**: 별도 AI 서버(`malkong/ai`)에 사진을 보내 6개 장소 라벨 중 하나를 응답받아 매핑 (모델 구현은 해당 저장소 소관)
- **STT**: Faster-Whisper (CPU)
- **인증**: JWT (`python-jose`), 비밀번호 해싱(`passlib`/`bcrypt`)
- **개인화 저장**: MySQL (`card_history` + `usage_log` 테이블)

## 관련 문서

- [`API_CONTRACT.md`](API_CONTRACT.md) — 팀 전체 API 명세서 (앱 ↔ 서버, 요청/응답 형식)
- [`PLAN_v1.md`](PLAN_v1.md) — 설계 배경, 카드 매칭/개인화 로직 상세, 개발 경과
