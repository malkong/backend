from sqlalchemy import BigInteger, Column, DateTime, String, func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255), nullable=False)
    nickname = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
