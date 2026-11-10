from contextlib import asynccontextmanager
import uvicorn
from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.core.config import settings
from app.core.database import init_db_engine, close_db_engine
from app.core.handlers import register_exception_handlers
from app.utils.logger import logger
from app.utils.minio_client import get_minio_storage


#fastAPI应用的生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：
        - 启动时：执行 yield 前的代码（初始化数据库引擎）
        - 运行中：yield 让出控制权，FastAPI 处理请求
        - 关闭时：执行 yield 后的代码（关闭数据库引擎）

    注意：
        - app 参数必须指定，类型为 FastAPI
        - 可通过 app.state 存储全局共享资源（当前未使用）
    """
    # 1. 应用启动
    print("启动服务器...")

    init_db_engine()
    logger.info("✅ 启动：初始化数据库链接资源")

    app.state.arq_redis = await create_pool(
        RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT, database=settings.REDIS_DB)
    )
    logger.info("✅ 启动：创建arq redis池")

    # 初始化 MinIO
    minio_client = get_minio_storage()
    await minio_client.init()
    logger.info("✅ 启动：MinIO 存储桶初始化完成")

    # 2. 进入 yield
    yield  # ← FastAPI 开始接收请求
    #    用户访问 API...

    # 3. 应用关闭（Ctrl+C 或部署平台停止）
    await close_db_engine()  # ← 执行这里，关闭连接池
    await app.state.arq_redis.close() #关闭：释放arq redis连接池
    print("服务器已关闭")
app = FastAPI(title="AgentFlow", version="0.1.0",lifespan=lifespan)
register_exception_handlers(app)  # 注册全局统一异常处理器
app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"msg": "AgentFlow API"}

if __name__ == '__main__':
        uvicorn.run(
            app=app,
            host=settings.APP_HOST,
            port=settings.APP_PORT
        )