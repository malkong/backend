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
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # GEMINI_API_KEY 등 아직 여기서 안 읽는 키는 무시
    )

    DATABASE_URL: str
    JWT_SECRET_KEY: str


settings = Settings()
