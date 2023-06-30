# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class WebsiteWithdrawalSaleOrder(models.Model):
    _inherit = 'sale.order'

    picking_type_id = fields.Many2one('stock.picking.type', 'Operation Type', default=lambda self: self.env['stock.picking.type'].search([('code', '=', 'outgoing')], limit=1), required=True)

    withdrawal_point_id = fields.Many2one('delivery.withdrawal.point', string='Withdrawal Point', help="Withdrawal Point")

    commitment_date_end = fields.Datetime(string='Commitment Date End', readonly=False, index=True, copy=False)

    def write(self, values):
        print("values write ", values)
        res = super(WebsiteWithdrawalSaleOrder, self).write(values)
        if values.get('picking_type_id'):
            self.order_line.move_ids.picking_type_id = values.get('picking_type_id')
        # if values.get('commitment_date_end'):
        #     self.commitment_date_end = values.get('commitment_date_end')
        # if values.get('withdrawal_point_id'):
        #     self.withdrawal_point_id = values.get('withdrawal_point_id')
        print("res write ", res)
        return res


class WebsiteWithdrawalSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, group_id=False):
        res = super(WebsiteWithdrawalSaleOrderLine, self)._prepare_procurement_values(group_id)
        res['picking_type_id'] = self.order_id.picking_type_id.id
        return res