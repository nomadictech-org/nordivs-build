# -*- coding: utf-8 -*-
{
    'name': 'Own Brand',
    'version': '18.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Enterprise-style App Dashboard (Home Menu) for Odoo 18 Community',
    'description': """
Own Brand
=========
Reproduces the Enterprise "app dashboard" (Home Menu app grid) in Odoo 18
Community Edition, fully independent of the proprietary `web_enterprise`
module.

Features
--------
* Custom web client that lands on a searchable, draggable app grid.
* Navbar with a Home / Back toggle button.
* Per-user persistence of the app ordering (homemenu_config).
* Custom backend styling (iOS-style messaging cards, dark dashboard).

This module depends only on community addons (base, web, mail, crm).
    """,
    'author': 'NomadicTech',
    'website': 'https://nordivs.com',
    'license': 'LGPL-3',

    # Independent: community addons only. NOT web_enterprise.
    'depends': [
        'base',
        'web',
        'mail',  # provides res.users.settings + chatter/mail templates
        'crm',
    ],

     'data': [
        'views/res_company_view.xml',
    ],

    'assets': {
        # Replace the community webclient entry point so OUR web client boots.
        'web.assets_web': [
            ('replace', 'web/static/src/main.js', 'own_brand/static/src/main.js'),
        ],

        'web.assets_backend': [
            # --- Styles ---
            'own_brand/static/src/scss/search_panel_style.scss',
            'own_brand/static/src/scss/panel_design_style.scss',
            'own_brand/static/src/webclient/navbar/navbar.scss',
            'own_brand/static/src/webclient/home_menu/home_menu.scss',

            # --- JavaScript (load services before components that use them) ---
            'own_brand/static/src/webclient/background/ownbrand_background_service.js',
            'own_brand/static/src/webclient/home_menu/home_menu_service.js',
            'own_brand/static/src/webclient/home_menu/home_menu.js',
            'own_brand/static/src/webclient/navbar/navbar.js',
            'own_brand/static/src/webclient/webclient.js',

            # --- QWeb templates for the OWL components ---
            'own_brand/static/src/webclient/home_menu/home_menu.xml',
            'own_brand/static/src/webclient/navbar/navbar.xml',
        ],

        'web.assets_frontend': [],
    },

    'installable': True,
    'application': True,
}
