"""MySQL 접속/쿼리 계층 (PyMySQL).

graceful degradation 불변식: 모든 함수는 DB 실패 시 예외를 상위로 전파하지 않고
폴백값(빈 결과 / 0 / 실패 신호)을 반환한다. `/analyze`·`/select`가 DB 다운으로
500을 내지 않도록 하기 위함이다.
"""
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# pymysql 미설치 상태에서도 `import app.main`이 깨지지 않도록 lazy-safe import.
try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:  # pragma: no cover - 설치 안 된 환경 방어
    pymysql = None
    DictCursor = None

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cards_catalog.json"

DEMO_USER_ID = 1


def _db_config() -> dict:
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "charset": "utf8mb4",
    }


def _connect(with_db: bool = True):
    """PyMySQL 커넥션 반환. 실패 시 예외를 던진다(호출자가 잡아 폴백)."""
    if pymysql is None:
        raise RuntimeError("PyMySQL이 설치되어 있지 않습니다.")
    config = _db_config()
    if with_db:
        config["database"] = os.getenv("DB_NAME", "aac")
    return pymysql.connect(**config)


# ---------------------------------------------------------------------------
# init / seed
# ---------------------------------------------------------------------------
def init_db() -> bool:
    """DB/테이블 생성 + 데모 유저(id=1) + 카탈로그 카드 seed. 모두 idempotent.

    MySQL 미가용 시 예외를 삼키고 False를 반환한다(서버는 계속 기동).
    """
    db_name = os.getenv("DB_NAME", "aac")
    try:
        conn = _connect(with_db=False)
    except Exception as e:
        logger.warning("DB 연결 실패(%s)로 init_db를 건너뜁니다(개인화 비활성).", e)
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(f"USE `{db_name}`")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "  id BIGINT PRIMARY KEY"
                ") CHARACTER SET utf8mb4"
            )
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
                "CREATE TABLE IF NOT EXISTS card_history ("
                "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "  user_id BIGINT NOT NULL,"
                "  word VARCHAR(64) NOT NULL,"
                "  card_id BIGINT NULL,"
                "  category VARCHAR(32) NULL,"
                "  count INT NOT NULL DEFAULT 0,"
                "  last_used DATETIME NULL,"
                "  UNIQUE KEY uq_user_word (user_id, word),"
                "  CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES users(id)"
                ") CHARACTER SET utf8mb4"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS usage_log ("
                "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "  user_id BIGINT NOT NULL,"
                "  word VARCHAR(64) NOT NULL,"
                "  category VARCHAR(32) NULL,"
                "  card_id BIGINT NULL,"
                "  intent VARCHAR(16) NULL,"
                "  place VARCHAR(32) NULL,"
                "  selected_at DATETIME NULL,"
                "  CONSTRAINT fk_usage_user FOREIGN KEY (user_id) REFERENCES users(id)"
                ") CHARACTER SET utf8mb4"
            )
            cur.execute("INSERT IGNORE INTO users (id) VALUES (%s)", (DEMO_USER_ID,))
            _seed_cards(cur)
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


_DRIVE_FILE_ID_RE = re.compile(r"drive\.google\.com/file/d/([^/]+)/")


def _normalize_image_url(url):
    """구글드라이브 '보기' 페이지 링크(.../file/d/{id}/view)를 <img>에 바로 넣을 수 있는
    썸네일 리소스 URL로 변환한다. 패턴이 없으면(다른 호스트 등) 원본을 그대로 반환한다.
    """
    if not url:
        return url
    m = _DRIVE_FILE_ID_RE.search(url)
    if not m:
        return url
    file_id = m.group(1)
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"


def _seed_cards(cur) -> None:
    """cards_catalog.json을 cards 테이블에 idempotent 적재. intention=NULL 그대로 적재.

    image_url은 embeddable 썸네일 형식으로 정규화(_normalize_image_url)해서 저장한다.
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
            c.get("name"),
            c.get("category"),
            c.get("context"),
            c.get("intention"),  # None이면 NULL로 적재
            _normalize_image_url(c.get("image_url")),
            json.dumps(c.get("valid_for_intents") or [], ensure_ascii=False),
        )
        for c in catalog
    ]
    cur.executemany(
        "INSERT IGNORE INTO cards (name, category, context, intention, image_url, valid_for_intents) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        rows,
    )
    # 기존에 이미 적재된 행도 정규화된 image_url/valid_for_intents로 보정.
    cur.executemany(
        "UPDATE cards SET image_url = %s, valid_for_intents = %s WHERE name = %s",
        [(image_url, tags_json, name) for name, _, _, _, image_url, tags_json in rows],
    )


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------
def get_cards_for_mapping() -> list[dict]:
    """cards 테이블 전체 조회. 실패 시 빈 리스트(호출자가 카탈로그 파일로 폴백).

    valid_for_intents는 DB에 JSON 문자열로 저장돼 있어 list로 파싱해 반환한다
    (카탈로그 파일 폴백 경로는 이미 list이므로 호출자 입장에서 형태가 통일된다).
    """
    try:
        conn = _connect()
    except Exception as e:
        logger.warning("get_cards_for_mapping: DB 연결 실패(%s), 카탈로그 파일 폴백.", e)
        return []
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(
                "SELECT id, name, category, context, intention, image_url, "
                "valid_for_intents FROM cards"
            )
            rows = list(cur.fetchall())
            for row in rows:
                raw = row.get("valid_for_intents")
                row["valid_for_intents"] = json.loads(raw) if raw else []
            return rows
    except Exception:
        logger.warning("get_cards_for_mapping: 조회 실패.", exc_info=True)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_usage_counts(user_id: int, word: str, intent=None, place=None) -> dict:
    """(user_id, word) 기준 count/intent_match/place_match 집계. 실패 시 zeros.

    - count: card_history.count (전역 누적 선택 횟수).
    - intent_match_count: usage_log 중 현재 intent와 일치하는 행 수(intent=None이면 0).
    - place_match_count: usage_log 중 현재 place와 일치하는 행 수(place=None/미기록 제외).
    """
    zeros = {"count": 0, "intent_match_count": 0, "place_match_count": 0}
    try:
        conn = _connect()
    except Exception:
        return zeros
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count FROM card_history WHERE user_id=%s AND word=%s",
                (user_id, word),
            )
            row = cur.fetchone()
            count = int(row[0]) if row else 0

            intent_match = 0
            if intent:
                cur.execute(
                    "SELECT COUNT(*) FROM usage_log "
                    "WHERE user_id=%s AND word=%s AND intent=%s AND intent IS NOT NULL",
                    (user_id, word, intent),
                )
                intent_match = int(cur.fetchone()[0])

            place_match = 0
            if place:
                cur.execute(
                    "SELECT COUNT(*) FROM usage_log "
                    "WHERE user_id=%s AND word=%s AND place=%s AND place IS NOT NULL",
                    (user_id, word, place),
                )
                place_match = int(cur.fetchone()[0])

            return {
                "count": count,
                "intent_match_count": intent_match,
                "place_match_count": place_match,
            }
    except Exception:
        logger.warning("get_usage_counts: 집계 실패, zeros 반환.", exc_info=True)
        return zeros
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_top_cards(user_id: int, limit: int = 20) -> list[dict]:
    """/profile용 상위 카드. 실패 시 빈 리스트."""
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(
                "SELECT word, category, count, card_id FROM card_history "
                "WHERE user_id=%s ORDER BY count DESC, word ASC LIMIT %s",
                (user_id, limit),
            )
            return list(cur.fetchall())
    except Exception:
        logger.warning("get_top_cards: 조회 실패.", exc_info=True)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
def record_selection(user_id: int, card, context=None) -> tuple[bool, int]:
    """card_history UPSERT + usage_log INSERT를 단일 트랜잭션으로 기록.

    card.card_id가 없으면 NULL 저장(문자열 더미 금지). 실패 시 (False, 0) 반환, 예외 전파 없음.
    반환: (성공 여부, 갱신된 card_history.count).
    """
    word = getattr(card, "word", None)
    if not word:
        return False, 0
    category = getattr(card, "category", None)
    card_id = getattr(card, "card_id", None)
    intent = getattr(context, "intent", None) if context is not None else None
    place = getattr(context, "place", None) if context is not None else None

    try:
        conn = _connect()
    except Exception as e:
        logger.warning("record_selection: DB 연결 실패(%s), (False, 0) 반환.", e)
        return False, 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO card_history (user_id, word, card_id, category, count, last_used) "
                "VALUES (%s, %s, %s, %s, 1, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "  count = count + 1, "
                "  last_used = NOW(), "
                "  card_id = COALESCE(VALUES(card_id), card_id), "
                "  category = COALESCE(VALUES(category), category)",
                (user_id, word, card_id, category),
            )
            cur.execute(
                "INSERT INTO usage_log (user_id, word, category, card_id, intent, place, selected_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                (user_id, word, category, card_id, intent, place),
            )
            cur.execute(
                "SELECT count FROM card_history WHERE user_id=%s AND word=%s",
                (user_id, word),
            )
            row = cur.fetchone()
            new_count = int(row[0]) if row else 0
        conn.commit()
        return True, new_count
    except Exception:
        logger.warning("record_selection: 기록 실패, 롤백 후 (False, 0) 반환.", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return False, 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
