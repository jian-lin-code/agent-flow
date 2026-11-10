from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).parents[2] / ".env"

class Settings(BaseSettings):
    # 数据库连接（改成你的真实密码）
    DATABASE_URL: str

    # JWT 配置
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时

    # 本地启动配置
    APP_HOST: str
    APP_PORT: int

    # minio配置
    MINIO_ENDPOINT:str
    MINIO_ACCESS_KEY:str
    MINIO_SECRET_KEY:str
    MINIO_BUCKET_NAME:str
    MINIO_IMG_DIR:str
    MINIO_SECURE: bool = False
    MINIO_EXPENSE_BUCKET_NAME:str

    # LLM
    OPENAI_API_KEY:str
    OPENAI_API_BASE:str
    LLM_DEFAULT_MODEL:str
    LLM_DEFAULT_TEMPERATURE:float
    VL_PLUS_MODEL:str
    LLM_MAX_TOKENS:int
    EMBEDDING_MODEL_NAME:str
    EMBEDDING_DIMENSION:int
    LLM_MAX_RETRIES:int
    # 意图识别
    LLM_INTENT_MODEL:str
    LLM_EXTRACT_MODEL:str
    # 重排序
    RERANK_API_BASE:str
    RERANK_MODEL_NAME:str

    # 是否启用「意图识别 + 费用抽取」合并调用。
    # 关闭后回退为两次独立调用（意图识别一次、补充信息抽取一次）。
    EXPENSE_MERGED_EXTRACTION: bool = True
    # 合并抽取结果的置信度下限，低于该值不信任抽取结果，回退到独立抽取。
    EXPENSE_MERGED_CONFIDENCE: float = 0.7

    # minerU
    MINERU_BASE_URL:str
    MINERU_API_TOKEN:str
    MINERU_OUTPUT_DIR:str

    # 图片摘要（多模态）并发与限流
    # 并发数：同时向多模态模型发起的图片摘要请求上限
    IMAGE_SUMMARY_CONCURRENCY: int = 4
    # 每分钟请求上限：按所选模型的 RPM 配额调整，过小会成为长文档的瓶颈
    IMAGE_SUMMARY_RPM: int = 60
    # 图片摘要缓存时间（秒），key 为图片内容 md5，重新处理/重复上传可直接复用
    IMAGE_SUMMARY_CACHE_TTL: int = 60 * 60 * 24 * 7

    # 文件缓存目录
    LOCAL_CACHE_DIR:str

    # ARQ配置
    REDIS_HOST:str
    REDIS_PORT:int
    REDIS_DB:int

    # Jev配置
    JEV_API_BASE:str
    JEV_API_KEY:str
    JEV_OPENROUTER_BASE:str
    JEV_OPENROUTER_KEY:str
    JEV_MODEL:str
    JEV_PROVIDER:str



    # 加载 .env 文件
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略.env里面没有定义在类里的多余变量，防止报错
    )

# lru_cache 单例，全局只加载一次.env，避免重复读取
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# 全局配置实例，项目其他地方直接 import 使用
settings = get_settings()
