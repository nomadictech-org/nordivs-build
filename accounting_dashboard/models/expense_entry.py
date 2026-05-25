# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ExpenseEntry(models.Model):
    """Manual / Google-Sheet expense entries shown on the dashboard.

    Used when the user wants to log expense lines that don't come from
    Odoo's standard accounting entries (e.g. team logs them from a Google
    Sheet). Standard expenses are aggregated from account.move directly.
    """
    _name = 'accounting.dashboard.expense'
    _description = 'Dashboard Expense Entry'
    _order = 'date desc, id desc'

    name = fields.Char(string='Description', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    category = fields.Selection(
        selection=[
            ('marketing', 'Marketing Expenses'),
            ('office', 'Office Expenses'),
            ('travel', 'Travel Expenses'),
            ('logistics', 'Logistics Expenses'),
            ('other', 'Other Expenses'),
        ],
        string='Category',
        required=True,
        default='other',
    )
    region = fields.Selection(
        selection=[
            ('north_america', 'North America'),
            ('asia', 'Asia'),
            ('europe', 'Europe'),
            ('south_america', 'South America'),
            ('africa', 'Africa'),
            ('oceania', 'Oceania'),
        ],
        string='Region',
        required=True,
        default='north_america',
    )
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    source = fields.Selection(
        selection=[
            ('manual', 'Manual Entry'),
            ('google_sheet', 'Google Sheet'),
            ('odoo', 'Auto from Odoo'),
        ],
        string='Source',
        required=True,
        default='manual',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    notes = fields.Text(string='Notes')
