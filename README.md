# AAC Mode 2 백엔드 — 의도 분석 서버

상대방의 발화를 AI가 분석해 맞춤 AAC 단어 카드를 추천하는 FastAPI 서버 모듈입니다.
청각/의사소통 보조가 필요한 사용자가 상대방 말을 쉽게 이해하고, 개인화된 단어 카드로 빠르게 응답할 수 있도록 돕습니다.

이 저장소는 팀 전체 앱(Android)의 백엔드 모듈이며, `web/index.html`은 앱 연동이 늦어질 경우를 대비한 발표용 백업 화면입니다.

## 의도 분석 (Intent Analysis)

핵심 기능은 `POST /analyze`에서 수행하는 **의도 분석**입니다. 상대방 발화(`speech_text`)를 Gemini API(`gemini-3.1-flash-lite`)에 전달해, 아래 5개 필드로 구조화된 결과를 받습니다.

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
- `schemas.py`의 `AnalysisResult.intent`는 `Literal`로 8개 값만 허용
- Gemini 호출 실패 시(`llm.py`) `FALLBACK_ANALYSIS`가 `"기타"` intent로 대체 응답 (서버가 죽지 않음)

### 처리 흐름

```
speech_text
  → llm.py: analyze_intent()  ─┐  Gemini 구조화 출력(response_schema=AnalysisResult)
                                │  실패 시 FALLBACK_ANALYSIS 반환
  → card_generator.py: get_candidate_cards()  ─ intent 기반 AAC 단어 카드 후보 생성
  → (2주차) personalize.py로 개인화 재정렬
  → AnalyzeResponse { analysis, cards }
```

의도 분석 결과는 카드 후보 생성(`card_generator.py`)의 입력으로 그대로 이어지며, `intent`·`intent_detail`·`easy_meaning`을 바탕으로 사용자가 답변할 수 있는 단어 카드(예: "좋아", "싫어", "시간")를 생성합니다.

## API 개요

전체 API 명세는 [`API_CONTRACT.md`](API_CONTRACT.md) 참고.

| 메서드 | 경로 | 역할 |
|------|------|------|
| GET | `/health` | 서버 생존 확인 |
| POST | `/transcribe` | 영상/오디오 → speech_text (Faster-Whisper STT) |
| POST | `/analyze` | **의도 분석 + 카드 추천 (핵심)** |
| POST | `/select` | 고른 카드 기록 → 개인화 학습 |
| GET | `/profile/{user_id}` | 사용자 선호 카드 확인 |

## 실행 방법

```bash
pip install -r requirements.txt
# .env 파일에 GEMINI_API_KEY 설정 (.env.example 참고)
uvicorn app.main:app --reload
# http://localhost:8000/docs 에서 API 테스트
```

## 기술 스택

- **서버**: FastAPI + Python
- **의도 분석 LLM**: Gemini API (`gemini-3.1-flash-lite`)
- **STT**: Faster-Whisper (GPU)
- **개인화 저장**: `data/history.json`

자세한 설계 배경과 주차별 작업 계획은 [`PLAN_v1.md`](PLAN_v1.md) 참고.
