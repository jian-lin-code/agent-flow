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
    # 1. 加列：tsvector 没有现成的 sa.Column 通用类型，直接用 SQL 最稳
    op.execute("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS fts tsvector")

    # 2. GIN 索引：全文检索 WHERE fts @@ query 必须有它，否则全表扫
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_fts ON document_chunks USING gin (fts)")

    # 3. 存量回填：zhparser 扩展在 PG 侧，纯 SQL 就能算，不需要 Python 参与
    op.execute("UPDATE document_chunks SET fts = to_tsvector('chinese', content)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts")

