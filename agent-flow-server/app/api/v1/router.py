# 汇总挂载所有 v1 路由
from fastapi import APIRouter
from app.api.v1 import knowledge
from app.api.v1 import auth, conversations
from app.api.v1 import expense_claims, expense_pre_review
from app.api.v1 import admin

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(conversations.router)
router.include_router(knowledge.router)
router.include_router(expense_claims.router)
router.include_router(expense_pre_review.router)
router.include_router(admin.router)


