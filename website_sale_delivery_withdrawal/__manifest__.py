# -*- coding: utf-8 -*-
{
    'name': "website_sale_delivery_withdrawal",
    'summary': """ Let's choose withdrawal point on your ecommerce """,

    'description': """
        This module allow your customer to choose a Withdrawal Point and use it as shipping address.
    """,
    'category': 'Website/Website',
    'version': '15.0.0.1.0',
    'depends': ['website_sale_delivery', 'delivery_withdrawal_method', 'purchase', 'purchase_stock', 'stock', 'sale'],
    'data': [
        'report/sale_report_templates.xml',
        'report/sale_report.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/website_sale.xml',
        'data/stock_rule.xml',
        'data/mail_template_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_delivery_withdrawal/static/src/js/website_sale_delivery_withdrawal.js',
            'website_sale_delivery_withdrawal/static/src/css/website_sale_delivery_withdrawal.css'
        ],
    },
    'license': 'AGPL-3',
    'auto_install': True,
}
