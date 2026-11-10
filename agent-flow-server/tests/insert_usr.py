import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.security import hash_password
from app.models import user

# 1. 定义插入逻辑（接收真正的 session）
async def create_user(session: AsyncSession):
    password_hash = hash_password("123456")

    # 实例化
    new_user = user.User(
        username="123456",
        password_hash=password_hash,
        nickname="小羊羊",
    )

    # 添加到 session
    session.add(new_user)

    # 提交事务
    await session.commit()

    # 刷新对象，获取数据库生成的自增 ID 和时间
    await session.refresh(new_user)

    print(new_user)
    return new_user


# 2. 定义主测试入口
async def main():
    # ⚠️ 你的 database 引擎需要先初始化
    database.init_db_engine()

    # 获取真正的 session 实例
    assert database.async_session is not None
    async with database.async_session() as session:
        # 把真正的 session 传进去
        await create_user(session)


# 3. 运行
if __name__ == '__main__':
    asyncio.run(main())








