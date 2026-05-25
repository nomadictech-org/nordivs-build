# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class AccountingDashboardController(http.Controller):
    """JSON endpoint for the dashboard. The OWL component primarily uses
    `orm.call('accounting.dashboard', 'get_dashboard_data', [period])`, but
    this endpoint is here if a REST consumer ever wants the data too.
    """

    @http.route('/accounting_dashboard/data', type='json', auth='user')
    def get_data(self, period='this_month', company_id=None):
        return request.env['accounting.dashboard'].get_dashboard_data(
            period=period, company_id=company_id,
        )
