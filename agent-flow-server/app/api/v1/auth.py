# 登录
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, UserOut
from app.services.auth_service import login
from app.core.response import UnifiedResponseRoute

# 显式使用统一返回格式的自定义路由类
router = APIRouter(prefix="/auth", tags=["auth"], route_class=UnifiedResponseRoute)

@router.post("/login")
async def login_api(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    # 如果你后端的 login 服务函数接收的是 Pydantic 模型，
    data = LoginRequest(username=form_data.username, password=form_data.password)
    return await login(data, session)

@router.get("/me", response_model=UserOut)
async def me_api(current_user: Annotated[User, Depends(get_current_user)]):
    """当前登录用户信息（供前端刷新本地缓存的昵称 / 角色等）。"""
    return UserOut.model_validate(current_user)
