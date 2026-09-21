"""enable pgvector

Baseline migration. Creates only the pgvector extension, which every later
migration adding an embedding column depends on.

Revision ID: 0001
Revises:
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Unqualified on purpose: Supabase puts extensions in the `extensions`
    # schema, a local Postgres container puts them in `public`, and both are on
    # the default search_path. Pinning a schema would break one of them.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Not dropped. Other objects may depend on the type, and dropping an
    # extension that something else installed is worse than leaving it.
    pass
