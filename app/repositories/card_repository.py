"""cards 테이블 접근 (@Repository).

=============================================================================
TODO(2차 리팩터링): 아직 PyMySQL 생 SQL이다.

  구조 리팩터링 1단계에서는 services/storage.py에 있던 쿼리를 로직 변경 없이
  이 파일로 옮기기만 했다. 2차에서 SQLAlchemy 세션 기반으로 전환한다.

    - get_legacy_connection() 대신 Session을 인자로 받거나 Depends(get_db)로 주입
    - 생 SQL 문자열 -> models.Card 기반 select()
    - json.loads 수동 파싱 -> JSON 컬럼 타입이 자동 처리
=============================================================================

graceful degradation 불변식: 모든 함수는 DB 실패 시 예외를 상위로 전파하지 않고
폴백값(빈 결과)을 반환한다. `/analyze`가 DB 다운으로 500을 내지 않도록 하기 위함이다.
"""
import json
import logging

from app.core.database import DictCursor, get_legacy_connection

logger = logging.getLogger(__name__)


def get_cards_for_mapping() -> list[dict]:
    """cards 테이블 전체 조회. 실패 시 빈 리스트(호출자가 카탈로그 파일로 폴백).

    valid_for_intents는 DB에 JSON 문자열로 저장돼 있어 list로 파싱해 반환한다
    (카탈로그 파일 폴백 경로는 이미 list이므로 호출자 입장에서 형태가 통일된다).
    """
    try:
        conn = get_legacy_connection()
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
