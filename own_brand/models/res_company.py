from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    brand_label = fields.Char(
        string="Own Label",
    )

    brand_logo = fields.Image(
        string="Brand Logo"
    )

    brand_favicon = fields.Image(  # renamed from favicon → brand_favicon
        string="Favicon",
        max_width=64,
        max_height=64
    )

    favicon = fields.Image(  # renamed from favicon → brand_favicon
        string="Favicon",
        max_width=64,
        max_height=64
    )

    ui_accent_color = fields.Char(
        string="UI Accent Color",
        default="#22c55e"
    )