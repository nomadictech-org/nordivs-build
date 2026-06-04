# -*- coding: utf-8 -*-
"""Token generation and validation — the core of the security model.

validate_request() is called at the top of EVERY endpoint except /login.
It returns (employee, None) on success or (None, error_response) on failure.
No endpoint should ever query data without first calling this function.
"""
import logging
import secrets
from datetime import timedelta
from functools import wraps
from odoo import fields, SUPERUSER_ID
from odoo import fields
from odoo.http import request

from . import response_helper as R

_logger = logging.getLogger(__name__)

TOKEN_BYTES = 32  # secrets.token_hex(32) produces 64 hex characters


# -------------------------------------------------------------------------
# Token Generation - for employee authentication purpose only
# -------------------------------------------------------------------------

def generate_token(employee, device_info=None):
    """Create a new API token for an authenticated employee.

    Args:
        employee: An hr.employee recordset (single record).
        device_info: Optional device identification string from Flutter.

    Returns:
        dict with 'token' (str) and 'expires_at' (datetime) keys.
    """
    token_str = secrets.token_hex(TOKEN_BYTES)
    now = fields.Datetime.now()
    expires = now + timedelta(days=30)

    request.env(user=SUPERUSER_ID)['employee.api.token'].create({
        'employee_id': employee.id,
        'token': token_str,
        'device_info': device_info or '',
        'expires_at': expires,
        'is_active': True,
        'last_used_at': now,
        'created_at': now,
    })

    _logger.info(
        'Token generated for employee %s (id=%d, device=%s)',
        employee.name, employee.id, device_info or 'unknown',
    )

    return {
        'token': token_str,
        'expires_at': expires,
    }


# -------------------------------------------------------------------------
# Token Validation (The Gatekeeper)
# -------------------------------------------------------------------------

def validate_request():
    """Validate the incoming request's bearer token.

    This function MUST be called at the top of every data endpoint.
    It performs 5 sequential checks, failing fast at each gate.

    Returns:
        tuple: (employee_record, None) on success
               (None, error_Response) on failure

    The caller MUST check the second element:
        employee, err = validate_request()
        if err:
            return err
    """
    # Gate 1: Authorization header present
    auth_header = request.httprequest.headers.get('Authorization', '')
    if not auth_header:
        return None, R.error_401(
            R.ERR_MISSING_AUTH,
            'Missing authorization header.',
        )

    # Gate 2: Header format is "Bearer <token>"
    if not auth_header.startswith('Bearer '):
        return None, R.error_401(
            R.ERR_MISSING_AUTH,
            'Authorization header must use Bearer scheme.',
        )

    token_str = auth_header[7:].strip()
    if not token_str:
        return None, R.error_401(
            R.ERR_MISSING_AUTH,
            'Bearer token is empty.',
        )

    # Gate 3: Token exists, is active, and not expired
    # This query hits the composite index on (token, is_active)
    env = request.env(user=SUPERUSER_ID)
    token_record = env['employee.api.token'].search([
        ('token', '=', token_str),
        ('is_active', '=', True),
        ('expires_at', '>', fields.Datetime.now()),
    ], limit=1)

    if not token_record:
        return None, R.error_401(
            R.ERR_INVALID_TOKEN,
            'Your session has expired. Please log in again.',
        )

    # Gate 4: Linked employee is still active in the system
    employee = token_record.employee_id
    if not employee or not employee.active:
        token_record.revoke()
        return None, R.error_401(
            R.ERR_INVALID_TOKEN,
            'Your employee account is no longer active.',
        )

    # Gate 5: Employee's API access is still enabled by HR
    if not employee.api_enabled:
        return None, R.error_403(
            R.ERR_ACCESS_DISABLED,
            'Mobile app access has been disabled for your account. '
            'Please contact HR.',
        )

    # All gates passed — update last_used timestamp (lightweight SQL)
    token_record.touch()

    return employee, None


# -------------------------------------------------------------------------
# Decorator (Alternative to manual validate_request calls)
# -------------------------------------------------------------------------

def require_token(fn):
    """Decorator that validates the token before calling the endpoint.

    Usage:
        @http.route(...)
        @require_token
        def my_endpoint(self, employee, **kw):
            # employee is already validated
            ...

    The decorated function receives the validated employee record as its
    first positional argument (after self).
    """
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        employee, err = validate_request()
        if err:
            return err
        return fn(self, employee, *args, **kwargs)
    return wrapper


# -------------------------------------------------------------------------
# Audit Logging
# -------------------------------------------------------------------------

def log_auth_event(event_type, employee=None, badge_id=None, ip=None, detail=None):
    """Log an authentication event for audit trail.

    Args:
        event_type: One of 'login_success', 'login_failed', 'logout',
                    'token_expired', 'account_locked'.
        employee: hr.employee record (if identified).
        badge_id: The submitted badge ID (for failed attempts where
                  employee may not exist).
        ip: Client IP address.
        detail: Additional context string.
    """
    ip = ip or _get_client_ip()
    parts = [f'AUTH EVENT: {event_type}']
    if employee:
        parts.append(f'employee={employee.name}(id={employee.id})')
    if badge_id:
        parts.append(f'badge_id={badge_id}')
    parts.append(f'ip={ip}')
    if detail:
        parts.append(f'detail={detail}')

    msg = ' | '.join(parts)

    if event_type in ('login_failed', 'account_locked'):
        _logger.warning(msg)
    else:
        _logger.info(msg)


def _get_client_ip():
    """Extract the real client IP, respecting proxy headers."""
    try:
        forwarded = request.httprequest.headers.get('X-Forwarded-For', '')
        if forwarded:
            # Take the first IP in the chain (client's original IP)
            return forwarded.split(',')[0].strip()
        return request.httprequest.remote_addr or 'unknown'
    except Exception:
        return 'unknown'
