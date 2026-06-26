"""pgvector: расширение + таблица эмбеддингов услуг (только Postgres)

Revision ID: b2f1a9c4d7e8
Revises: 3a507c7fa04a
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2f1a9c4d7e8"
down_revision: Union[str, None] = "3a507c7fa04a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # семантика на SQLite работает in-process, таблица не нужна
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "CREATE TABLE IF NOT EXISTS service_embeddings ("
        " service_id uuid PRIMARY KEY REFERENCES service_catalog(id) ON DELETE CASCADE,"
        " embedding vector(384)"
        ")"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS service_embeddings")
