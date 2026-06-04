# -*- coding: utf-8 -*-
"""Standardized HTTP JSON response builders.

Every API endpoint returns one of these. The envelope is always:

    Success: {"status": "success", "data": {...}, "meta": {...}}
    Error:   {"status": "error", "error": {"code": "...", "message": "..."}}

This module ensures no endpoint accidentally leaks Python tracebacks,
Odoo model names, or internal field names to the mobile client.
"""
import json
import logging
import traceback

from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Success Responses
# -------------------------------------------------------------------------

def success(data=None, status=200, meta=None):
    """Return a standard success JSON response.

    Args:
        data: The response payload (dict, list, or None).
        status: HTTP status code (default 200).
        meta: Optional pagination metadata dict.

    Returns:
        werkzeug.wrappers.Response with JSON body.
    """
    body = {'status': 'success'}
    if data is not None:
        body['data'] = data
    if meta is not None:
        body['meta'] = meta
    return _json_response(body, status)


def success_list(data, total_count, offset, limit):
    """Return a paginated list response with metadata.

    Args:
        data: List of serialized records.
        total_count: Total matching records (before pagination).
        offset: Current offset.
        limit: Current limit.

    Returns:
        Response with data + pagination meta.
    """
    meta = {
        'count': total_count,
        'offset': offset,
        'limit': limit,
        'has_more': (offset + limit) < total_count,
    }
    return success(data=data, meta=meta)


def created(data):
    """Return a 201 Created response (for POST create operations)."""
    return success(data=data, status=201)


# -------------------------------------------------------------------------
# Error Responses
# -------------------------------------------------------------------------

# Standard error code constants — used in both Python and Flutter
ERR_MISSING_AUTH = 'MISSING_AUTH'
ERR_INVALID_TOKEN = 'INVALID_TOKEN'
ERR_INVALID_CREDENTIALS = 'INVALID_CREDENTIALS'
ERR_ACCOUNT_LOCKED = 'ACCOUNT_LOCKED'
ERR_ACCESS_DISABLED = 'ACCESS_DISABLED'
ERR_NOT_FOUND = 'NOT_FOUND'
ERR_VALIDATION = 'VALIDATION_ERROR'
ERR_STATE = 'STATE_ERROR'
ERR_METHOD_NOT_ALLOWED = 'METHOD_NOT_ALLOWED'
ERR_SERVER = 'SERVER_ERROR'


def error(code, message, status=400):
    """Return a standard error JSON response.

    Args:
        code: Machine-readable error code (e.g., 'INVALID_TOKEN').
        message: Human-readable message for the mobile app to display.
        status: HTTP status code.

    Returns:
        werkzeug.wrappers.Response with JSON error body.
    """
    body = {
        'status': 'error',
        'error': {
            'code': code,
            'message': message,
        },
    }
    return _json_response(body, status)


def error_400(code, message):
    """400 Bad Request — malformed input."""
    return error(code, message, 400)


def error_401(code, message):
    """401 Unauthorized — bad credentials or token."""
    return error(code, message, 401)


def error_403(code, message):
    """403 Forbidden — authenticated but not allowed."""
    return error(code, message, 403)


def error_404(message='Resource not found'):
    """404 Not Found — record missing or not owned by this employee."""
    return error(ERR_NOT_FOUND, message, 404)


def error_409(message):
    """409 Conflict — invalid state transition."""
    return error(ERR_STATE, message, 409)


def error_422(message):
    """422 Unprocessable Entity — validation failure."""
    return error(ERR_VALIDATION, message, 422)


def error_429(message, retry_after=None):
    """429 Too Many Requests — rate limited or account locked."""
    resp = error(ERR_ACCOUNT_LOCKED, message, 429)
    if retry_after:
        resp.headers['Retry-After'] = str(retry_after)
    return resp


def error_500(exception=None):
    """500 Internal Server Error — unhandled exception.

    NEVER leaks the traceback to the client. Logs it server-side.
    """
    if exception:
        _logger.error(
            'Unhandled API error:\n%s', traceback.format_exc()
        )
    return error(
        ERR_SERVER,
        'An internal error occurred. Please try again later.',
        500,
    )


# -------------------------------------------------------------------------
# Internal
# -------------------------------------------------------------------------

def _json_response(body, status):
    """Build a werkzeug Response with JSON content type.

    Uses json.dumps with ensure_ascii=False for proper UTF-8 support
    (employee names, Arabic/Hindi/CJK characters in announcements, etc.).
    """
    return Response(
        json.dumps(body, ensure_ascii=False, default=_json_serial),
        content_type='application/json; charset=utf-8',
        status=status,
    )


def _json_serial(obj):
    """JSON serializer fallback for types json.dumps doesn't handle natively.

    Handles:
    - datetime/date objects → ISO format strings
    - bytes → UTF-8 string
    - Odoo recordsets → list of IDs (safety net, should never reach here
      if serializers are written correctly)
    """
    import datetime as dt
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    if hasattr(obj, 'ids'):
        # Odoo recordset — this is a bug if it reaches here, but safer
        # than crashing. Log a warning so we catch it in dev.
        _logger.warning(
            'Recordset leaked into JSON response: %s(%s)',
            obj._name, obj.ids,
        )
        return obj.ids
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')
