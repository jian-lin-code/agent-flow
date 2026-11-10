from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    uid: str
    username: str
    role: str
    nickname: str | None = None

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

