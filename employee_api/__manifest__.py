# -*- coding: utf-8 -*-
{
    'name': 'Employee Self-Service API',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'REST API for employee mobile app — zero res.users required',
    'description': """
        Provides a stateless REST API for a Flutter mobile application.
        Employees authenticate via badge ID + PIN (no Odoo user account needed).
        Supports attendance, leaves, payslips, and announcements.

        Key design:
        - All routes use auth='none' (no Odoo session)
        - Bearer token authentication via employee.api.token model
        - Every query uses sudo() with ownership domain filter
        - Security enforced in Python code, not access rules
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_attendance',
        'hr_holidays',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'wizards/pin_wizard_views.xml',
        'views/employee_api_token_views.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
