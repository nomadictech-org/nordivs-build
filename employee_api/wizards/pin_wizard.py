# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmployeeApiPinWizard(models.TransientModel):
    _name = 'employee.api.pin.wizard'
    _description = 'Set Employee Mobile PIN'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        readonly=True,
    )
    new_pin = fields.Char(
        string='New PIN',
        required=True,
        help='4 to 8 digits. Will be hashed immediately — '
             'the plaintext is never stored.',
    )
    confirm_pin = fields.Char(
        string='Confirm PIN',
        required=True,
    )
    auto_enable = fields.Boolean(
        string='Enable app access',
        default=True,
        help='Automatically set "Mobile App Access" to ON after setting the PIN.',
    )

    def action_set_pin(self):
        """Validate and set the PIN."""
        self.ensure_one()

        if self.new_pin != self.confirm_pin:
            raise ValidationError('PINs do not match.')

        self.employee_id.set_api_pin(self.new_pin)

        if self.auto_enable and not self.employee_id.api_enabled:
            self.employee_id.api_enabled = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'PIN Set',
                'message': f'Mobile PIN has been set for {self.employee_id.name}.',
                'type': 'success',
                'sticky': False,
            },
        }
