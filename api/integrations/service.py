"""Integrations dashboard business logic (no Flask HTTP)."""

from __future__ import annotations

from api.extensions import db
from api.integrations.constants import (
    MS_GRAPH_SCOPE_LABELS,
    PROVIDER_LABELS,
    SUPPORTED_PROVIDERS,
)
from api.models import Integration
from api.tenancy import require_matching_org


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _msgraph_permissions_payload(integration: Integration) -> list[dict]:
    """Merge catalog scopes with stored permission rows (never tokens)."""
    by_scope = {p.scope: p for p in (integration.ms_graph_permissions or [])}
    payload = []
    for scope, label in MS_GRAPH_SCOPE_LABELS.items():
        row = by_scope.get(scope)
        payload.append(
            {
                "scope": scope,
                "label": label,
                "is_active": bool(row.is_active) if row else False,
            }
        )
    return payload


def ensure_provider_rows(*, user_id: int, organization_id: int) -> list[Integration]:
    """Ensure plaid + msgraph rows exist for this user/org; return both ordered."""
    require_matching_org(user_id=user_id, organization_id=organization_id)
    existing = {
        row.provider: row
        for row in Integration.query.filter_by(
            user_id=user_id,
            organization_id=organization_id,
        ).all()
    }

    created = False
    for provider in SUPPORTED_PROVIDERS:
        if provider not in existing:
            row = Integration(
                user_id=user_id,
                organization_id=organization_id,
                provider=provider,
                status="not_connected",
            )
            db.session.add(row)
            existing[provider] = row
            created = True

    if created:
        db.session.commit()
        # Refresh so relationship collections are available
        for provider in SUPPORTED_PROVIDERS:
            db.session.refresh(existing[provider])

    return [existing[provider] for provider in SUPPORTED_PROVIDERS]


def serialize_integration(row: Integration) -> dict:
    permissions: list[dict] = []
    if row.provider == "msgraph":
        permissions = _msgraph_permissions_payload(row)

    return {
        "provider": row.provider,
        "label": PROVIDER_LABELS.get(row.provider, row.provider),
        "status": row.status,
        "connected_account": row.connected_account,
        "connected_at": _iso(row.connected_at),
        "updated_at": _iso(row.updated_at),
        "permissions": permissions,
    }


def list_integrations(*, user_id: int, organization_id: int) -> list[dict]:
    """Return safe status payloads for both providers (org-scoped)."""
    rows = ensure_provider_rows(user_id=user_id, organization_id=organization_id)
    return [serialize_integration(row) for row in rows]
