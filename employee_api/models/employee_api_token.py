# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

TOKEN_EXPIRY_DAYS = 30
STALE_TOKEN_CLEANUP_DAYS = 7


class EmployeeApiToken(models.Model):
    _name = 'employee.api.token'
    _description = 'Employee API Session Token'
    _order = 'created_at desc'
    _rec_name = 'employee_id'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    token = fields.Char(
        string='Token',
        size=128,
        required=True,
        copy=False,
        index=True,
    )
    device_info = fields.Char(
        string='Device',
        size=256,
        help='Device model and OS sent by mobile app at login',
    )
    expires_at = fields.Datetime(
        string='Expires At',
        required=True,
    )
    is_active = fields.Boolean(
        string='Active',
        default=True,
        index=True,
    )
    last_used_at = fields.Datetime(
        string='Last Used',
        default=fields.Datetime.now,
    )
    created_at = fields.Datetime(
        string='Created',
        default=fields.Datetime.now,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # SQL Constraints
    # -------------------------------------------------------------------------

    _sql_constraints = [
        (
            'token_unique',
            'UNIQUE(token)',
            'API token must be unique.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Database Indexes
    # -------------------------------------------------------------------------

    def init(self):
        """Create composite index on (token, is_active) for O(1) lookup.

        Every API call hits this pair — the index is critical for performance
        under load. A sequential scan on a growing token table would degrade
        every endpoint's response time linearly.
        """
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_api_token_lookup
            ON employee_api_token (token, is_active)
            WHERE is_active = TRUE
        """)

    # -------------------------------------------------------------------------
    # CRUD Overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Set expiry on creation if not explicitly provided."""
        now = fields.Datetime.now()
        for vals in vals_list:
            if not vals.get('expires_at'):
                vals['expires_at'] = now + timedelta(days=TOKEN_EXPIRY_DAYS)
            if not vals.get('created_at'):
                vals['created_at'] = now
            if not vals.get('last_used_at'):
                vals['last_used_at'] = now
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Token Lifecycle
    # -------------------------------------------------------------------------

    def revoke(self):
        """Deactivate this token immediately. Used for logout and HR revocation."""
        self.write({'is_active': False})
        _logger.info(
            'Token revoked for employee %s (token_id=%s)',
            self.employee_id.name, self.id,
        )

    def touch(self):
        """Update last_used_at. Called by token_helper on every validated request.

        Uses a raw SQL write to avoid triggering ORM write hooks, computed fields,
        or record rules — this runs on every single API call so it must be fast.
        """
        self.env.cr.execute(
            "UPDATE employee_api_token SET last_used_at = %s WHERE id = %s",
            (fields.Datetime.now(), self.id),
        )

    # -------------------------------------------------------------------------
    # Scheduled Cleanup
    # -------------------------------------------------------------------------

    @api.model
    def _cron_gc_expired_tokens(self):
        """Daily cron: expire overdue tokens and purge old revoked ones.

        Two-phase cleanup:
        1. Deactivate tokens past their expires_at (session expired naturally)
        2. Delete tokens that have been inactive for STALE_TOKEN_CLEANUP_DAYS
           (no reason to keep revoked/expired rows forever)
        """
        now = fields.Datetime.now()
        cutoff = now - timedelta(days=STALE_TOKEN_CLEANUP_DAYS)

        # Phase 1: deactivate expired but still marked active
        expired = self.sudo().search([
            ('is_active', '=', True),
            ('expires_at', '<', now),
        ])
        if expired:
            expired.write({'is_active': False})
            _logger.info('Deactivated %d expired API tokens.', len(expired))

        # Phase 2: purge long-dead tokens
        stale = self.sudo().search([
            ('is_active', '=', False),
            ('last_used_at', '<', cutoff),
        ])
        if stale:
            count = len(stale)
            stale.unlink()
            _logger.info('Purged %d stale API tokens.', count)

    # -------------------------------------------------------------------------
    # Admin Helpers
    # -------------------------------------------------------------------------

    def action_revoke_all_for_employee(self):
        """HR action: revoke every active token for this token's employee.
        
        Used when an employee leaves the company or loses their device.
        """
        tokens = self.sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('is_active', '=', True),
        ])
        tokens.write({'is_active': False})
        _logger.info(
            'Revoked %d tokens for employee %s (triggered by admin)',
            len(tokens), self.employee_id.name,
        )
        return True
