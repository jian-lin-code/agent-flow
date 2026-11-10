-- 仅首次初始化数据目录时执行；pgvector 镜像已内置该扩展
CREATE EXTENSION IF NOT EXISTS vector;
