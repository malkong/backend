from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# 비밀번호
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """평문 비밀번호를 bcrypt 해시로 변환한다."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """평문과 저장된 해시를 비교한다. 해시 형식이 깨져 있어도 예외 대신 False."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_access_token(user_id: int, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    """user_id를 sub 클레임에 담은 액세스 토큰을 발급한다.

    sub는 JWT 표준상 문자열이어야 하므로 str로 변환해 넣는다(디코드 측에서 int 복원).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """토큰을 검증하고 페이로드를 반환한다. 서명 불일치/만료/형식 오류면 None."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_user_id_from_token(token: str) -> int | None:
    """토큰에서 user_id(sub)를 꺼낸다. 유효하지 않으면 None."""
    payload = decode_access_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
