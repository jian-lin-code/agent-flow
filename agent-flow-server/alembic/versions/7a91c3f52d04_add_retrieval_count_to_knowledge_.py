"""knowledge_bases 表新增检索调用频次字段 retrieval_count

Revision ID: 7a91c3f52d04
Revises: 86fb34f9b05b
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a91c3f52d04'
down_revision: Union[str, Sequence[str], None] = '86fb34f9b05b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_bases',
        sa.Column(
            'retrieval_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='知识检索调用频次',
        ),
    )


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'retrieval_count')
