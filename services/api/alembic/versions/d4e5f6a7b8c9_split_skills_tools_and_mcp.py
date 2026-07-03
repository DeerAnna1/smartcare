"""split skills, tools and mcp server configuration

Revision ID: d4e5f6a7b8c9
Revises: a3f2d1e8c047
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "a3f2d1e8c047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("skill_packages", sa.Column("instructions", sa.Text(), nullable=False, server_default=""))
    op.add_column("skill_packages", sa.Column("source_scope", sa.String(32), nullable=False, server_default="custom"))
    op.add_column("skill_packages", sa.Column("package_path", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("server_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("transport", sa.String(32), nullable=False, server_default="http"),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("command", sa.Text(), nullable=False, server_default=""),
        sa.Column("args_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("env_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("headers_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("oauth_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("server_key", name="uq_mcp_servers_server_key"),
    )
    op.create_index("ix_mcp_servers_server_key", "mcp_servers", ["server_key"])

    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_key", sa.String(256), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=False, server_default="builtin"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_schema_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("annotations_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provider_type", sa.String(32), nullable=False, server_default="builtin"),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("mcp_servers.id"), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tool_key", name="uq_tool_definitions_tool_key"),
    )
    op.create_index("ix_tool_definitions_tool_key", "tool_definitions", ["tool_key"])
    op.create_index("ix_tool_definitions_name", "tool_definitions", ["name"])
    op.create_index("ix_tool_definitions_provider_id", "tool_definitions", ["provider_id"])

    op.create_table(
        "skill_tool_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skill_packages.id"), nullable=False),
        sa.Column("tool_id", sa.String(36), sa.ForeignKey("tool_definitions.id"), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permission", sa.String(32), nullable=False, server_default="allow"),
        sa.UniqueConstraint("skill_id", "tool_id", name="uq_skill_tool_binding"),
    )
    op.create_index("ix_skill_tool_bindings_skill_id", "skill_tool_bindings", ["skill_id"])
    op.create_index("ix_skill_tool_bindings_tool_id", "skill_tool_bindings", ["tool_id"])

    op.create_table(
        "agent_skill_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skill_packages.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("agent_name", "skill_id", name="uq_agent_skill_policy"),
    )
    op.create_index("ix_agent_skill_policies_agent_name", "agent_skill_policies", ["agent_name"])
    op.create_index("ix_agent_skill_policies_skill_id", "agent_skill_policies", ["skill_id"])


def downgrade() -> None:
    op.drop_table("agent_skill_policies")
    op.drop_table("skill_tool_bindings")
    op.drop_table("tool_definitions")
    op.drop_table("mcp_servers")
    op.drop_column("skill_packages", "package_path")
    op.drop_column("skill_packages", "source_scope")
    op.drop_column("skill_packages", "instructions")
