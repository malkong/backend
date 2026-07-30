from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_user_id_from_token
from app.models.user import User
from app.repositories import user_repository

# auto_error=True: 헤더가 없거나 Bearer 형식이 아니면 FastAPI가 403을 반환한다.
bearer_scheme = HTTPBearer()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="유효하지 않은 인증 정보입니다.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authorization: Bearer 토큰을 검증하고 해당 User를 반환한다. 실패 시 401.

    토큰 서명이 유효해도 그 사이 유저가 삭제됐을 수 있으므로 DB 존재 여부까지 확인한다.
    """
    user_id = get_user_id_from_token(credentials.credentials)
    if user_id is None:
        raise _UNAUTHORIZED

    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise _UNAUTHORIZED
    return user
