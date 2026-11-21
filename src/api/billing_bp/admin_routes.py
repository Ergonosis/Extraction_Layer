"""Ergonosis Admin Billing routes (platform admin only)."""

from __future__ import annotations

from flask import jsonify, request, session

from src.api.billing_bp import admin_bp
from src.api.rate_limit import auth_me_limit
from src.billing import services
from src.billing.decorators import platform_admin_required


@admin_bp.get('/orgs')
@auth_me_limit
@platform_admin_required
def list_orgs():
    return jsonify({'organizations': services.admin_list_orgs()})


@admin_bp.get('/orgs/<int:organization_id>')
@auth_me_limit
@platform_admin_required
def get_org(organization_id: int):
    try:
        data = services.admin_get_org(organization_id)
    except LookupError:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(data)


@admin_bp.post('/orgs/<int:organization_id>')
@auth_me_limit
@platform_admin_required
def upsert_org(organization_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        data = services.admin_upsert_org_plan(organization_id, actor_user_id=session.get('user_id'), payload=payload)
    except LookupError:
        return jsonify({'error': 'Not found'}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({'error': 'Bad request', 'detail': str(exc)}), 400
    return jsonify(data)


@admin_bp.post('/orgs/<int:organization_id>/resume')
@auth_me_limit
@platform_admin_required
def resume_org(organization_id: int):
    try:
        data = services.admin_resume(organization_id, actor_user_id=session.get('user_id'))
    except LookupError:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(data)


@admin_bp.post('/orgs/<int:organization_id>/refund')
@auth_me_limit
@platform_admin_required
def refund_org(organization_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        data = services.admin_refund(
            organization_id, actor_user_id=session.get('user_id'), invoice_id=payload.get('invoice_id')
        )
    except LookupError:
        return jsonify({'error': 'Not found'}), 404
    except ValueError as exc:
        return jsonify({'error': 'Bad request', 'detail': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': 'Refund failed', 'detail': str(exc)}), 502
    return jsonify(data)


@admin_bp.get('/orgs/<int:organization_id>/disputes')
@auth_me_limit
@platform_admin_required
def disputes_org(organization_id: int):
    try:
        data = services.admin_disputes(organization_id)
    except LookupError:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(data)
