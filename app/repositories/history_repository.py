"""card_history / usage_log 테이블 접근 (@Repository).

=============================================================================
TODO(2차 리팩터링): 아직 PyMySQL 생 SQL이다.

  구조 리팩터링 1단계에서는 services/storage.py에 있던 쿼리를 로직 변경 없이
  이 파일로 옮기기만 했다. 2차에서 SQLAlchemy 세션 기반으로 전환한다.

    - get_legacy_connection() 대신 Session 주입
    - INSERT ... ON DUPLICATE KEY UPDATE -> sqlalchemy.dialects.mysql.insert(...).on_duplicate_key_update()
    - 수동 commit/rollback/close -> 세션 컨텍스트가 담당
=============================================================================

graceful degradation 불변식: 모든 함수는 DB 실패 시 예외를 상위로 전파하지 않고
폴백값(빈 결과 / 0 / 실패 신호)을 반환한다. `/select`가 DB 다운으로 500을 내지
않도록 하기 위함이다.
"""
import logging

from app.core.database import DictCursor, get_legacy_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------
def get_usage_counts(user_id: int, card_id: int, intent=None, place=None) -> dict:
    """(user_id, card_id) 기준 count/intent_match/place_match 집계. 실패 시 zeros.

    카드의 정체성은 card_id다(예전에는 word였으나 이름이 바뀌거나 중복되면 깨졌다).

    - count: card_history.count (전역 누적 선택 횟수).
    - intent_match_count: usage_log 중 현재 intent와 일치하는 행 수(intent=None이면 0).
    - place_match_count: usage_log 중 현재 place와 일치하는 행 수(place=None/미기록 제외).
    """
    zeros = {"count": 0, "intent_match_count": 0, "place_match_count": 0}
    if card_id is None:
        return zeros
    try:
        conn = get_legacy_connection()
    except Exception:
        return zeros
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count FROM card_history WHERE user_id=%s AND card_id=%s",
                (user_id, card_id),
            )
            row = cur.fetchone()
            count = int(row[0]) if row else 0

            intent_match = 0
            if intent:
                cur.execute(
                    "SELECT COUNT(*) FROM usage_log "
                    "WHERE user_id=%s AND card_id=%s AND intent=%s AND intent IS NOT NULL",
                    (user_id, card_id, intent),
                )
                intent_match = int(cur.fetchone()[0])

            place_match = 0
            if place:
                cur.execute(
                    "SELECT COUNT(*) FROM usage_log "
                    "WHERE user_id=%s AND card_id=%s AND place=%s AND place IS NOT NULL",
                    (user_id, card_id, place),
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
        conn = get_legacy_connection()
    except Exception:
        return []
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(
                "SELECT word, category, count, card_id FROM card_history "
                "WHERE user_id=%s ORDER BY count DESC, card_id ASC LIMIT %s",
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

    카운팅 키는 (user_id, card_id)다. card_id가 없으면 기록하지 않고 (False, 0)을 반환한다
    (card_history.card_id / usage_log.card_id가 NOT NULL이므로 저장 자체가 불가능).
    word/category는 키가 아니라 표시·디버깅용이지만 매번 최신 값으로 갱신한다.

    실패 시 (False, 0) 반환, 예외 전파 없음.
    반환: (성공 여부, 갱신된 card_history.count).
    """
    card_id = getattr(card, "card_id", None)
    if card_id is None:
        logger.warning("record_selection: card_id가 없어 기록을 건너뜁니다.")
        return False, 0
    word = getattr(card, "word", None)
    if not word:
        return False, 0
    category = getattr(card, "category", None)
    intent = getattr(context, "intent", None) if context is not None else None
    place = getattr(context, "place", None) if context is not None else None

    try:
        conn = get_legacy_connection()
    except Exception as e:
        logger.warning("record_selection: DB 연결 실패(%s), (False, 0) 반환.", e)
        return False, 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                # UNIQUE 키가 (user_id, card_id)이므로 ON DUPLICATE는 그 키로 걸린다.
                # word/category는 키가 아니므로 최신 값으로 계속 갱신한다(카드 이름 변경 반영).
                "INSERT INTO card_history (user_id, word, card_id, category, count, last_used) "
                "VALUES (%s, %s, %s, %s, 1, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "  count = count + 1, "
                "  last_used = NOW(), "
                "  word = VALUES(word), "
                "  category = COALESCE(VALUES(category), category)",
                (user_id, word, card_id, category),
            )
            cur.execute(
                "INSERT INTO usage_log (user_id, word, category, card_id, intent, place, selected_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                (user_id, word, category, card_id, intent, place),
            )
            cur.execute(
                "SELECT count FROM card_history WHERE user_id=%s AND card_id=%s",
                (user_id, card_id),
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
