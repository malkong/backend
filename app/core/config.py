"""애플리케이션 설정 — .env 값을 읽어 검증하는 단일 진입점.

값 자체는 .env(git 제외)에 있고, 이 파일은 그 값을 "어떤 이름·타입으로 읽을지"를
선언한다. 필수 항목이 .env에 없으면 서버 기동 시점에 즉시 ValidationError로 죽는다
(예전처럼 os.getenv 기본값으로 조용히 넘어가지 않는다).

TODO(2차 리팩터링): GEMINI_API_KEY / STT_MODEL_SIZE / STT_DEVICE / STT_COMPUTE_TYPE은
    아직 services/llm.py, services/stt.py가 각자 load_dotenv() + os.getenv()로 읽고 있다.
    2차에서 이 Settings로 흡수하고 각 모듈의 load_dotenv() 호출을 제거할 것.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 루트 (app/core/config.py -> app/core -> app -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """.env에서 읽어오는 설정값.

    DATABASE_URL: SQLAlchemy 접속 URL. 예)
        mysql+pymysql://<user>:<password>@<host>:3306/<database>
    JWT_SECRET_KEY: 토큰 서명 키. 회원가입/로그인 기능에서 사용.
    AI_SERVER_URL: 장면 인식 AI 서버 주소. /scene이 여기 /predict를 호출한다.
    AI_SERVER_TIMEOUT: AI 서버 호출 타임아웃(초). 초과 시 장소 인식은 실패로 처리되지만
        앱이 멈추지 않도록 200 + context=null을 반환한다.

    AI_SERVER_*는 기본값이 있어 .env에 없어도 서버가 기동한다(장면 인식만 실패).
    필수로 만들면 .env를 아직 갱신하지 않은 팀원의 서버가 통째로 죽는다.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # GEMINI_API_KEY 등 아직 여기서 안 읽는 키는 무시
    )

    DATABASE_URL: str
    JWT_SECRET_KEY: str
    AI_SERVER_URL: str = "http://localhost:8001"
    AI_SERVER_TIMEOUT: float = 10.0


settings = Settings()
