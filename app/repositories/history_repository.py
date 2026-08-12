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


def _in_placeholders(items: list) -> str:
    """`IN (%s, %s, ...)` 절에 쓸 placeholder 문자열. get_usage_counts_bulk/record_selection이
    공유하는 단일 소스 — IN절 크기 제한 같은 걸 손볼 때 한 곳만 고치면 되게 한다."""
    return ",".join(["%s"] * len(items))


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------
def get_usage_counts_bulk(user_id: int, card_ids: list[int], intent=None, place=None) -> dict:
    """card_ids 전체의 count/intent_match/place_match를 커넥션 하나로 집계.

    카드마다 커넥션을 새로 열던 get_usage_counts(단일)를 대체한다 — /analyze가
    카드 8장을 rerank할 때 커넥션 8~9개를 열어 응답이 느려지는 문제가 있었다.

    카드의 정체성은 card_id다(예전에는 word였으나 이름이 바뀌거나 중복되면 깨졌다).

    반환: {card_id: {"count", "intent_match_count", "place_match_count"}}.
    요청한 card_ids 전부에 대해 항목이 채워지며(이력이 없으면 0), 실패 시 빈 dict
    (호출자가 각 카드에 대해 .get(card_id)가 None → 0으로 처리해야 함).
    """
    card_ids = [cid for cid in dict.fromkeys(card_ids) if cid is not None]
    if not card_ids:
        return {}
    try:
        conn = get_legacy_connection()
    except Exception:
        return {}
    try:
        placeholders = _in_placeholders(card_ids)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT card_id, count FROM card_history "
                f"WHERE user_id=%s AND card_id IN ({placeholders})",
                (user_id, *card_ids),
            )
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}

            intent_matches = {}
            if intent:
                cur.execute(
                    f"SELECT card_id, COUNT(*) FROM usage_log "
                    f"WHERE user_id=%s AND card_id IN ({placeholders}) "
                    f"AND intent=%s AND intent IS NOT NULL GROUP BY card_id",
                    (user_id, *card_ids, intent),
                )
                intent_matches = {row[0]: int(row[1]) for row in cur.fetchall()}

            place_matches = {}
            if place:
                cur.execute(
                    f"SELECT card_id, COUNT(*) FROM usage_log "
                    f"WHERE user_id=%s AND card_id IN ({placeholders}) "
                    f"AND place=%s AND place IS NOT NULL GROUP BY card_id",
                    (user_id, *card_ids, place),
                )
                place_matches = {row[0]: int(row[1]) for row in cur.fetchall()}

        return {
            cid: {
                "count": counts.get(cid, 0),
                "intent_match_count": intent_matches.get(cid, 0),
                "place_match_count": place_matches.get(cid, 0),
            }
            for cid in card_ids
        }
    except Exception:
        logger.warning("get_usage_counts_bulk: 집계 실패, 빈 dict 반환.", exc_info=True)
        return {}
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
def record_selection(user_id: int, cards: list, context=None) -> tuple[bool, list[dict]]:
    """card_history UPSERT + usage_log INSERT를 카드 여러 장에 대해 단일 트랜잭션으로 기록.

    한 문장에 쓴 카드 여러 장(예: "이거"+"주세요")을 한 번에 기록한다. record_onboarding과
    같은 executemany + 단일 트랜잭션 패턴을 쓴다 — N행이 같은 NOW()로 들어가므로
    usage_log에서 시각이 같은 행끼리가 한 문장이었음을 알 수 있다.

    카운팅 키는 (user_id, card_id)다. card_id/word가 없는 카드는 건너뛴다
    (card_history.card_id / usage_log.card_id가 NOT NULL이므로 저장 자체가 불가능).
    같은 요청 안에서 card_id가 중복되면 처음 것만 남긴다 — UPSERT가 같은 키를 두 번 치면
    count가 2 올라가 버린다(온보딩 코드도 같은 이유로 중복을 제거한다).
    word/category는 키가 아니라 표시·디버깅용이지만 매번 최신 값으로 갱신한다.

    실패/유효한 카드 없음 시 (False, []) 반환, 예외 전파 없음.
    반환: (성공 여부, [{"card_id", "new_count"}, ...]) — 유효한 카드의 등장 순서를 유지.
    """
    intent = getattr(context, "intent", None) if context is not None else None
    place = getattr(context, "place", None) if context is not None else None

    seen: set = set()
    items: list[tuple] = []
    for card in cards:
        card_id = getattr(card, "card_id", None)
        word = getattr(card, "word", None)
        if card_id is None or not word:
            logger.warning("record_selection: card_id/word가 없는 카드를 건너뜁니다.")
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        items.append((card_id, word, getattr(card, "category", None)))

    if not items:
        return False, []

    try:
        conn = get_legacy_connection()
    except Exception as e:
        logger.warning("record_selection: DB 연결 실패(%s), (False, []) 반환.", e)
        return False, []

    try:
        with conn.cursor() as cur:
            # UNIQUE 키가 (user_id, card_id)이므로 ON DUPLICATE는 그 키로 걸린다.
            # word/category는 키가 아니므로 최신 값으로 계속 갱신한다(카드 이름 변경 반영).
            cur.executemany(
                "INSERT INTO card_history (user_id, word, card_id, category, count, last_used) "
                "VALUES (%s, %s, %s, %s, 1, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "  count = count + 1, "
                "  last_used = NOW(), "
                "  word = VALUES(word), "
                "  category = COALESCE(VALUES(category), category)",
                [(user_id, word, card_id, category) for card_id, word, category in items],
            )
            cur.executemany(
                "INSERT INTO usage_log (user_id, word, category, card_id, intent, place, selected_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                [
                    (user_id, word, category, card_id, intent, place)
                    for card_id, word, category in items
                ],
            )
            card_ids = [card_id for card_id, _, _ in items]
            placeholders = _in_placeholders(card_ids)
            cur.execute(
                f"SELECT card_id, count FROM card_history "
                f"WHERE user_id=%s AND card_id IN ({placeholders})",
                (user_id, *card_ids),
            )
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
        conn.commit()
        results = [{"card_id": cid, "new_count": counts.get(cid, 0)} for cid in card_ids]
        return True, results
    except Exception:
        logger.warning("record_selection: 기록 실패, 롤백 후 (False, []) 반환.", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return False, []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def record_onboarding(user_id: int, items: list[dict], usage_rows_per_card: int = 4) -> bool:
    """온보딩 선택을 card_history/usage_log에 기록하고 users.is_onboarded를 세운다.

    record_selection과 같은 SQL 형태를 쓰되, 세 가지가 다르다:
      1) 카드 여러 장을 executemany로 묶어 **단일 트랜잭션**으로 처리한다.
      2) card_history의 초기 count가 4이고, 이미 행이 있으면 GREATEST(count, 4)로
         "최소 4 보장"만 한다(온보딩은 최초 1회뿐이라 누적이 아니다).
      3) usage_log에 카드당 4행을 INSERT한다 — place_match_count 보너스가
         count 보너스와 같은 비중으로 작동하려면 이력 행 수가 필요하기 때문이다.

    is_onboarded 갱신을 같은 트랜잭션의 **맨 앞**에서 `WHERE is_onboarded = 0` 가드와
    함께 수행한다. 동시 요청이 둘 다 409 검사를 통과해도 UPDATE에 성공한 쪽만 남고
    나머지는 rowcount=0으로 감지되어 롤백된다.

    items: [{"card_id": int, "word": str, "category": str|None, "place": str}, ...]
    반환: 성공 여부. 이미 온보딩된 유저면 False(호출자가 409로 변환).
    """
    if not items:
        return False

    try:
        conn = get_legacy_connection()
    except Exception as e:
        logger.warning("record_onboarding: DB 연결 실패(%s).", e)
        return False

    try:
        with conn.cursor() as cur:
            # 경합 방어: 이미 온보딩된 유저면 여기서 0행이 되어 아래에서 롤백된다.
            cur.execute(
                "UPDATE users SET is_onboarded = 1 WHERE id = %s AND is_onboarded = 0",
                (user_id,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                logger.info("record_onboarding: 이미 온보딩된 유저(user_id=%s).", user_id)
                return False

            history_rows = [
                (user_id, it["word"], it["card_id"], it.get("category"))
                for it in items
            ]
            cur.executemany(
                "INSERT INTO card_history (user_id, word, card_id, category, count, last_used) "
                "VALUES (%s, %s, %s, %s, 4, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "  count = GREATEST(count, 4), "
                "  last_used = NOW(), "
                "  word = VALUES(word), "
                "  category = COALESCE(VALUES(category), category)",
                history_rows,
            )

            # intent는 온보딩 시점에 알 수 없으므로 NULL. place는 선택한 context 값.
            usage_rows = [
                (user_id, it["word"], it.get("category"), it["card_id"], None, it["place"])
                for it in items
                for _ in range(usage_rows_per_card)
            ]
            # source='onboarding' — 이력 조회(GET /history/me)에서 걸러내기 위한 표시.
            # 개인화 집계(get_usage_counts_bulk)는 이 값을 보지 않고 온보딩 행도 그대로 센다.
            cur.executemany(
                "INSERT INTO usage_log "
                "(user_id, word, category, card_id, intent, place, selected_at, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'onboarding')",
                usage_rows,
            )
        conn.commit()
        logger.info(
            "record_onboarding 완료: user_id=%s, 카드 %d장, usage_log %d행",
            user_id, len(items), len(items) * usage_rows_per_card,
        )
        return True
    except Exception:
        logger.warning("record_onboarding: 기록 실패, 롤백.", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_history(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """사용 이력을 최신순으로 조회한다(GET /history/me).

    source='select'로 필터링해 온보딩으로 심어진 행을 제외한다. 온보딩은 카드당 4행을
    같은 시각에 넣기 때문에, 걸러내지 않으면 이력 화면이 같은 카드 4번 반복으로 도배된다.

    주의: 이 필터는 이력 조회 전용이다. 개인화 집계(get_usage_counts_bulk)에는 절대 넣지 마라 —
    온보딩 행을 빼면 콜드 스타트 보정이 사라져 온보딩 기능이 조용히 무의미해진다.

    cards와 LEFT JOIN해 image_url을 함께 반환한다(카드가 삭제됐어도 이력은 남긴다).
    실패 시 빈 리스트.
    """
    try:
        conn = get_legacy_connection()
    except Exception as e:
        logger.warning("get_history: DB 연결 실패(%s), 빈 리스트 반환.", e)
        return []
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(
                "SELECT u.word, u.place, u.card_id, c.image_url, u.selected_at "
                "FROM usage_log u "
                "LEFT JOIN cards c ON c.id = u.card_id "
                "WHERE u.user_id = %s AND u.source = 'select' "
                "ORDER BY u.selected_at DESC, u.id DESC "
                "LIMIT %s OFFSET %s",
                (user_id, limit, offset),
            )
            return list(cur.fetchall())
    except Exception:
        logger.warning("get_history: 조회 실패.", exc_info=True)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
