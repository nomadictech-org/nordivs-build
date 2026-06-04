# -*- coding: utf-8 -*-
"""Authentication and session management endpoints.

These are the only endpoints in the system that don't require a valid token
(login) or that manage token lifecycle (logout, verify, change PIN).

Route table:
    POST  /api/employee/login          Authenticate with badge + PIN
    POST  /api/employee/logout         Revoke current token
    POST  /api/employee/token/verify   Check if stored token is still valid
    POST  /api/employee/pin/change     Change PIN (requires current PIN)
    GET   /api/employee/sessions       List active sessions for this employee
    POST  /api/employee/sessions/revoke-all  Revoke all other sessions

Security notes:
    - /login uses auth='none' — no Odoo session or user context
    - Error messages for badge/PIN are identical to prevent enumeration
    - Brute-force protection: 5 attempts → 15-minute lockout
    - Audit logging on every auth event
"""
import logging

from odoo import http, fields
from odoo.http import request
from odoo import http, fields, SUPERUSER_ID
from ..helpers import response_helper as R
from ..helpers import token_helper
from ..helpers import validators as V

_logger = logging.getLogger(__name__)


class EmployeeAuthController(http.Controller):

    # =====================================================================
    # LOGIN
    # =====================================================================

    @http.route(
        '/api/employee/login',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def login(self, **kw):
        """Authenticate an employee with badge ID and PIN.

        Request body:
            {
                "badge_id": "EMP001",
                "pin": "1234",
                "device_info": "Pixel 8, Android 15"  (optional)
            }

        Success response (200):
            {
                "status": "success",
                "data": {
                    "token": "a1b2c3...",
                    "expires_at": "2026-07-02T10:00:00",
                    "employee": { ...profile... }
                }
            }

        Error responses:
            400 — missing badge_id or pin
            401 — invalid credentials (same message for bad badge or bad PIN)
            403 — api_enabled is False
            429 — account locked after too many failed attempts
        """
        # Handle CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            # Step 1: Parse and validate input
            body, parse_err = V.parse_json_body()
            if parse_err:
                return R.error_400(R.ERR_VALIDATION, parse_err)

            data, val_err = V.validate_login(body)
            if val_err:
                return R.error_400(R.ERR_VALIDATION, val_err)

            badge_id = data['badge_id']
            pin = data['pin']
            device_info = data['device_info']
            client_ip = token_helper._get_client_ip()

            # Step 2: Find the employee by badge (barcode field)
            env = request.env(user=SUPERUSER_ID)
            employee = env['hr.employee'].search([
                ('barcode', '=', badge_id),
            ], limit=1)

            if not employee:
                token_helper.log_auth_event(
                    'login_failed', badge_id=badge_id, ip=client_ip,
                    detail='badge_id not found',
                )
                # Generic message — never reveal that the badge doesn't exist
                return R.error_401(
                    R.ERR_INVALID_CREDENTIALS,
                    'Invalid credentials.',
                )

            # Step 3: Check if API access is enabled by HR
            if not employee.api_enabled:
                token_helper.log_auth_event(
                    'login_failed', employee=employee, ip=client_ip,
                    detail='api_enabled=False',
                )
                return R.error_403(
                    R.ERR_ACCESS_DISABLED,
                    'Mobile app access is not enabled for your account. '
                    'Please contact HR.',
                )

            # Step 4: Check if account is locked
            if employee.is_locked():
                remaining = employee.get_lockout_remaining_seconds()
                minutes_left = max(1, remaining // 60)
                token_helper.log_auth_event(
                    'login_failed', employee=employee, ip=client_ip,
                    detail=f'account_locked, {remaining}s remaining',
                )
                return R.error_429(
                    f'Account is temporarily locked. '
                    f'Try again in {minutes_left} minute(s).',
                    retry_after=remaining,
                )

            # Step 5: Check if PIN has been set
            if not employee.api_pin_hash:
                token_helper.log_auth_event(
                    'login_failed', employee=employee, ip=client_ip,
                    detail='no PIN configured',
                )
                return R.error_401(
                    R.ERR_INVALID_CREDENTIALS,
                    'Invalid credentials.',
                )

            # Step 6: Verify the PIN
            if not employee.verify_api_pin(pin):
                employee.register_failed_attempt()

                detail = f'wrong PIN, attempt #{employee.api_failed_attempts}'
                if employee.is_locked():
                    token_helper.log_auth_event(
                        'account_locked', employee=employee, ip=client_ip,
                        detail=detail,
                    )
                else:
                    token_helper.log_auth_event(
                        'login_failed', employee=employee, ip=client_ip,
                        detail=detail,
                    )

                return R.error_401(
                    R.ERR_INVALID_CREDENTIALS,
                    'Invalid credentials.',
                )

            # Step 7: PIN correct — clear any previous failed attempts
            employee.reset_failed_attempts()

            # Step 8: Generate bearer token
            token_data = token_helper.generate_token(employee, device_info)

            # Step 9: Build success response with employee profile
            token_helper.log_auth_event(
                'login_success', employee=employee, ip=client_ip,
                detail=f'device={device_info}',
            )

            return R.success({
                'token': token_data['token'],
                'expires_at': token_data['expires_at'].isoformat(),
                'employee': self._serialize_profile(employee),
            })

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # LOGOUT
    # =====================================================================

    @http.route(
        '/api/employee/logout',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def logout(self, **kw):
        """Revoke the current bearer token.

        This invalidates the session for the device that sent the request.
        Other devices with different tokens remain logged in.

        Success response (200):
            {"status": "success", "data": {"message": "Logged out successfully"}}
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            # Find and revoke the specific token used in this request
            auth_header = request.httprequest.headers.get('Authorization', '')
            token_str = auth_header[7:].strip()

            token_record = request.env['employee.api.token'].sudo().search([
                ('token', '=', token_str),
                ('is_active', '=', True),
            ], limit=1)

            if token_record:
                token_record.revoke()

            token_helper.log_auth_event(
                'logout', employee=employee,
            )

            return R.success({'message': 'Logged out successfully.'})

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # TOKEN VERIFY
    # =====================================================================

    @http.route(
        '/api/employee/token/verify',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def verify_token(self, **kw):
        """Check if the stored token is still valid.

        Called by Flutter on app launch to decide: show login screen or home?
        This is a lightweight call — no heavy data loading.

        Success response (200):
            {
                "status": "success",
                "data": {
                    "valid": true,
                    "employee": { ...profile... }
                }
            }

        Error response (401):
            Token is expired, revoked, or employee deactivated.
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            return R.success({
                'valid': True,
                'employee': self._serialize_profile(employee),
            })

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # CHANGE PIN
    # =====================================================================

    @http.route(
        '/api/employee/pin/change',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def change_pin(self, **kw):
        """Change the employee's mobile app PIN.

        Requires the current PIN for verification (prevents someone who
        steals an unlocked phone from changing the PIN).

        Request body:
            {
                "current_pin": "0000",
                "new_pin": "1234",
                "confirm_pin": "1234"
            }

        Success response (200):
            {"status": "success", "data": {"message": "PIN changed successfully"}}

        Error responses:
            401 — invalid token
            401 — current_pin is wrong
            422 — validation errors (too short, non-numeric, mismatch)
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

            data, val_err = V.validate_pin_change(body)
            if val_err:
                return R.error_422(val_err)

            # Verify current PIN before allowing change
            if not employee.verify_api_pin(data['current_pin']):
                return R.error_401(
                    R.ERR_INVALID_CREDENTIALS,
                    'Current PIN is incorrect.',
                )

            # Set the new PIN (hashes automatically)
            employee.set_api_pin(data['new_pin'])

            token_helper.log_auth_event(
                'pin_changed', employee=employee,
            )

            return R.success({'message': 'PIN changed successfully.'})

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # SESSION MANAGEMENT
    # =====================================================================

    @http.route(
        '/api/employee/sessions',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def list_sessions(self, **kw):
        """List all active sessions (tokens) for the authenticated employee.

        Lets the employee see which devices are logged in.

        Success response (200):
            {
                "status": "success",
                "data": [
                    {
                        "id": 5,
                        "device_info": "Pixel 8, Android 15",
                        "created_at": "2026-06-02T08:00:00",
                        "last_used_at": "2026-06-02T15:30:00",
                        "is_current": true
                    }
                ]
            }
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            # Get current token to mark which session is "this device"
            auth_header = request.httprequest.headers.get('Authorization', '')
            current_token = auth_header[7:].strip() if auth_header else ''

            tokens = request.env['employee.api.token'].sudo().search([
                ('employee_id', '=', employee.id),
                ('is_active', '=', True),
                ('expires_at', '>', fields.Datetime.now()),
            ], order='last_used_at desc')

            sessions = []
            for t in tokens:
                sessions.append({
                    'id': t.id,
                    'device_info': t.device_info or 'Unknown device',
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
                    'is_current': t.token == current_token,
                })

            return R.success(sessions)

        except Exception as e:
            return R.error_500(exception=e)

    @http.route(
        '/api/employee/sessions/revoke-all',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def revoke_other_sessions(self, **kw):
        """Revoke all sessions except the current one.

        Useful when an employee suspects someone else has their token.
        This is the "log out everywhere else" button.

        Success response (200):
            {"status": "success", "data": {"revoked_count": 2}}
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            # Find current token
            auth_header = request.httprequest.headers.get('Authorization', '')
            current_token = auth_header[7:].strip()

            # Revoke all OTHER active tokens
            other_tokens = request.env['employee.api.token'].sudo().search([
                ('employee_id', '=', employee.id),
                ('is_active', '=', True),
                ('token', '!=', current_token),
            ])

            count = len(other_tokens)
            if other_tokens:
                other_tokens.write({'is_active': False})

            token_helper.log_auth_event(
                'sessions_revoked', employee=employee,
                detail=f'revoked {count} other sessions',
            )

            return R.success({'revoked_count': count})

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # Profile Serializer (used by login + verify)
    # =====================================================================

    def _serialize_profile(self, employee):
        """Serialize employee profile for login/verify responses.

        This is intentionally a method on the controller, not a standalone
        serializer, because profile serialization at login may differ from
        the full profile endpoint (which includes more fields).
        """
        return {
            'id': employee.id,
            'name': employee.name or '',
            'department': employee.department_id.name if employee.department_id else None,
            'job_title': employee.job_title or (
                employee.job_id.name if employee.job_id else None
            ),
            'work_email': employee.work_email or None,
            'work_phone': employee.work_phone or None,
            'company': employee.company_id.name if employee.company_id else None,
            'photo_url': f'/api/employee/profile/photo' if employee.image_128 else None,
        }

    # =====================================================================
    # CORS Helper
    # =====================================================================

    def _cors_preflight(self):
        """Handle CORS preflight (OPTIONS) requests.

        Required because Flutter (web build) and debugging tools
        may send preflight requests.
        """
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
