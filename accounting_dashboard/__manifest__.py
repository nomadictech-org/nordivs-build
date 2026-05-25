# -*- coding: utf-8 -*-
{
    'name': 'Accounting Dashboard',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Modern Accounting Dashboard with KPIs, charts and expense tracking',
    'description': """
Accounting Dashboard
====================
A modern, interactive Accounting Dashboard for Odoo 18 featuring:
    * KPI cards (Cash in Bank, Accounts Receivable, Revenue, Expenses, Net Total)
    * Revenue & Expense summary tables
    * Revenue Trend (line chart) & Expense Trend (bar chart)
    * Net Summary with donut/margin chart
    * Recent Expense Entries
    * Multi-company, period filter
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/expense_entry_views.xml',
        'views/dashboard_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'accounting_dashboard/static/src/scss/dashboard.scss',
            'accounting_dashboard/static/src/js/dashboard.js',
            'accounting_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
