import asyncio
import asyncpg


async def fix_db():
    # 你的连接串
    conn = await asyncpg.connect('postgresql://postgres:123456@172.19.46.73:5432/agent_flow')

    print("开始给 agent_flow 库打补丁...")

    # 1. 安装扩展
    await conn.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")

    # 2. 创建中文配置和词性映射 (如果不存在的话)
    sql_do = """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
        CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
        ALTER TEXT SEARCH CONFIGURATION chinese
          ADD MAPPING FOR n, v, a, i, e, l WITH simple;
      END IF;
    END $$;
    """
    await conn.execute(sql_do)

    print("补丁打完了！")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_db())