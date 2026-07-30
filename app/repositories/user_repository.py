from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """이메일로 유저 조회. 없으면 None."""
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """PK로 유저 조회. 없으면 None."""
    return db.get(User, user_id)


def create_user(db: Session, email: str, hashed_password: str, nickname: str) -> User:
    user = User(email=email, password=hashed_password, nickname=nickname)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
