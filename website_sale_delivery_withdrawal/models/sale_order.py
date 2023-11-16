# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class WebsiteWithdrawalSaleOrder(models.Model):
    _inherit = 'sale.order'

    picking_type_id = fields.Many2one('stock.picking.type', 'Operation Type', default=lambda self: self.env['stock.picking.type'].search([('code', '=',
                                                                                                                                           'outgoing')], limit=1), required=True)

    is_withdrawal = fields.Boolean(string='Is Withdrawal Point', compute='_compute_is_withdrawal_point')

    withdrawal_point_id = fields.Many2one('delivery.withdrawal.point', string='Withdrawal Point', help="Withdrawal Point")

    commitment_hour_from = fields.Char(string='Commitment hour from', readonly=False, index=True, copy=False)

    commitment_hour_to = fields.Char(string='Commitment hour to', readonly=False, index=True, copy=False)

    def write(self, values):
        res = super(WebsiteWithdrawalSaleOrder, self).write(values)
        if values.get('picking_type_id'):
            self.order_line.move_ids.picking_type_id = values.get('picking_type_id')
        return res

    @api.depends('carrier_id.is_withdrawal_point')
    def _compute_is_withdrawal_point(self):
        for order in self:
            order.is_withdrawal = order.carrier_id.is_withdrawal_point if order.carrier_id else False

    def _find_mail_template(self, force_confirmation_template=False):
        self.ensure_one()
        template_id = False
        print("PASSAGE ICI")
        print("self ", self)
        print("self.state ", self.state)
        print("self.env.context.get('proforma', False) ", self.env.context.get('proforma', False))
        print("self.is_withdrawal ", self.is_withdrawal)
        if force_confirmation_template or (self.state == 'sale' and not self.env.context.get('proforma', False)):
            if not self.is_withdrawal:
                template_id = int(self.env['ir.config_parameter'].sudo().get_param('sale.default_confirmation_template'))
                template_id = self.env['mail.template'].search([('id', '=', template_id)]).id
                if not template_id:
                    template_id = self.env['ir.model.data']._xmlid_to_res_id('sale.mail_template_sale_confirmation',
                                                                             raise_if_not_found=False)
            else:
                template_id = self.env['ir.model.data']._xmlid_to_res_id('website_sale_delivery_withdrawal.mail_template_sale_confirmation_withdrawal',
                                                                         raise_if_not_found=False)
                print("template_id 4", template_id)
        if not template_id:
            template_id = self.env['ir.model.data']._xmlid_to_res_id('sale.email_template_edi_sale',
                                                                     raise_if_not_found=False)

        return template_id


class WebsiteWithdrawalSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, group_id=False):
        res = super(WebsiteWithdrawalSaleOrderLine, self)._prepare_procurement_values(group_id)
        res['picking_type_id'] = self.order_id.picking_type_id.id
        return res
