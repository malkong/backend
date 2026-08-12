import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """인증 관련 도메인 예외의 베이스."""


class EmailAlreadyExistsError(AuthError):
    """이미 가입된 이메일로 회원가입을 시도한 경우."""


class InvalidCredentialsError(AuthError):
    """이메일이 없거나 비밀번호가 일치하지 않는 경우."""


def signup(db: Session, request: SignupRequest) -> User:
    """이메일 중복 확인 → 비밀번호 해싱 → 저장.

    중복 검사를 먼저 하지만, 그 사이 동시 요청이 끼어들 수 있으므로 DB의 UNIQUE 제약
    위반(IntegrityError)도 같은 예외로 변환한다(검사-사용 경합 방어).
    """
    if user_repository.get_user_by_email(db, request.email) is not None:
        raise EmailAlreadyExistsError(request.email)

    try:
        return user_repository.create_user(
            db,
            email=request.email,
            hashed_password=hash_password(request.password),
            nickname=request.nickname,
        )
    except IntegrityError:
        db.rollback()
        logger.info("signup: UNIQUE 제약 위반(동시 가입 경합). email=%s", request.email)
        raise EmailAlreadyExistsError(request.email) from None


def login(db: Session, request: LoginRequest) -> LoginResponse:
    """비밀번호 검증 후 액세스 토큰 발급.

    이메일이 없는 경우와 비밀번호가 틀린 경우를 같은 예외로 처리한다 — 어느 쪽인지
    구분해 알려주면 가입된 이메일 목록을 캐낼 수 있기 때문이다(user enumeration 방지).
    """
    user = user_repository.get_user_by_email(db, request.email)
    if user is None or not verify_password(request.password, user.password):
        raise InvalidCredentialsError(request.email)

    return LoginResponse(
        accessToken=create_access_token(user.id),
        userId=user.id,
        nickname=user.nickname,
        isOnboarded=bool(user.is_onboarded),
    )
