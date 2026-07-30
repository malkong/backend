from pydantic import BaseModel, EmailStr, Field

# bcrypt는 72바이트를 넘는 입력을 조용히 잘라내므로 스키마 단계에서 막는다.
_PASSWORD_MAX = 72


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=_PASSWORD_MAX)
    nickname: str = Field(min_length=1, max_length=100)


class SignupResponse(BaseModel):
    userId: int
    email: EmailStr
    nickname: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)


class LoginResponse(BaseModel):
    accessToken: str
    userId: int
    nickname: str
    # false면 프론트가 온보딩 화면으로 보낸다.
    isOnboarded: bool
