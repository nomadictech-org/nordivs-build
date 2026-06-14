# -*- coding: utf-8 -*-
"""Field-whitelist serializers — turn Odoo records into safe API dicts.

Every model exposed to Flutter has exactly one serializer here. The serializer
is the only place that decides which fields cross the security boundary; if a
field isn't listed in a serializer, it is not in the API response. This is the
implementation of the "field whitelisting" security rule.

All datetimes are emitted as ISO-8601 strings in UTC (Odoo stores naive UTC).
Flutter must treat them as UTC even though the trailing 'Z' is omitted to stay
consistent with the existing auth responses.
"""


# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _iso(dt):
    """Format a datetime/date as ISO-8601 string, or None if falsy."""
    if not dt:
        return None
    return dt.isoformat()


def _round(value, digits=2):
    """Round a float defensively (handles None, False, 0)."""
    return round(float(value or 0.0), digits)


# -------------------------------------------------------------------------
# hr.attendance
# -------------------------------------------------------------------------

def serialize_attendance(att):
    """Serialize a single hr.attendance record.

    Excludes audit fields (create_uid, write_uid, write_date) and internal
    flags (color, no_validated_overtime_hours, expected_hours) that the
    mobile app has no use for.
    """
    return {
        'id': att.id,
        'check_in': _iso(att.check_in),
        'check_out': _iso(att.check_out),
        'worked_hours': _round(att.worked_hours),
        'overtime_hours': _round(att.overtime_hours),
        'validated_overtime_hours': _round(att.validated_overtime_hours),
        'overtime_status': att.overtime_status or None,
        'in_mode': att.in_mode,
        'out_mode': att.out_mode,
        'in_latitude': att.in_latitude or None,
        'in_longitude': att.in_longitude or None,
        'out_latitude': att.out_latitude or None,
        'out_longitude': att.out_longitude or None,
        'in_city': att.in_city or None,
        'out_city': att.out_city or None,
        'in_country_name': att.in_country_name or None,
        'out_country_name': att.out_country_name or None,
        'is_open': not att.check_out,
    }


def serialize_attendance_list(records):
    """Serialize a recordset of hr.attendance records."""
    return [serialize_attendance(r) for r in records]


def serialize_attendance_status(employee):
    """Dashboard 'current status' payload.

    Combines the employee-level aggregates (hours_today, total_overtime, etc.)
    with the current open attendance, if any. Driven by the Flutter dashboard's
    Clock Toggle + Balance Cards.
    """
    last_att = employee.last_attendance_id
    is_open = bool(last_att and not last_att.check_out)

    return {
        'attendance_state': employee.attendance_state,
        'is_checked_in': employee.attendance_state == 'checked_in',
        'hours_today': _round(employee.hours_today),
        'hours_previously_today': _round(employee.hours_previously_today),
        'last_attendance_worked_hours': _round(employee.last_attendance_worked_hours),
        'hours_last_month': _round(employee.hours_last_month),
        'total_overtime': _round(employee.total_overtime),
        'last_check_in': _iso(employee.last_check_in),
        'last_check_out': _iso(employee.last_check_out),
        'current_attendance': serialize_attendance(last_att) if is_open else None,
    }


# -------------------------------------------------------------------------
# account.analytic.line (timesheets)
# -------------------------------------------------------------------------

def serialize_timesheet(line):
    """Serialize a single timesheet entry (account.analytic.line).

    The 'name' field defaults to '/' in Odoo when blank — we map that to an
    empty string so Flutter doesn't show a stray slash.
    """
    return {
        'id': line.id,
        'date': _iso(line.date),
        'description': line.name if line.name and line.name != '/' else '',
        'unit_amount': _round(line.unit_amount),
        'project_id': line.project_id.id if line.project_id else None,
        'project_name': line.project_id.name if line.project_id else None,
        'task_id': line.task_id.id if line.task_id else None,
        'task_name': line.task_id.name if line.task_id else None,
    }


def serialize_timesheet_list(records):
    """Serialize a recordset of timesheet entries."""
    return [serialize_timesheet(r) for r in records]


# -------------------------------------------------------------------------
# project.project + project.task (lookup data for timesheet form)
# -------------------------------------------------------------------------

def serialize_project(project, include_tasks=False):
    """Serialize a project. Optionally embed its tasks for one-shot fetch."""
    data = {
        'id': project.id,
        'name': project.name,
        'allow_timesheets': project.allow_timesheets,
    }
    if include_tasks:
        data['tasks'] = [
            serialize_task(t)
            for t in project.task_ids
            if t.active and t.allow_timesheets
        ]
    return data


def serialize_task(task):
    """Serialize a task — light payload for dropdown lists."""
    return {
        'id': task.id,
        'name': task.name,
        'project_id': task.project_id.id if task.project_id else None,
    }
