"""document_chunks 加 fts 列支持中文全文检索

Revision ID: abe3d8909488
Revises: 7a91c3f52d04
Create Date: 2026-11-19 16:21:04.572798

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abe3d8909488'
down_revision: Union[str, Sequence[str], None] = '7a91c3f52d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. 预先加载并配置中文分词器（防止手动漏配）
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
        CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
        ALTER TEXT SEARCH CONFIGURATION chinese
          ADD MAPPING FOR n, v, a, i, e, l WITH simple;
      END IF;
    END $$;
    """)

    # 1. 加列：tsvector 没有现成的 sa.Column 通用类型，直接用 SQL 最稳
    op.execute("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS fts tsvector")

    # 2. GIN 索引：全文检索 WHERE fts @@ query 必须有它，否则全表扫
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_fts ON document_chunks USING gin (fts)")

    # 3. 存量回填：注意这里加上了 public. 前缀，防止 schema 找不到配置报错
    op.execute("UPDATE document_chunks SET fts = to_tsvector('public.chinese', content)")

    # 4. 创建触发器：以后新增或修改 content，自动更新 fts
    op.execute("""
    DROP TRIGGER IF EXISTS trg_update_fts ON document_chunks;
    CREATE TRIGGER trg_update_fts 
    BEFORE INSERT OR UPDATE OF content ON document_chunks
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(fts, 'public.chinese', content);
    """)


def downgrade() -> None:
    # 回滚：先删触发器，再删索引和列
    op.execute("DROP TRIGGER IF EXISTS trg_update_fts ON document_chunks")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts")

    # 注意：我们通常不建议在 downgrade 里删除扩展（DROP EXTENSION），
    # 因为可能有其他表/字段还在依赖它，所以这里保留扩展不删。