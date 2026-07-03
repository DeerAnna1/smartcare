"""harden consultation runs

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consultation_sessions", sa.Column("clinical_memory", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("consultation_sessions", sa.Column("active_run_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_conversation_request", "conversation_messages", ["session_id", "client_request_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_conversation_request", "conversation_messages", type_="unique")
    op.drop_column("consultation_sessions", "active_run_heartbeat_at")
    op.drop_column("consultation_sessions", "clinical_memory")
