"""Plaid connect / exchange / disconnect / status / export business logic."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from flask import current_app
from plaid.exceptions import ApiException
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from api.audit import audit
from api.crypto import decrypt_token, encrypt_token
from api.extensions import db
from api.integrations.service import ensure_provider_rows, serialize_integration
from api.models import Integration, PlaidCredential
from api.plaid_bp.client import get_plaid_client
from api.plaid_bp.extractor import load_fetch_and_store

logger = logging.getLogger(__name__)

# Plaid error codes that mean the user must re-authenticate via Link.
_REAUTH_ERROR_CODES = frozenset(
    {
        "ITEM_LOGIN_REQUIRED",
        "PENDING_EXPIRATION",
        "ITEM_LOCKED",
        "USER_PERMISSION_REVOKED",
    }
)


class PlaidServiceError(Exception):
    """Domain error with HTTP-friendly message + status."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _plaid_integration(*, user_id: int, organization_id: int) -> Integration:
    rows = ensure_provider_rows(user_id=user_id, organization_id=organization_id)
    for row in rows:
        if row.provider == "plaid":
            return row
    raise PlaidServiceError("Plaid integration row missing", status_code=500)


def _validate_public_token(public_token: object) -> str:
    if not isinstance(public_token, str):
        raise PlaidServiceError("public_token is required")
    token = public_token.strip()
    if not token:
        raise PlaidServiceError("public_token is required")
    if len(token) > 512 or not token.startswith("public-"):
        raise PlaidServiceError("invalid public_token")
    return token


def _plaid_error_code(exc: ApiException) -> str | None:
    try:
        body = json.loads(exc.body) if isinstance(exc.body, str) else (exc.body or {})
        code = body.get("error_code")
        return str(code) if code else None
    except Exception:
        return None


def _institution_name(client, access_token: str) -> str | None:
    """Resolve institution display name; never fail the exchange on metadata errors."""
    try:
        item = client.item_get(ItemGetRequest(access_token=access_token)).to_dict()
        inst_id = (item.get("item") or {}).get("institution_id")
        if not inst_id:
            return None
        inst = client.institutions_get_by_id(
            InstitutionsGetByIdRequest(
                institution_id=inst_id,
                country_codes=[CountryCode("US")],
            )
        ).to_dict()
        return (inst.get("institution") or {}).get("name")
    except Exception:
        logger.exception("Failed to resolve Plaid institution name")
        return None


def create_link_token(*, user_id: int, organization_id: int) -> dict:
    """Create a Plaid Link token and mark the integration as connecting."""
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)
    client = get_plaid_client()

    req = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Ergonosis Portal",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
    )

    try:
        resp = client.link_token_create(req).to_dict()
    except ApiException as exc:
        code = _plaid_error_code(exc)
        logger.exception("Plaid link_token_create failed (%s)", code)
        raise PlaidServiceError(
            "Could not create Plaid Link token",
            status_code=502,
        ) from exc
    except RuntimeError as exc:
        raise PlaidServiceError(str(exc), status_code=503) from exc

    link_token = resp.get("link_token")
    if not link_token:
        raise PlaidServiceError("Plaid did not return a link_token", status_code=502)

    integration.status = "connecting"
    integration.updated_at = _utcnow()
    db.session.commit()
    audit(
        "plaid.connect.start",
        user_id=user_id,
        organization_id=organization_id,
    )

    return {
        "link_token": link_token,
        "expiration": resp.get("expiration"),
        "integration": serialize_integration(integration),
    }


def exchange_public_token(
    *,
    user_id: int,
    organization_id: int,
    public_token: object,
) -> dict:
    """Exchange public_token → access_token; store only Fernet ciphertext."""
    token = _validate_public_token(public_token)
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)

    try:
        client = get_plaid_client()
    except RuntimeError as exc:
        raise PlaidServiceError(str(exc), status_code=503) from exc

    try:
        exchange_resp = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=token)
        )
        access_token = exchange_resp["access_token"]
        item_id = exchange_resp["item_id"]
    except ApiException as exc:
        code = _plaid_error_code(exc)
        logger.exception("Plaid public_token exchange failed (%s)", code)
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        raise PlaidServiceError(
            "Could not exchange Plaid public_token",
            status_code=502,
        ) from exc

    # Encrypt immediately — plaintext must never be written to the DB.
    access_token_enc = encrypt_token(access_token)
    institution_name = _institution_name(client, access_token)

    cred = integration.plaid_credential
    if cred is None:
        cred = PlaidCredential(integration_id=integration.id)
        db.session.add(cred)

    cred.access_token_enc = access_token_enc
    cred.item_id = item_id
    cred.institution_name = institution_name

    integration.status = "connected"
    integration.connected_account = institution_name or item_id
    integration.connected_at = _utcnow()
    integration.updated_at = _utcnow()
    db.session.commit()
    audit(
        "plaid.connect.success",
        user_id=user_id,
        organization_id=organization_id,
        item_id=item_id,
    )

    return {"integration": serialize_integration(integration)}


def disconnect(*, user_id: int, organization_id: int) -> dict:
    """Revoke at Plaid (best-effort), delete local credentials, set not_connected."""
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)
    cred = integration.plaid_credential

    if cred is not None:
        try:
            client = get_plaid_client()
            access_token = decrypt_token(cred.access_token_enc)
            try:
                client.item_remove(ItemRemoveRequest(access_token=access_token))
            except ApiException as exc:
                # Item may already be gone — still clear local state.
                logger.warning(
                    "Plaid item_remove failed (%s); clearing local credentials",
                    _plaid_error_code(exc),
                )
        except RuntimeError:
            logger.warning("Plaid not configured during disconnect; clearing local only")
        except Exception:
            logger.exception("Unexpected error during Plaid disconnect revoke")

        db.session.delete(cred)

    integration.status = "not_connected"
    integration.connected_account = None
    integration.connected_at = None
    integration.updated_at = _utcnow()
    db.session.commit()
    audit(
        "plaid.disconnect",
        user_id=user_id,
        organization_id=organization_id,
    )

    return {"integration": serialize_integration(integration)}


def cancel_connect(*, user_id: int, organization_id: int) -> dict:
    """Abandon an in-progress Link flow.

    Only clears `connecting` when no credential exists — never wipes a
    completed connection.
    """
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)

    if integration.plaid_credential is not None:
        return {"integration": serialize_integration(integration)}

    if integration.status == "connecting":
        integration.status = "not_connected"
        integration.connected_account = None
        integration.connected_at = None
        integration.updated_at = _utcnow()
        db.session.commit()

    return {"integration": serialize_integration(integration)}


def check_status(*, user_id: int, organization_id: int) -> dict:
    """Call Plaid item_get; surface reauth_required without returning tokens."""
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)
    cred = integration.plaid_credential

    if cred is None:
        if integration.status not in ("not_connected", "connecting", "error"):
            integration.status = "not_connected"
            integration.connected_account = None
            integration.connected_at = None
            integration.updated_at = _utcnow()
            db.session.commit()
        return {"integration": serialize_integration(integration)}

    try:
        client = get_plaid_client()
        access_token = decrypt_token(cred.access_token_enc)
        client.item_get(ItemGetRequest(access_token=access_token))
    except RuntimeError as exc:
        raise PlaidServiceError(str(exc), status_code=503) from exc
    except ApiException as exc:
        code = _plaid_error_code(exc)
        if code in _REAUTH_ERROR_CODES:
            integration.status = "reauth_required"
            integration.updated_at = _utcnow()
            db.session.commit()
            return {"integration": serialize_integration(integration)}
        logger.exception("Plaid item_get failed (%s)", code)
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        return {"integration": serialize_integration(integration)}
    except Exception:
        logger.exception("Unexpected error during Plaid status check")
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        return {"integration": serialize_integration(integration)}

    # Healthy item — ensure status reflects connected.
    if integration.status != "connected":
        integration.status = "connected"
        if not integration.connected_account:
            integration.connected_account = cred.institution_name or cred.item_id
        integration.updated_at = _utcnow()
        db.session.commit()

    return {"integration": serialize_integration(integration)}


def _parse_optional_date(value: object, field: str) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise PlaidServiceError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise PlaidServiceError(
            f"{field} must be an ISO date string (YYYY-MM-DD)"
        ) from exc


def run_export(
    *,
    user_id: int,
    organization_id: int,
    start_date: object = None,
    end_date: object = None,
    window_days: object = None,
    account_filter: object = None,
) -> dict:
    """Decrypt Plaid token in-memory and call legacy ``fetch_and_store``.

    Never returns or logs the access token.
    """
    integration = _plaid_integration(user_id=user_id, organization_id=organization_id)
    cred = integration.plaid_credential
    if cred is None or integration.status not in ("connected", "reauth_required"):
        raise PlaidServiceError(
            "Connect Plaid before exporting transactions",
            status_code=400,
        )

    parsed_start = _parse_optional_date(start_date, "start_date")
    parsed_end = _parse_optional_date(end_date, "end_date")

    parsed_window: int | None = None
    if window_days is not None and window_days != "":
        try:
            parsed_window = int(window_days)
        except (TypeError, ValueError) as exc:
            raise PlaidServiceError("window_days must be an integer") from exc
        if parsed_window <= 0:
            raise PlaidServiceError("window_days must be greater than 0")

    output_dir = current_app.config.get("PLAID_RECORDS_DIR") or "records"

    try:
        client = get_plaid_client()
        access_token = decrypt_token(cred.access_token_enc)
        fetch_and_store = load_fetch_and_store()
        file_path = fetch_and_store(
            client,
            access_token,
            item_id=cred.item_id,
            start_date=parsed_start,
            end_date=parsed_end,
            window_days=parsed_window,
            account_filter=account_filter,
            output_dir=output_dir,
        )
    except RuntimeError as exc:
        raise PlaidServiceError(str(exc), status_code=503) from exc
    except ValueError as exc:
        raise PlaidServiceError(str(exc), status_code=400) from exc
    except ApiException as exc:
        code = _plaid_error_code(exc)
        if code in _REAUTH_ERROR_CODES:
            integration.status = "reauth_required"
            integration.updated_at = _utcnow()
            db.session.commit()
            raise PlaidServiceError(
                "Plaid re-authentication required",
                status_code=401,
            ) from exc
        logger.exception("Plaid export failed (%s)", code)
        raise PlaidServiceError("Plaid export failed", status_code=502) from exc
    except Exception as exc:
        logger.exception("Unexpected error during Plaid export")
        raise PlaidServiceError("Plaid export failed", status_code=502) from exc

    audit(
        "plaid.export",
        user_id=user_id,
        organization_id=organization_id,
        item_id=cred.item_id,
    )
    return {
        "file": file_path,
        "item_id": cred.item_id,
        "integration": serialize_integration(integration),
    }
