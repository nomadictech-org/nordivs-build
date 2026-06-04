# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class HrEmployeeInherit(models.Model):
    _inherit = 'hr.employee'

    # -------------------------------------------------------------------------
    # New Fields for Mobile API
    # -------------------------------------------------------------------------

    api_enabled = fields.Boolean(
        string='Mobile App Access',
        default=False,
        tracking=True,
        help='Toggle ON to allow this employee to log in via the mobile app. '
             'Toggle OFF to instantly block access (existing tokens become '
             'invalid at their next request).',
    )
    api_pin_hash = fields.Char(
        string='API PIN Hash',
        size=256,
        copy=False,
        groups='hr.group_hr_manager',
        help='PBKDF2-hashed PIN for mobile app authentication. '
             'Never stores the raw PIN.',
    )
    api_failed_attempts = fields.Integer(
        string='Failed Login Attempts',
        default=0,
        copy=False,
    )
    api_locked_until = fields.Datetime(
        string='Locked Until',
        copy=False,
        help='Account is locked until this timestamp after repeated '
             'failed login attempts.',
    )
    api_token_count = fields.Integer(
        string='Active Sessions',
        compute='_compute_api_token_count',
    )
    api_pin_set = fields.Boolean(
        string='PIN Configured',
        compute='_compute_api_pin_set',
        help='Indicates whether the employee has a PIN set for mobile access.',
    )

    # -------------------------------------------------------------------------
    # Computed Fields
    # -------------------------------------------------------------------------

    def _compute_api_token_count(self):
        """Count active API tokens for each employee.

        Uses a single grouped read_group call instead of N+1 searches —
        this matters when viewing the employee list in the backend.
        """
        token_data = self.env['employee.api.token'].sudo().read_group(
            domain=[
                ('employee_id', 'in', self.ids),
                ('is_active', '=', True),
                ('expires_at', '>', fields.Datetime.now()),
            ],
            fields=['employee_id'],
            groupby=['employee_id'],
        )
        counts = {
            item['employee_id'][0]: item['employee_id_count']
            for item in token_data
        }
        for employee in self:
            employee.api_token_count = counts.get(employee.id, 0)

    @api.depends('api_pin_hash')
    def _compute_api_pin_set(self):
        for employee in self:
            employee.api_pin_set = bool(employee.api_pin_hash)

    # -------------------------------------------------------------------------
    # PIN Management
    # -------------------------------------------------------------------------

    def set_api_pin(self, raw_pin):
        """Hash and store a new PIN.

        Args:
            raw_pin: The plaintext PIN string (4-8 digits recommended).

        Raises:
            ValidationError: If the PIN is empty, too short, or non-numeric.
        """
        self.ensure_one()

        if not raw_pin or not raw_pin.strip():
            raise ValidationError('PIN cannot be empty.')
        raw_pin = raw_pin.strip()

        if len(raw_pin) < 4:
            raise ValidationError('PIN must be at least 4 characters.')
        if len(raw_pin) > 8:
            raise ValidationError('PIN must be at most 8 characters.')
        if not raw_pin.isdigit():
            raise ValidationError('PIN must contain only digits.')

        self.sudo().write({
            'api_pin_hash': generate_password_hash(
                raw_pin, method='pbkdf2:sha256:600000'
            ),
            'api_failed_attempts': 0,
            'api_locked_until': False,
        })
        _logger.info(
            'API PIN set for employee %s (id=%d)', self.name, self.id
        )

    def verify_api_pin(self, raw_pin):
        """Verify a submitted PIN against the stored hash.

        Returns:
            True if the PIN matches, False otherwise.
        """
        self.ensure_one()
        if not self.api_pin_hash or not raw_pin:
            return False
        return check_password_hash(self.api_pin_hash, raw_pin.strip())

    # -------------------------------------------------------------------------
    # Brute-Force Protection
    # -------------------------------------------------------------------------

    def register_failed_attempt(self):
        """Increment the failure counter. Lock the account after MAX attempts.

        Called by the login endpoint when PIN verification fails.
        """
        self.ensure_one()
        new_count = self.api_failed_attempts + 1
        vals = {'api_failed_attempts': new_count}

        if new_count >= MAX_FAILED_ATTEMPTS:
            lock_until = fields.Datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
            vals['api_locked_until'] = lock_until
            _logger.warning(
                'Employee %s (id=%d) locked until %s after %d failed attempts',
                self.name, self.id, lock_until, new_count,
            )

        self.sudo().write(vals)

    def reset_failed_attempts(self):
        """Clear the failure counter and lockout. Called on successful login."""
        self.ensure_one()
        if self.api_failed_attempts > 0 or self.api_locked_until:
            self.sudo().write({
                'api_failed_attempts': 0,
                'api_locked_until': False,
            })

    def is_locked(self):
        """Check whether this employee is currently locked out.

        Returns:
            True if locked, False if unlocked or lock has expired.
        """
        self.ensure_one()
        if not self.api_locked_until:
            return False
        return self.api_locked_until > fields.Datetime.now()

    def get_lockout_remaining_seconds(self):
        """Return seconds remaining on the lockout, or 0 if not locked."""
        self.ensure_one()
        if not self.is_locked():
            return 0
        delta = self.api_locked_until - fields.Datetime.now()
        return max(0, int(delta.total_seconds()))

    # -------------------------------------------------------------------------
    # Scheduled Actions
    # -------------------------------------------------------------------------

    @api.model
    def _cron_unlock_expired_locks(self):
        """Every 5 minutes: clear lockouts that have expired naturally.

        This ensures that an employee whose 15-minute lockout has passed
        can log in immediately, rather than waiting for the login endpoint
        to lazily check the timestamp.
        """
        locked = self.sudo().search([
            ('api_locked_until', '!=', False),
            ('api_locked_until', '<', fields.Datetime.now()),
        ])
        if locked:
            locked.write({
                'api_failed_attempts': 0,
                'api_locked_until': False,
            })
            _logger.info('Unlocked %d employee accounts.', len(locked))

    # -------------------------------------------------------------------------
    # HR Admin Actions
    # -------------------------------------------------------------------------

    def action_set_api_pin_wizard(self):
        """Open a wizard for HR to set/reset an employee's mobile PIN.

        Returns an action dict to open the wizard form view.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Set Mobile PIN',
            'res_model': 'employee.api.pin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def action_revoke_all_api_tokens(self):
        """HR action: revoke every active mobile session for this employee."""
        self.ensure_one()
        tokens = self.env['employee.api.token'].sudo().search([
            ('employee_id', '=', self.id),
            ('is_active', '=', True),
        ])
        if tokens:
            tokens.write({'is_active': False})
        return {
            'type': 'ir.client_tag',
            'tag': 'display_notification',
            'params': {
                'title': 'Sessions Revoked',
                'message': f'{len(tokens)} active session(s) revoked for {self.name}.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_toggle_api_access(self):
        """Quick toggle for api_enabled from list/form view."""
        self.ensure_one()
        new_state = not self.api_enabled
        self.api_enabled = new_state

        # If disabling, also revoke all active tokens immediately
        if not new_state:
            self.action_revoke_all_api_tokens()

        return True
