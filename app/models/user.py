from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255), nullable=False)
    nickname = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    # 온보딩(콜드 스타트) 완료 여부. 최초 1회만 수행하며 재실행은 409로 막는다.
    is_onboarded = Column(Boolean, nullable=False, server_default="0")
