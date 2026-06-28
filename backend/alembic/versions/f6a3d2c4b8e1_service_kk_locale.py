"""service_catalog: name_kk / description_kk — казахская локализация витрины

Revision ID: f6a3d2c4b8e1
Revises: e5b2c6a9f1d3
Create Date: 2026-06-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a3d2c4b8e1"
down_revision: Union[str, None] = "e5b2c6a9f1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("service_catalog")}
    if "name_kk" not in cols:
        op.add_column("service_catalog", sa.Column("name_kk", sa.Text(), nullable=False, server_default=""))
    if "description_kk" not in cols:
        op.add_column("service_catalog", sa.Column("description_kk", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("service_catalog", "description_kk")
    op.drop_column("service_catalog", "name_kk")
