"""add fts trigger

Revision ID: 2ede5bca772e
Revises: abe3d8909488
Create Date: 2026-11-19 17:48:44.505333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ede5bca772e'
down_revision: Union[str, Sequence[str], None] = 'abe3d8909488'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS trg_update_fts ON document_chunks;
    CREATE TRIGGER trg_update_fts 
    BEFORE INSERT OR UPDATE OF content ON document_chunks
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(fts, 'chinese', content);
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_update_fts ON document_chunks")
