"""add token usage to messages

Revision ID: 6f4f76ab8747
Revises: c3e113f96917
Create Date: 2026-10-30 19:45:18.697856

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f4f76ab8747'
down_revision: Union[str, Sequence[str], None] = 'c3e113f96917'


branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("input_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("total_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "total_tokens")
    op.drop_column("messages", "output_tokens")
    op.drop_column("messages", "input_tokens")