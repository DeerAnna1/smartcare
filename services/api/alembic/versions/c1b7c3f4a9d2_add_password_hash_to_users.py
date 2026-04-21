"""add password hash to users

Revision ID: c1b7c3f4a9d2
Revises: 9a288366c564
Create Date: 2026-04-19 19:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c1b7c3f4a9d2"
down_revision = "9a288366c564"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
