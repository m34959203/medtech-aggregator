"""prices.is_anomaly — детерминированный флаг ценовой аномалии (nonresident<resident)

Revision ID: e5b2c6a9f1d3
Revises: d4a1b2c3e5f6
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b2c6a9f1d3"
down_revision: Union[str, None] = "d4a1b2c3e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("prices")}
    if "is_anomaly" not in cols:
        op.add_column(
            "prices",
            sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("prices", "is_anomaly")
