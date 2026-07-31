"""DB 초기화(DDL) + 카탈로그 시딩.

=============================================================================
TODO(2차 리팩터링): 이 파일 전체가 임시다.

  - init_db()의 CREATE TABLE 문자열은 data/schema.sql과 내용이 중복된다.
    (컬럼 하나 추가할 때 두 곳을 손으로 맞춰야 하고, 실제로 valid_for_intents
     추가 때 그랬다.) 2차에서 models/의 SQLAlchemy 모델을 단일 진실 원천으로
     삼고, 스키마 변경은 Alembic 마이그레이션으로 옮긴다.
  - CREATE TABLE IF NOT EXISTS 방식은 "테이블이 이미 있으면" 컬럼 추가를
    감지하지 못한다. 이것도 Alembic으로 해결할 항목.
  - seed_cards()는 마이그레이션과 분리된 별도 시드 스크립트로 뺀다.
=============================================================================
"""
import json
import logging
from pathlib import Path

from app.core.database import engine, get_legacy_connection, get_legacy_db_name
from app.core.security import hash_password
from app.core.utils import normalize_image_url
from app.models.user import User

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cards_catalog.json"

# AAC 개인화용 데모 계정. card_history/usage_log가 users.id를 FK로 참조하므로 이 행이
# 없으면 /select가 FK 위반으로 전부 실패한다.
DEMO_USER_ID = 1
DEMO_USER_EMAIL = "tester@gmail.com"
DEMO_USER_PASSWORD = "demo1234"
DEMO_USER_NICKNAME = "테스터"


def init_db() -> bool:
    """DB/테이블 생성 + 데모 유저(id=1) + 카탈로그 카드 seed. 모두 idempotent.

    MySQL 미가용 시 예외를 삼키고 False를 반환한다(서버는 계속 기동).
    """
    db_name = get_legacy_db_name()
    try:
        conn = get_legacy_connection(with_db=False)
    except Exception as e:
        logger.warning("DB 연결 실패(%s)로 init_db를 건너뜁니다(개인화 비활성).", e)
        return False

    try:
        with conn.cursor() as cur:
            # RDS의 애플리케이션 계정에는 보통 CREATE DATABASE 권한이 없다.
            # 로컬 개발(DB가 아직 없는 경우)을 위해 시도하되, 실패해도 계속 진행한다.
            try:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            except Exception as e:
                logger.info(
                    "CREATE DATABASE 생략(%s). 이미 존재하는 `%s`를 사용합니다.", e, db_name
                )
            cur.execute(f"USE `{db_name}`")
            # users의 DDL은 models/user.py가 단일 정의 원천이다. 아래 테이블들이
            # users.id를 FK로 참조하므로 반드시 먼저 생성한다.
            User.__table__.create(bind=engine, checkfirst=True)
            cur.execute(
                "CREATE TABLE IF NOT EXISTS cards ("
                "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "  name VARCHAR(128) NOT NULL,"
                "  category VARCHAR(32) NOT NULL,"
                "  context VARCHAR(32) NOT NULL,"
                "  intention VARCHAR(32) NULL,"
                "  image_url VARCHAR(512) NULL,"
                "  valid_for_intents JSON NULL,"
                "  UNIQUE KEY uq_card_name (name)"
                ") CHARACTER SET utf8mb4"
            )
            cur.execute(
                # 카운팅 키는 (user_id, card_id). word/category는 표시·디버깅용으로만 남긴다.
                "CREATE TABLE IF NOT EXISTS card_history ("
                "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "  user_id BIGINT NOT NULL,"
                "  word VARCHAR(64) NOT NULL,"
                "  card_id BIGINT NOT NULL,"
                "  category VARCHAR(32) NULL,"
                "  count INT NOT NULL DEFAULT 0,"
                "  last_used DATETIME NULL,"
                "  UNIQUE KEY uq_user_card (user_id, card_id),"
                "  CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES users(id)"
                ") CHARACTER SET utf8mb4"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS usage_log ("
                "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "  user_id BIGINT NOT NULL,"
                "  word VARCHAR(64) NOT NULL,"
                "  category VARCHAR(32) NULL,"
                "  card_id BIGINT NOT NULL,"
                "  intent VARCHAR(16) NULL,"
                "  place VARCHAR(32) NULL,"
                "  selected_at DATETIME NULL,"
                # DEFAULT 'select' 덕분에 record_selection의 INSERT는 컬럼을 명시하지
                # 않아도 자동으로 'select'가 들어간다. 온보딩만 명시적으로 지정한다.
                "  source VARCHAR(16) NOT NULL DEFAULT 'select',"
                "  CONSTRAINT fk_usage_user FOREIGN KEY (user_id) REFERENCES users(id)"
                ") CHARACTER SET utf8mb4"
            )
            _seed_demo_user(cur)
            seed_cards(cur)
        conn.commit()
        logger.info("init_db 완료 (DB=%s)", db_name)
        return True
    except Exception:
        logger.warning("init_db 중 오류 발생.", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _seed_demo_user(cur) -> None:
    """데모 유저(id=1) 생성
    """
    cur.execute("SELECT 1 FROM users WHERE id=%s", (DEMO_USER_ID,))
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO users (id, email, password, nickname) VALUES (%s, %s, %s, %s)",
        (
            DEMO_USER_ID,
            DEMO_USER_EMAIL,
            hash_password(DEMO_USER_PASSWORD),
            DEMO_USER_NICKNAME,
        ),
    )
    logger.info("데모 유저(id=%s) 생성 완료.", DEMO_USER_ID)


def seed_cards(cur) -> None:
    """cards_catalog.json을 cards 테이블에 idempotent 적재. intention=NULL 그대로 적재.

    image_url은 embeddable 썸네일 형식으로 정규화(normalize_image_url)해서 저장한다.
    이미 시딩된 기존 행도 매 startup마다 정규화된 값(image_url/valid_for_intents)으로
    UPDATE한다(과거에 원본 구글드라이브 '보기' 링크로 저장된 데이터, 또는 카탈로그
    파일에서만 갱신된 valid_for_intents를 재시딩 없이 자동 교정하기 위함).

    valid_for_intents: 카드가 응답으로 적절한 "상대방 intent" 리스트. JSON 배열로 저장.
    카탈로그 파일의 intention과는 축이 다르므로 별도 컬럼(매핑에는 이 필드만 사용).
    """
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            catalog = json.load(f)
    except Exception:
        logger.warning("cards_catalog.json 로드 실패, 카드 seed 건너뜀.", exc_info=True)
        return
    rows = [
        (
            c.get("id"),  # 파일의 id를 그대로 적재 — 파일 폴백 경로의 card_id와 DB id가 일치해야 한다
            c.get("name"),
            c.get("category"),
            c.get("context"),
            c.get("intention"),  # None이면 NULL로 적재
            normalize_image_url(c.get("image_url")),
            json.dumps(c.get("valid_for_intents") or [], ensure_ascii=False),
        )
        for c in catalog
    ]
    cur.executemany(
        "INSERT IGNORE INTO cards (id, name, category, context, intention, image_url, valid_for_intents) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    # 기존에 이미 적재된 행도 정규화된 image_url/valid_for_intents로 보정.
    cur.executemany(
        "UPDATE cards SET image_url = %s, valid_for_intents = %s WHERE name = %s",
        [(image_url, tags_json, name) for _, name, _, _, _, image_url, tags_json in rows],
    )
