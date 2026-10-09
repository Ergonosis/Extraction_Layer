"""initial portal schema

Revision ID: 001_portal_schema
Revises:
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa

revision = "001_portal_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ms_tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ms_tenant_id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("ms_oid", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ms_oid", name="uq_users_org_ms_oid"),
    )
    op.create_index(
        op.f("ix_users_organization_id"),
        "users",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("connected_account", sa.String(length=255), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('plaid', 'msgraph')", name="ck_integrations_provider"),
        sa.CheckConstraint(
            "status IN ('not_connected', 'connecting', 'connected', 'reauth_required', 'error')",
            name="ck_integrations_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_integrations_user_provider"),
    )
    op.create_index(
        op.f("ix_integrations_organization_id"),
        "integrations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integrations_user_id"),
        "integrations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "plaid_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id"),
    )

    op.create_table(
        "ms_graph_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes_granted", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id"),
    )

    op.create_table(
        "ms_graph_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ms_graph_permissions_integration_id"),
        "ms_graph_permissions",
        ["integration_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_ms_graph_permissions_integration_id"), table_name="ms_graph_permissions")
    op.drop_table("ms_graph_permissions")
    op.drop_table("ms_graph_credentials")
    op.drop_table("plaid_credentials")
    op.drop_index(op.f("ix_integrations_user_id"), table_name="integrations")
    op.drop_index(op.f("ix_integrations_organization_id"), table_name="integrations")
    op.drop_table("integrations")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
