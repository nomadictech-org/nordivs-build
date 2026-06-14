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


def _parse_iso_datetime(value):
    """Parse an ISO-8601 datetime, returning a naive UTC datetime.

    Accepts 'Z' suffix or explicit offset; Odoo stores all datetimes as
    naive UTC, so we strip the tzinfo after normalizing.
    """
    raw = str(value).strip().replace('Z', '+00:00')
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        # Convert to UTC then drop tzinfo
        from datetime import timezone as _tz
        parsed = parsed.astimezone(_tz.utc).replace(tzinfo=None)
    return parsed


# -------------------------------------------------------------------------
# Geo Coordinate Validation (shared by attendance endpoints)
# -------------------------------------------------------------------------

def validate_geo_coords(data):
    """Pull and validate optional latitude/longitude from a request body.

    Returns (latitude, longitude, error). Either coord may be None if not
    provided; both must be present together to be meaningful but we don't
    enforce that — Odoo's geo fields tolerate one or the other.
    """
    lat = data.get('latitude')
    lng = data.get('longitude')

    if lat is not None and lat != '':
        try:
            lat = float(lat)
            if not -90 <= lat <= 90:
                raise ValueError
        except (ValueError, TypeError):
            return None, None, 'latitude must be a number between -90 and 90.'
    else:
        lat = None

    if lng is not None and lng != '':
        try:
            lng = float(lng)
            if not -180 <= lng <= 180:
                raise ValueError
        except (ValueError, TypeError):
            return None, None, 'longitude must be a number between -180 and 180.'
    else:
        lng = None

    return lat, lng, None


# -------------------------------------------------------------------------
# Manual Attendance Submission ("Apply Attendance")
# -------------------------------------------------------------------------

MAX_BACKDATE_DAYS = 30


def validate_attendance_apply(data):
    """Validate a manual attendance submission.

    Expected:
        {
            "check_in": "2026-06-13T08:00:00Z",
            "check_out": "2026-06-13T17:00:00Z",  (optional — open attendance if omitted)
            "latitude": 18.5204,                  (optional)
            "longitude": 73.8567                  (optional)
        }

    Rules:
        - check_in is required
        - check_in cannot be in the future (small +5min tolerance for clock skew)
        - check_in cannot be more than MAX_BACKDATE_DAYS old
        - check_out, if provided, must be strictly after check_in
        - check_out cannot be in the future
    """
    check_in_raw = data.get('check_in')
    if not check_in_raw:
        return None, 'check_in is required (ISO 8601 datetime).'

    try:
        check_in = _parse_iso_datetime(check_in_raw)
    except (ValueError, TypeError):
        return None, 'check_in must be a valid ISO 8601 datetime.'

    now = datetime.utcnow()
    skew = timedelta(minutes=5)

    if check_in > now + skew:
        return None, 'check_in cannot be in the future.'
    if (now - check_in).days > MAX_BACKDATE_DAYS:
        return None, f'check_in cannot be more than {MAX_BACKDATE_DAYS} days in the past.'

    check_out = None
    check_out_raw = data.get('check_out')
    if check_out_raw:
        try:
            check_out = _parse_iso_datetime(check_out_raw)
        except (ValueError, TypeError):
            return None, 'check_out must be a valid ISO 8601 datetime.'
        if check_out <= check_in:
            return None, 'check_out must be after check_in.'
        if check_out > now + skew:
            return None, 'check_out cannot be in the future.'

    lat, lng, geo_err = validate_geo_coords(data)
    if geo_err:
        return None, geo_err

    return {
        'check_in': check_in,
        'check_out': check_out,
        'latitude': lat,
        'longitude': lng,
    }, None


# -------------------------------------------------------------------------
# Timesheet Submission ("Apply Timesheet")
# -------------------------------------------------------------------------

MAX_TIMESHEET_HOURS_PER_ENTRY = 24


def validate_timesheet_create(data):
    """Validate a timesheet entry submission.

    Expected:
        {
            "project_id": 5,
            "task_id": 12,           (optional — may be a project-level entry)
            "date": "2026-06-13",
            "unit_amount": 3.5,      (hours)
            "description": "Worked on the auth refactor"  (optional)
        }
    """
    project_id = data.get('project_id')
    if not project_id:
        return None, 'project_id is required.'
    try:
        project_id = int(project_id)
        if project_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, 'project_id must be a positive integer.'

    task_id = data.get('task_id')
    if task_id is not None and task_id != '':
        try:
            task_id = int(task_id)
            if task_id <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return None, 'task_id must be a positive integer.'
    else:
        task_id = None

    date_raw = data.get('date')
    if not date_raw:
        return None, 'date is required (YYYY-MM-DD).'
    try:
        date_val = _parse_date(date_raw)
    except (ValueError, TypeError):
        return None, 'date must be a valid date (YYYY-MM-DD).'

    if date_val > date.today() + timedelta(days=1):
        return None, 'Cannot create a timesheet entry for a future date.'

    unit_amount = data.get('unit_amount')
    if unit_amount is None or unit_amount == '':
        return None, 'unit_amount is required (in hours).'
    try:
        unit_amount = float(unit_amount)
    except (ValueError, TypeError):
        return None, 'unit_amount must be a number.'
    if unit_amount <= 0:
        return None, 'unit_amount must be greater than zero.'
    if unit_amount > MAX_TIMESHEET_HOURS_PER_ENTRY:
        return None, f'unit_amount cannot exceed {MAX_TIMESHEET_HOURS_PER_ENTRY} hours per entry.'

    # 'description' on the API maps to 'name' on the model
    description = str(data.get('description', '')).strip()[:500]

    return {
        'project_id': project_id,
        'task_id': task_id,
        'date': date_val,
        'unit_amount': unit_amount,
        'name': description or '/',  # Odoo convention: '/' for blank
    }, None
