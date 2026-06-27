"""service_catalog.description — краткое пояснение услуги для витрины

Revision ID: d4a1b2c3e5f6
Revises: c3d8e1f20a4b
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a1b2c3e5f6"
down_revision: Union[str, None] = "c3d8e1f20a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("service_catalog")}
    if "description" not in cols:
        op.add_column(
            "service_catalog",
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    op.drop_column("service_catalog", "description")
