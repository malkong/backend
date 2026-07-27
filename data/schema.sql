-- AAC Mode 2 — DB 스키마 (선택적 엄격, Selective Strictness 단일 DDL)
-- 제약(FK/NOT NULL)은 "항상 값이 보장되는 컬럼에만" 건다.
--   FK   : card_history.user_id -> users.id, usage_log.user_id -> users.id (2개만)
--   NOTNULL: cards.name/category/context, 로그의 user_id/word
--   nullable & FK 없음: 모든 card_id, cards.intention, usage_log.intent/place
-- storage.init_db()가 이 스키마를 참조하지 않고 코드에서 직접 생성하지만,
-- 문서/수동 초기화용으로 동일 DDL을 여기에 보존한다.

CREATE DATABASE IF NOT EXISTS aac CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aac;

-- 데모 유저 1명(id=1)만. 로그인/회원가입은 스코프 밖.
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY
) CHARACTER SET utf8mb4;

INSERT IGNORE INTO users (id) VALUES (1);

-- 카탈로그 카드. intention은 NULL 허용(화요일/환승역 2건이 NULL).
-- valid_for_intents: 이 카드가 "상대방의 어떤 intent"에 대한 응답으로 적절한지 태깅한
-- 리스트(JSON 배열, 예: ["요청","제안","확인"]). intention과는 축이 다르다 —
-- intention은 "카드 자체(사용자)의 발화 유형", valid_for_intents는 "상대방 intent"다.
-- 매핑(card_generator._tier_for)은 이 필드만 사용하고 intention은 참고용으로 남긴다.
CREATE TABLE IF NOT EXISTS cards (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  name               VARCHAR(128) NOT NULL,
  category           VARCHAR(32)  NOT NULL,
  context            VARCHAR(32)  NOT NULL,
  intention          VARCHAR(32)  NULL,
  image_url          VARCHAR(512) NULL,
  valid_for_intents  JSON         NULL,
  UNIQUE KEY uq_card_name (name)
) CHARACTER SET utf8mb4;

-- 집계 테이블. 카운팅 키 (user_id, word). card_id는 FK 없음·nullable.
CREATE TABLE IF NOT EXISTS card_history (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id   BIGINT       NOT NULL,
  word      VARCHAR(64)  NOT NULL,
  card_id   BIGINT       NULL,
  category  VARCHAR(32)  NULL,
  count     INT          NOT NULL DEFAULT 0,
  last_used DATETIME     NULL,
  UNIQUE KEY uq_user_word (user_id, word),
  CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES users(id)
) CHARACTER SET utf8mb4;

-- 이벤트 로그(append-only). card_id는 FK 없음·nullable. place는 한글 7종 값 도메인.
CREATE TABLE IF NOT EXISTS usage_log (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     BIGINT       NOT NULL,
  word        VARCHAR(64)  NOT NULL,
  category    VARCHAR(32)  NULL,
  card_id     BIGINT       NULL,
  intent      VARCHAR(16)  NULL,
  place       VARCHAR(32)  NULL,
  selected_at DATETIME     NULL,
  CONSTRAINT fk_usage_user FOREIGN KEY (user_id) REFERENCES users(id)
) CHARACTER SET utf8mb4;
