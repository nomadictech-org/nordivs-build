# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Expose the current company's dashboard background configuration to
        the web client so the home menu can render a per-company background.

        We always provide a ready-to-use CSS `background-image` value:
          - image:    url(...)
          - gradient: linear-gradient(...)
          - solid:    a flat color expressed as a (degenerate) linear-gradient
                      so a single CSS property covers every case.
        """
        result = super().session_info()
        company = self.env.company
        bg_type = company.ownbrand_bg_type or 'gradient'
        c1 = company.ownbrand_bg_color_1 or '#0c1f33'
        c2 = company.ownbrand_bg_color_2 or '#000511'
        angle = company.ownbrand_bg_angle or 135

        if bg_type == 'image' and company.ownbrand_bg_image:
            image_url = (
                "/web/image?model=res.company&id=%s&field=ownbrand_bg_image"
                % company.id
            )
            css_bg_image = "url('%s')" % image_url
        elif bg_type == 'solid':
            # A single-color "gradient" renders as a flat fill.
            css_bg_image = "linear-gradient(%s, %s)" % (c1, c1)
        else:  # gradient (default)
            css_bg_image = (
                "linear-gradient(%sdeg, %s 0%%, %s 100%%)" % (angle, c1, c2)
            )

        result['ownbrand_background'] = {
            'type': bg_type,
            'css_bg_image': css_bg_image,
        }
        return result