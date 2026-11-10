# 登录校验、签发 token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import verify_password, create_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, UserOut, LoginResponse
from fastapi import HTTPException


async def authenticate_user(username: str, password: str, session: AsyncSession) -> User:
    result = await session.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    return user


async def login(data: LoginRequest, session: AsyncSession) -> LoginResponse:
    user = await authenticate_user(data.username, data.password, session)
    # Token 中存放用户对外唯一标识 uid，不暴露自增 id
    token = create_access_token(user.uid)
    return LoginResponse(
        access_token=token,
        user=UserOut.model_validate(user)
    )
