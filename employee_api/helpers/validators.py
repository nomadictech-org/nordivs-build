# -*- coding: utf-8 -*-
"""Input validation for API request bodies and query parameters.

Every function returns (cleaned_data, error_message).
If error_message is not None, the controller returns a 422 immediately.
If error_message is None, cleaned_data is safe to use in ORM calls.

These validators are intentionally strict — we reject anything ambiguous
rather than guessing what the client meant.
"""
import json
import logging
from datetime import date, datetime, timedelta

from odoo.http import request

_logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Pagination defaults
# -------------------------------------------------------------------------

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_OFFSET = 0


# -------------------------------------------------------------------------
# Request Body Parsing
# -------------------------------------------------------------------------

def parse_json_body():
    """Safely parse the JSON body from the current HTTP request.

    Returns:
        (dict, None) on success, (None, error_message) on failure.

    Handles:
    - Empty body
    - Non-JSON content type
    - Malformed JSON
    """
    try:
        raw = request.httprequest.get_data(as_text=True)
        if not raw or not raw.strip():
            return {}, None  # Empty body is valid for endpoints that don't need it
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None, 'Request body must be a JSON object.'
        return data, None
    except (json.JSONDecodeError, ValueError):
        return None, 'Invalid JSON in request body.'


# -------------------------------------------------------------------------
# Login Validation
# -------------------------------------------------------------------------

def validate_login(data):
    """Validate login request body.

    Expected:
        {
            "badge_id": "1234",
            "pin": "0000",
            "device_info": "Samsung Galaxy A54, Android 14"  (optional)
        }

    Returns:
        (cleaned_dict, None) or (None, error_message)
    """
    badge_id = data.get('badge_id')
    pin = data.get('pin')

    if not badge_id or not str(badge_id).strip():
        return None, 'badge_id is required.'
    if not pin or not str(pin).strip():
        return None, 'pin is required.'

    return {
        'badge_id': str(badge_id).strip(),
        'pin': str(pin).strip(),
        'device_info': str(data.get('device_info', '')).strip()[:256],
    }, None


# -------------------------------------------------------------------------
# PIN Change Validation
# -------------------------------------------------------------------------

def validate_pin_change(data):
    """Validate PIN change request body.

    Expected:
        {
            "current_pin": "0000",
            "new_pin": "1234",
            "confirm_pin": "1234"
        }
    """
    current = data.get('current_pin')
    new = data.get('new_pin')
    confirm = data.get('confirm_pin')

    if not current or not str(current).strip():
        return None, 'current_pin is required.'
    if not new or not str(new).strip():
        return None, 'new_pin is required.'
    if not confirm or not str(confirm).strip():
        return None, 'confirm_pin is required.'

    new = str(new).strip()
    confirm = str(confirm).strip()

    if new != confirm:
        return None, 'new_pin and confirm_pin do not match.'
    if len(new) < 4:
        return None, 'PIN must be at least 4 digits.'
    if len(new) > 8:
        return None, 'PIN must be at most 8 digits.'
    if not new.isdigit():
        return None, 'PIN must contain only digits.'

    return {
        'current_pin': str(current).strip(),
        'new_pin': new,
    }, None


# -------------------------------------------------------------------------
# Leave Request Validation
# -------------------------------------------------------------------------

def validate_leave_request(data):
    """Validate leave creation request body.

    Expected:
        {
            "leave_type_id": 3,
            "date_from": "2026-07-10",
            "date_to": "2026-07-14",
            "description": "Family vacation"  (optional)
        }
    """
    leave_type_id = data.get('leave_type_id')
    date_from = data.get('date_from')
    date_to = data.get('date_to')

    if not leave_type_id:
        return None, 'leave_type_id is required.'
    try:
        leave_type_id = int(leave_type_id)
        if leave_type_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, 'leave_type_id must be a positive integer.'

    if not date_from:
        return None, 'date_from is required (format: YYYY-MM-DD).'
    if not date_to:
        return None, 'date_to is required (format: YYYY-MM-DD).'

    try:
        parsed_from = _parse_date(date_from)
    except ValueError:
        return None, 'date_from must be a valid date (YYYY-MM-DD).'

    try:
        parsed_to = _parse_date(date_to)
    except ValueError:
        return None, 'date_to must be a valid date (YYYY-MM-DD).'

    if parsed_to < parsed_from:
        return None, 'date_to cannot be before date_from.'

    if parsed_from < date.today():
        return None, 'Cannot request leave for past dates.'

    description = str(data.get('description', '')).strip()[:500]

    return {
        'leave_type_id': leave_type_id,
        'date_from': parsed_from.isoformat(),
        'date_to': parsed_to.isoformat(),
        'description': description,
    }, None


# -------------------------------------------------------------------------
# Profile Update Validation
# -------------------------------------------------------------------------

def validate_profile_update(data):
    """Validate profile update — only whitelisted fields allowed.

    Allowed fields:
        - work_phone (string, max 20 chars)
        - emergency_contact (string, max 100 chars)
        - emergency_phone (string, max 20 chars)
    """
    allowed = {}
    errors = []

    if 'work_phone' in data:
        phone = str(data['work_phone']).strip()[:20]
        allowed['work_phone'] = phone

    if 'emergency_contact' in data:
        name = str(data['emergency_contact']).strip()[:100]
        allowed['emergency_contact'] = name

    if 'emergency_phone' in data:
        phone = str(data['emergency_phone']).strip()[:20]
        allowed['emergency_phone'] = phone

    if not allowed:
        return None, 'No valid fields to update. Allowed: work_phone, emergency_contact, emergency_phone.'

    return allowed, None


# -------------------------------------------------------------------------
# Attendance Timestamp Validation
# -------------------------------------------------------------------------

def validate_attendance_timestamp(data):
    """Validate an optional offline timestamp for attendance actions.

    If timestamp is provided, validate it's within 48 hours of now.
    If not provided, return None (use server time).

    Returns:
        (datetime_or_none, error_message)
    """
    ts = data.get('timestamp')
    if not ts:
        return None, None

    try:
        parsed = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        naive = parsed.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None, 'timestamp must be a valid ISO 8601 datetime.'

    now = datetime.utcnow()
    diff = abs((now - naive).total_seconds())
    max_drift = 48 * 3600  # 48 hours

    if diff > max_drift:
        return None, 'timestamp is too far from server time (max 48 hours).'

    return naive, None


# -------------------------------------------------------------------------
# Query Parameter Parsing
# -------------------------------------------------------------------------

def parse_pagination(params=None):
    """Parse limit and offset from query parameters.

    Args:
        params: Dict of query parameters (defaults to request.params).

    Returns:
        (limit, offset) tuple with sane defaults and hard caps.
    """
    if params is None:
        params = request.params

    try:
        limit = int(params.get('limit', DEFAULT_LIMIT))
    except (ValueError, TypeError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    try:
        offset = int(params.get('offset', DEFAULT_OFFSET))
    except (ValueError, TypeError):
        offset = DEFAULT_OFFSET
    offset = max(0, offset)

    return limit, offset


def parse_date_range(params=None):
    """Parse from/to date range from query parameters.

    Args:
        params: Dict of query parameters (defaults to request.params).

    Returns:
        (date_from, date_to, None) on success
        (None, None, error_message) on failure

    Defaults to current month if not provided.
    """
    if params is None:
        params = request.params

    today = date.today()

    date_from_str = params.get('from')
    date_to_str = params.get('to')

    if date_from_str:
        try:
            date_from = _parse_date(date_from_str)
        except ValueError:
            return None, None, "'from' must be a valid date (YYYY-MM-DD)."
    else:
        date_from = today.replace(day=1)

    if date_to_str:
        try:
            date_to = _parse_date(date_to_str)
        except ValueError:
            return None, None, "'to' must be a valid date (YYYY-MM-DD)."
    else:
        date_to = today

    if date_to < date_from:
        return None, None, "'to' date cannot be before 'from' date."

    # Hard cap: no more than 1 year of data per request
    if (date_to - date_from).days > 366:
        return None, None, 'Date range cannot exceed one year.'

    return date_from, date_to, None


def parse_state_filter(params=None, allowed_states=None):
    """Parse an optional state filter from query parameters.

    Args:
        params: Dict of query parameters.
        allowed_states: List of valid state values.

    Returns:
        state string or None.
    """
    if params is None:
        params = request.params

    state = params.get('state', '').strip().lower()
    if not state:
        return None

    if allowed_states and state not in allowed_states:
        return None  # Silently ignore invalid states (don't error)

    return state


# -------------------------------------------------------------------------
# Internal Helpers
# -------------------------------------------------------------------------

def _parse_date(value):
    """Parse a date string in YYYY-MM-DD format.

    Raises ValueError if the format is wrong or date is invalid.
    """
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
