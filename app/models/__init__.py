"""SQLAlchemy ORM 모델 패키지.

=============================================================================
TODO(2차 리팩터링): 아직 3개 테이블이 남아 있다.

  구조 리팩터링 1단계에서는 폴더 배치만 잡고, DB 접근은 기존 PyMySQL 생 SQL을
  그대로 옮겨왔다(repositories/ 참고). 아래 모델들을 정의하고
  app.core.database.Base를 상속시킨다.

    Card        <- cards           (valid_for_intents는 JSON 컬럼)
    CardHistory <- card_history    (UNIQUE (user_id, word))
    UsageLog    <- usage_log

  정의 후에는 data/schema.sql과 core/seed.py의 CREATE TABLE 문자열을 걷어내고,
  이 모델을 스키마의 단일 진실 원천으로 삼는다(Alembic 마이그레이션 도입).
=============================================================================
"""
