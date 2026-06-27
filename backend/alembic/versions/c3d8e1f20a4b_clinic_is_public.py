"""clinics.is_public — флаг публичности (скрыть обезличенные архив-клиники Кейса 2)

Revision ID: c3d8e1f20a4b
Revises: b2f1a9c4d7e8
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d8e1f20a4b"
down_revision: Union[str, None] = "b2f1a9c4d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # идемпотентно: колонка могла быть добавлена hot-fix'ом руками на проде
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("clinics")}
    if "is_public" not in cols:
        op.add_column(
            "clinics",
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    # обезличенные архив-клиники Кейса 2 («Клиника N») — скрыть из публичной выдачи.
    # Прод = Postgres (regex `~`); на SQLite (dev/тесты) таких клиник нет, пропускаем.
    if bind.dialect.name == "postgresql":
        op.execute(r"UPDATE clinics SET is_public=false WHERE name ~ '^Клиника [0-9]+$'")


def downgrade() -> None:
    op.drop_column("clinics", "is_public")
