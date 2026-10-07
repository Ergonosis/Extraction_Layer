"""SQLAlchemy models for the portal (multi-organization schema)."""

from datetime import datetime, timezone

from api.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    ms_tenant_id = db.Column(db.String(36), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    users = db.relationship("User", back_populates="organization")
    integrations = db.relationship("Integration", back_populates="organization")


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "ms_oid", name="uq_users_org_ms_oid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    email = db.Column(db.String(320), nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    ms_oid = db.Column(db.String(36), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    last_login = db.Column(db.DateTime(timezone=True), nullable=True)

    organization = db.relationship("Organization", back_populates="users")
    integrations = db.relationship("Integration", back_populates="user")


class Integration(db.Model):
    __tablename__ = "integrations"
    __table_args__ = (
        db.UniqueConstraint("user_id", "provider", name="uq_integrations_user_provider"),
        db.CheckConstraint("provider IN ('plaid', 'msgraph')", name="ck_integrations_provider"),
        db.CheckConstraint(
            "status IN ('not_connected', 'connecting', 'connected', 'reauth_required', 'error')",
            name="ck_integrations_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="not_connected")
    connected_account = db.Column(db.String(255), nullable=True)
    connected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    organization = db.relationship("Organization", back_populates="integrations")
    user = db.relationship("User", back_populates="integrations")
    plaid_credential = db.relationship(
        "PlaidCredential",
        back_populates="integration",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ms_graph_credential = db.relationship(
        "MsGraphCredential",
        back_populates="integration",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ms_graph_permissions = db.relationship(
        "MsGraphPermission",
        back_populates="integration",
        cascade="all, delete-orphan",
    )


class PlaidCredential(db.Model):
    __tablename__ = "plaid_credentials"

    id = db.Column(db.Integer, primary_key=True)
    integration_id = db.Column(
        db.Integer,
        db.ForeignKey("integrations.id"),
        nullable=False,
        unique=True,
    )
    access_token_enc = db.Column(db.LargeBinary, nullable=False)
    item_id = db.Column(db.String(255), nullable=False)
    institution_name = db.Column(db.String(255), nullable=True)

    integration = db.relationship("Integration", back_populates="plaid_credential")


class MsGraphCredential(db.Model):
    __tablename__ = "ms_graph_credentials"

    id = db.Column(db.Integer, primary_key=True)
    integration_id = db.Column(
        db.Integer,
        db.ForeignKey("integrations.id"),
        nullable=False,
        unique=True,
    )
    access_token_enc = db.Column(db.LargeBinary, nullable=False)
    refresh_token_enc = db.Column(db.LargeBinary, nullable=False)
    token_expiry = db.Column(db.DateTime(timezone=True), nullable=True)
    scopes_granted = db.Column(db.JSON, nullable=False, default=list)

    integration = db.relationship("Integration", back_populates="ms_graph_credential")


class MsGraphPermission(db.Model):
    __tablename__ = "ms_graph_permissions"

    id = db.Column(db.Integer, primary_key=True)
    integration_id = db.Column(
        db.Integer,
        db.ForeignKey("integrations.id"),
        nullable=False,
        index=True,
    )
    scope = db.Column(db.String(128), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    granted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    integration = db.relationship("Integration", back_populates="ms_graph_permissions")
