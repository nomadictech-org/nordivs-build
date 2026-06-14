# -*- coding: utf-8 -*-
"""Attendance endpoints — the only WRITE path the offline queue cares about.

These endpoints sit between Flutter and Odoo's native `hr.attendance` model.
The toggle endpoint mirrors what `hr.employee._attendance_action_change`
does in the native systray, but is split into two branches:

    online  → delegate to `_attendance_action_change(geo)`
              (lets Odoo own the state-machine decision)
    offline → bypass it and write the device timestamp directly
              (so a queued action retains its true wall-clock time)

Route table:
    GET   /api/employee/attendance/status   Dashboard payload (state + hours)
    POST  /api/employee/attendance/toggle   Clock in/out (online or replay)
    GET   /api/employee/attendance          Paginated history for this employee
    POST  /api/employee/attendance          Manual submission ("apply")

Security contract on every endpoint:
    - validate_request() at the top (auth gate)
    - ownership domain `[('employee_id', '=', employee.id)]` on every query
    - never accept an `employee_id` from the request — always self
    - field whitelist via serializers.serialize_attendance
"""
import logging

from odoo import http, fields, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from ..helpers import response_helper as R
from ..helpers import token_helper
from ..helpers import validators as V
from ..helpers import serializers as S

_logger = logging.getLogger(__name__)


class EmployeeAttendanceController(http.Controller):

    # =====================================================================
    # Geo info builder — shared by toggle + apply
    # =====================================================================

    def _build_geo_info(self, latitude=None, longitude=None, mode='manual'):
        """Construct the geo dict in the shape native hr_attendance expects.

        Keys without the in_/out_ prefix; `_attendance_action_change` adds the
        prefix based on which side of the toggle it's writing. The IP and
        browser are sniffed from the current HTTP request; if Odoo's GeoIP
        middleware is active, city/country will be populated, otherwise empty.
        """
        try:
            geoip = getattr(request, 'geoip', None)
            city = (geoip and geoip.city and geoip.city.name) or ''
            country = (geoip and geoip.country and geoip.country.name) or ''
        except Exception:
            city, country = '', ''

        try:
            browser = request.httprequest.user_agent.browser or 'mobile'
        except Exception:
            browser = 'mobile'

        return {
            'latitude': latitude or False,
            'longitude': longitude or False,
            'ip_address': token_helper._get_client_ip(),
            'browser': browser,
            'city': city,
            'country_name': country,
            'mode': mode,
        }

    def _geo_to_attendance_vals(self, geo, side):
        """Translate the side-agnostic geo dict into hr.attendance fields.

        `side` is 'in' or 'out'. Only non-empty values are included so we
        don't overwrite existing data with blanks on the check-out write.
        """
        prefix = f'{side}_'
        return {
            f'{prefix}{key}': value
            for key, value in geo.items()
            if value not in (None, False, '')
        }

    # =====================================================================
    # GET /api/employee/attendance/status
    # =====================================================================

    @http.route(
        '/api/employee/attendance/status',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def get_status(self, **kw):
        """Return the dashboard payload: state, hours, current open attendance.

        Designed for stale-while-revalidate: cheap to call, returns everything
        the Dashboard tab needs in one shot.

        Success response (200):
            {
                "status": "success",
                "data": {
                    "attendance_state": "checked_in",
                    "is_checked_in": true,
                    "hours_today": 3.5,
                    "hours_last_month": 142.0,
                    "total_overtime": 4.5,
                    "last_check_in": "2026-06-13T08:00:00",
                    "last_check_out": null,
                    "current_attendance": { ... }   (or null if checked_out)
                }
            }
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            # The employee record we got back is already sudo-loaded by the
            # token helper, but invalidate cache to make sure recently-written
            # attendance affects the computed fields.
            employee.invalidate_recordset([
                'attendance_state', 'hours_today', 'hours_previously_today',
                'last_attendance_worked_hours', 'last_check_in',
                'last_check_out', 'last_attendance_id',
                'hours_last_month', 'total_overtime',
            ])

            return R.success(S.serialize_attendance_status(employee))

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # POST /api/employee/attendance/toggle
    # =====================================================================

    @http.route(
        '/api/employee/attendance/toggle',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def toggle(self, **kw):
        """Clock in or out, depending on current state.

        Request body (all fields optional):
            {
                "latitude": 18.5204,
                "longitude": 73.8567,
                "timestamp": "2026-06-13T08:00:00Z"   (offline-replay only)
            }

        Online path (no timestamp):
            Delegates to `employee._attendance_action_change(geo)` so Odoo's
            native state machine decides whether to create a check-in row
            or close the open one.

        Offline path (timestamp present):
            Bypasses `_attendance_action_change` (which would record
            sync-time) and writes the device timestamp directly. The 48-hour
            drift cap in the validator guards against bogus clocks.

        Success response (200):
            {
                "status": "success",
                "data": {
                    "action": "checked_in" | "checked_out",
                    "attendance": { ...serialized... },
                    "state": { ...status payload... }
                }
            }

        Error responses:
            422 — bad timestamp or coords
            409 — state conflict (e.g. trying to check out with no open record,
                  or backdated check-in overlaps an existing record)
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            body, parse_err = V.parse_json_body()
            if parse_err:
                return R.error_400(R.ERR_VALIDATION, parse_err)

            lat, lng, geo_err = V.validate_geo_coords(body)
            if geo_err:
                return R.error_422(geo_err)

            ts, ts_err = V.validate_attendance_timestamp(body)
            if ts_err:
                return R.error_422(ts_err)

            geo = self._build_geo_info(latitude=lat, longitude=lng, mode='manual')
            env = request.env(user=SUPERUSER_ID)

            # ----- decide path: online vs offline replay -----
            try:
                if ts is None:
                    # Online — native method picks the side
                    attendance = employee.sudo()._attendance_action_change(geo)
                else:
                    # Offline replay — write the device timestamp explicitly
                    if employee.attendance_state == 'checked_out':
                        attendance = env['hr.attendance'].create({
                            'employee_id': employee.id,
                            'check_in': ts,
                            **self._geo_to_attendance_vals(geo, 'in'),
                        })
                    else:
                        attendance = env['hr.attendance'].search([
                            ('employee_id', '=', employee.id),
                            ('check_out', '=', False),
                        ], limit=1)
                        if not attendance:
                            return R.error_409(
                                'No open attendance found to check out from.'
                            )
                        # Don't allow check_out before the open record's check_in
                        if ts <= attendance.check_in:
                            return R.error_409(
                                'Replayed check-out time is earlier than the '
                                'open check-in. Refusing to write.'
                            )
                        attendance.write({
                            'check_out': ts,
                            **self._geo_to_attendance_vals(geo, 'out'),
                        })
            except (UserError, ValidationError) as e:
                # _attendance_action_change raises UserError if there's no
                # corresponding check-in; _check_validity raises ValidationError
                # on overlap or double-open. Both are user-fixable state issues.
                return R.error_409(str(e))

            # Re-read employee state after the write
            employee.invalidate_recordset()
            action = 'checked_in' if employee.attendance_state == 'checked_in' else 'checked_out'

            _logger.info(
                'Attendance %s for employee %s (id=%d, attendance_id=%s, offline=%s)',
                action, employee.name, employee.id, attendance.id, ts is not None,
            )

            return R.success({
                'action': action,
                'attendance': S.serialize_attendance(attendance),
                'state': S.serialize_attendance_status(employee),
            })

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # GET /api/employee/attendance
    # =====================================================================

    @http.route(
        '/api/employee/attendance',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def list_attendance(self, **kw):
        """List the authenticated employee's attendance history.

        Query parameters:
            from   YYYY-MM-DD   (default: first day of current month)
            to     YYYY-MM-DD   (default: today)
            limit  int          (default: 20, max: 100)
            offset int          (default: 0)
            state  open|closed  (optional — open = check_out is empty)

        Success response (200):
            {
                "status": "success",
                "data": [ {...attendance...}, ... ],
                "meta": { "count": 142, "offset": 0, "limit": 20, "has_more": true }
            }
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            date_from, date_to, date_err = V.parse_date_range(request.params)
            if date_err:
                return R.error_422(date_err)

            limit, offset = V.parse_pagination(request.params)
            state = V.parse_state_filter(request.params, allowed_states=['open', 'closed'])

            # Ownership filter — non-negotiable, first clause
            domain = [
                ('employee_id', '=', employee.id),
                ('check_in', '>=', f'{date_from.isoformat()} 00:00:00'),
                ('check_in', '<=', f'{date_to.isoformat()} 23:59:59'),
            ]
            if state == 'open':
                domain.append(('check_out', '=', False))
            elif state == 'closed':
                domain.append(('check_out', '!=', False))

            env = request.env(user=SUPERUSER_ID)
            total = env['hr.attendance'].search_count(domain)
            records = env['hr.attendance'].search(
                domain, limit=limit, offset=offset, order='check_in desc',
            )

            return R.success_list(
                data=S.serialize_attendance_list(records),
                total_count=total,
                offset=offset,
                limit=limit,
            )

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # POST /api/employee/attendance
    # =====================================================================

    @http.route(
        '/api/employee/attendance',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def apply_attendance(self, **kw):
        """Manually create an attendance record ("apply attendance").

        Use this when an employee forgot to clock in/out and wants to submit
        a complete record retroactively. The same overlap and ordering
        constraints (`_check_validity`) apply as for the toggle path.

        Request body:
            {
                "check_in": "2026-06-13T08:00:00Z",   (required)
                "check_out": "2026-06-13T17:00:00Z",  (optional)
                "latitude": 18.5204,                  (optional)
                "longitude": 73.8567                  (optional)
            }

        Success response (201):
            {
                "status": "success",
                "data": { ...serialized attendance... }
            }

        Error responses:
            422 — validation error (missing/bad fields, future date, overlap with self)
            409 — conflicts with an existing attendance record for this employee
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            body, parse_err = V.parse_json_body()
            if parse_err:
                return R.error_400(R.ERR_VALIDATION, parse_err)

            data, val_err = V.validate_attendance_apply(body)
            if val_err:
                return R.error_422(val_err)

            geo = self._build_geo_info(
                latitude=data['latitude'],
                longitude=data['longitude'],
                mode='manual',
            )

            vals = {
                'employee_id': employee.id,
                'check_in': data['check_in'],
                **self._geo_to_attendance_vals(geo, 'in'),
            }
            if data['check_out']:
                vals['check_out'] = data['check_out']
                # On a single-shot apply with both sides, mirror the geo to out_
                vals.update(self._geo_to_attendance_vals(geo, 'out'))

            env = request.env(user=SUPERUSER_ID)

            try:
                attendance = env['hr.attendance'].create(vals)
            except (UserError, ValidationError) as e:
                return R.error_409(str(e))

            _logger.info(
                'Manual attendance applied by employee %s (id=%d, attendance_id=%d, '
                'check_in=%s, check_out=%s)',
                employee.name, employee.id, attendance.id,
                data['check_in'], data['check_out'],
            )

            return R.created(S.serialize_attendance(attendance))

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # CORS Helper
    # =====================================================================

    def _cors_preflight(self):
        """Handle CORS preflight (OPTIONS) requests."""
        from werkzeug.wrappers import Response
        return Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                'Access-Control-Max-Age': '86400',
            },
        )
