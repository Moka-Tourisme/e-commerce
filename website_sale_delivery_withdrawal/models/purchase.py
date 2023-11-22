# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import traceback
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from functools import partial
from itertools import groupby
import json

from markupsafe import escape, Markup
from pytz import timezone, UTC
from werkzeug.urls import url_encode

from odoo import api, fields, models, _
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, get_lang, format_amount


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"
    _description = "Purchase Order"
    _order = 'priority desc, id desc'

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            print("values ", values)
            if values.get('display_type', self.default_get(['display_type'])['display_type']):
                values.update(product_id=False, price_unit=0, product_uom_qty=0, product_uom=False, date_planned=False)
            else:
                values.update(self._prepare_add_missing_fields(values))
        lines = super().create(vals_list)
        for line in lines:
            if line.product_id and line.order_id.state == 'purchase':
                msg = _("Extra line with %s ") % (line.product_id.display_name,)
                line.order_id.message_post(body=msg)
        return lines

    def write(self, values):
        if 'display_type' in values and self.filtered(lambda line: line.display_type != values.get('display_type')):
            raise UserError(
                _("You cannot change the type of a purchase order line. Instead you should delete the current line and create a new line of the proper type."))

        if 'product_qty' in values:
            for line in self:
                if line.order_id.state == 'purchase':
                    line.order_id.message_post_with_view('purchase.track_po_line_template',
                                                         values={'line': line, 'product_qty': values['product_qty']},
                                                         subtype_id=self.env.ref('mail.mt_note').id)
        if 'qty_received' in values:
            for line in self:
                line._track_qty_received(values['qty_received'])
        return super(PurchaseOrderLine, self).write(values)

    @api.model
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom, company_id, supplier, po):
        partner = supplier.name
        uom_po_qty = product_uom._compute_quantity(product_qty, product_id.uom_po_id)
        # _select_seller is used if the supplier have different price depending
        # the quantities ordered.
        seller = product_id.with_company(company_id)._select_seller(
            partner_id=partner,
            quantity=uom_po_qty,
            date=po.date_order and po.date_order.date(),
            uom_id=product_id.uom_po_id)

        product_taxes = product_id.supplier_taxes_id.filtered(lambda x: x.company_id.id == company_id.id)
        taxes = po.fiscal_position_id.map_tax(product_taxes)

        price_unit = self.env['account.tax']._fix_tax_included_price_company(
            seller.price, product_taxes, taxes, company_id) if seller else 0.0
        if price_unit and seller and po.currency_id and seller.currency_id != po.currency_id:
            price_unit = seller.currency_id._convert(
                price_unit, po.currency_id, po.company_id, po.date_order or fields.Date.today())

        product_lang = product_id.with_prefetch().with_context(
            lang=partner.lang,
            partner_id=partner.id,
        )
        name = product_lang.with_context(seller_id=seller.id).display_name
        if product_lang.description_purchase:
            name += '\n' + product_lang.description_purchase

        date_planned = self.order_id.date_planned or self._get_date_planned(seller, po=po)
        vals_return = {
            'name': name,
            'product_qty': uom_po_qty,
            'product_id': product_id.id,
            'product_uom': product_id.uom_po_id.id,
            'price_unit': price_unit,
            'date_planned': date_planned,
            'taxes_id': [(6, 0, taxes.ids)],
            'order_id': po.id,
        }

        return vals_return

    def write(self, values):
        if values.get('date_planned'):
            new_date = fields.Datetime.to_datetime(values['date_planned'])
            self.filtered(lambda l: not l.display_type)._update_move_date_deadline(new_date)
        lines = self.filtered(lambda l: l.order_id.state == 'purchase')
        previous_product_qty = {line.id: line.product_uom_qty for line in lines}
        result = super(PurchaseOrderLine, self).write(values)
        if 'price_unit' in values:
            for line in lines:
                # Avoid updating kit components' stock.move
                moves = line.move_ids.filtered(
                    lambda s: s.state not in ('cancel', 'done') and s.product_id == line.product_id)
                moves.write({'price_unit': line.price_unit})
        if 'product_qty' in values:
            lines.with_context(previous_product_qty=previous_product_qty)._create_or_update_picking()
        return result



    @api.model
    def _get_date_planned(self, seller, po=False):
        """Return the datetime value to use as Schedule Date (``date_planned``) for
           PO Lines that correspond to the given product.seller_ids,
           when ordered at `date_order_str`.

           :param Model seller: used to fetch the delivery delay (if no seller
                                is provided, the delay is 0)
           :param Model po: purchase.order, necessary only if the PO line is
                            not yet attached to a PO.
           :rtype: datetime
           :return: desired Schedule Date for the PO line
        """
        date_order = po.date_order if po else self.order_id.date_order
        if date_order:
            if seller:
                return self._get_next_pickup_date(seller, date_planned=date_order + relativedelta(days=seller.delay))
            else:
                return date_order
        else:
            if seller:
                return self._get_next_pickup_date(seller, date_planned=datetime.today() + relativedelta(days=seller.delay))
            else:
                return datetime.today()

    def _get_next_pickup_date(self, seller, date_planned):
        today = date_planned
        day_of_week = today.weekday()
        days = [seller.name.mon, seller.name.tue, seller.name.wed, seller.name.thu, seller.name.fri, seller.name.sat,
                seller.name.sun]

        if days[day_of_week]:
            return today
        else:
            for i in range(1, 7):
                if days[(day_of_week + i) % 7]:
                    return today + relativedelta(days=i)
