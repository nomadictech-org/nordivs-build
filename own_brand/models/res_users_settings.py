# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsersSettings(models.Model):
    """Add the home menu configuration field so users can persist their
    custom app ordering on the home menu (app grid). This mirrors the field
    added by web_enterprise, but is provided here so the module stays
    independent of web_enterprise.

    `res.users.settings` is provided by the `mail` addon, which is already
    a dependency of this module.
    """
    _inherit = 'res.users.settings'

    homemenu_config = fields.Json(string="Home Menu Configuration", readonly=True)
