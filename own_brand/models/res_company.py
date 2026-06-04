# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # --- Home menu (dashboard) background configuration ---------------------
    ownbrand_bg_type = fields.Selection(
        selection=[
            ('gradient', 'Gradient'),
            ('solid', 'Solid Color'),
            ('image', 'Image'),
        ],
        string="Dashboard Background Type",
        default='gradient',
    )
    ownbrand_bg_color_1 = fields.Char(
        string="Color 1",
        default='#0c1f33',
        help="Gradient first color, or the solid background color.",
    )
    ownbrand_bg_color_2 = fields.Char(
        string="Gradient Color 2",
        default='#000511',
        help="Second color of the dashboard background gradient.",
    )
    ownbrand_bg_angle = fields.Integer(
        string="Gradient Angle",
        default=135,
        help="Angle of the gradient in degrees (0-360).",
    )
    ownbrand_bg_image = fields.Binary(
        string="Dashboard Background Image",
        help="Custom image used as the dashboard background. "
             "Used when Background Type is 'Image'.",
    )

    report_header_image = fields.Binary(
        string="Report Header Image",
        help="Image displayed at the top of every printed report (PDF) for "
             "this company. Stretches to full page width.",
    )
    report_footer_image = fields.Binary(
        string="Report Footer Image",
        help="Image displayed at the bottom of every printed report (PDF) "
             "for this company. Stretches to full page width.",
    )
    report_hide_default_header = fields.Boolean(
        string="Hide Default Report Header",
        help="When checked, the standard Odoo header (logo + company info) "
             "is hidden so only the uploaded header image is shown.",
    )
    report_hide_default_footer = fields.Boolean(
        string="Hide Default Report Footer",
        help="When checked, the standard Odoo footer (company details + "
             "page numbers) is hidden so only the uploaded footer image "
             "is shown.",
    )