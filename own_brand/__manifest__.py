# -*- coding: utf-8 -*-
{
    'name': 'NomadicTech Own Brand',
    'version': '18.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Modern Odoo 18 Branding for NovaOS and Dubak Projects',
    'author': 'NomadicTech',
    'website': 'https://nomadictech.com',  # Example website
    'license': 'LGPL-3',
    'depends': [
        'web',
        'mail',  # Required for the unified <chatter/> and mail templates
    ],
    'data': [
        'views/res_company_view.xml',
        'views/mail_template_update.xml',
        # Note: ui_theme.xml and own_brand_view.xml must use <list> instead of <tree>
    ],
    'assets': {
        'web.assets_backend': [
            'own_brand/static/src/scss/appbar.scss',
            'own_brand/static/src/scss/menu_item.scss',
            "own_brand/static/src/scss/button_style.scss",
            'own_brand/static/src/scss/files_attached.scss',
            'own_brand/static/src/scss/ios_cards.scss',
            'own_brand/static/src/scss/ios_kanban.scss',
            'own_brand/static/src/scss/layout_colors.scss',
            'own_brand/static/src/scss/modal.scss',
            'own_brand/static/src/scss/status_bar.scss',
            'own_brand/static/src/scss/tabs.scss',
        ],
        'web.assets_frontend': [
            # Login styles belong in the frontend bundle
            # 'own_brand/static/src/scss/login.scss',
        ],
    },
    'installable': True,
    'application': True,  # Set to True if this is the primary "NovaOS" entry point
}