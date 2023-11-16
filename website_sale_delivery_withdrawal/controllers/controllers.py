# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import http, _
from odoo.addons.website_sale.controllers.main import WebsiteSale, PaymentPortal
from odoo.addons.website_sale_delivery.controllers.main import WebsiteSaleDelivery
from odoo.exceptions import AccessDenied, ValidationError, UserError
from odoo.tools.misc import get_lang, babel_locale_parse
from odoo.http import request
from datetime import datetime
from pytz import timezone


class WithdrawalPoints(http.Controller):
    @http.route(['/website_sale_delivery_withdrawal/update_shipping'], type='json', auth="public", website=True)
    def withdrawal_update_shipping(self, **data):
        order = request.website.sale_get_order()
        tz = request.context.get('tz', 'utc') or 'utc'
        commitment_date = datetime.strptime(data['commitment_date'], "%d/%m/%Y %H:%M")
        commitment_date = pytz.timezone(tz).localize(commitment_date)
        commitment_date = commitment_date.astimezone(timezone(tz)).replace(tzinfo=None)
        print("data", data)
        order.commitment_date = commitment_date
        order.commitment_hour_from = data['hour_from']
        order.commitment_hour_to = data['hour_to']
        order.withdrawal_point_id = data['withdrawal_point_id']
        order.picking_type_id = data['picking_type_id']
        if order.partner_id == request.website.user_id.sudo().partner_id:
            raise AccessDenied('Customer of the order cannot be the public user at this step.')
        partner_shipping = order.partner_id.sudo()._withdrawal_search_or_create({
            'name': data['city'],
            'street': data['street'],
            'zip': data['zip'],
            'city': data['city'],
            'country_id': data['country'],
        })
        if order.partner_shipping_id != partner_shipping:
            order.partner_shipping_id = partner_shipping
            order.onchange_partner_shipping_id()

        values = {
            'address': request.env['ir.qweb']._render('website_sale.address_on_payment', {
                'order': order,
                'only_services': order and order.only_services,
            }),
            'new_partner_shipping_id': order.partner_shipping_id.id,
        }
        return values

    @http.route(['/website_sale_delivery_withdrawal/load_data'], type='json', auth="public", website=True)
    def load_order_data(self, **data):
        order = request.website.sale_get_order()
        print("order ", order)
        print("self ", self)
        config = order.company_id

        print("config ", config.days_to_purchase)
        order_lines = order.order_line
        new_date_planned = datetime.today()
        for order_line in order_lines:
            print("Entrée dans la boucle")
            print("order_line ", order_line)
            print("order_line.product_type ", order_line.product_type)
            print("order_line.product_id ", order_line.product_id)
            if order_line.product_type == 'product' and order_line.free_qty_today <= 0:
                product = order_line.product_id
                if not product.seller_ids:
                    raise UserError(
                        _("There is no seller for the product %s. Please add one.") % product.name)
                seller = product.seller_ids[0]
                days = [seller.name.mon, seller.name.tue, seller.name.wed, seller.name.thu, seller.name.fri,
                        seller.name.sat, seller.name.sun]
                date_planned = datetime.today() + timedelta(days=config.days_to_purchase) + timedelta(days=seller.delay)
                print("New date planned ", new_date_planned)
                print("Initial date planned ", date_planned)
                day_of_week = date_planned.weekday()
                # From date_planned we need to get the next day corresponding to the days list and the seller delay
                if days[day_of_week]:
                    print("Next day available 1", date_planned)
                    if date_planned > new_date_planned:
                        new_date_planned = date_planned
                else:
                    for i in range(1, 7):
                        print("i ", i)
                        if days[(day_of_week + i) % 7]:
                            print(days[(day_of_week + i) % 7])
                            print("Next day available 2", date_planned + relativedelta(days=i))
                            date_planned = date_planned + relativedelta(days=i)
                            if date_planned > new_date_planned:
                                new_date_planned = date_planned
                            break
        return {
            'first_pickup_date': new_date_planned
        }


class WebsiteSaleDeliveryMondialrelay(WebsiteSaleDelivery):

    def _update_website_sale_delivery_return(self, order, **post):
        res = super()._update_website_sale_delivery_return(order, **post)

        if order.carrier_id.is_withdrawal_point:
            res['withdrawal_point'] = {
                'allowed_points': order.carrier_id.withdrawal_point_ids.mapped('id'),
            }

        return res
