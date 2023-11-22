# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from dateutil.relativedelta import relativedelta
from datetime import datetime
from itertools import groupby
from odoo.tools import float_compare

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.addons.stock.models.stock_rule import ProcurementException


class StockRule(models.Model):
    _inherit = 'stock.rule'

    group_propagation_option = fields.Selection(selection_add=[('group', 'Group')], ondelete={'group': 'set default'})

    def _get_custom_move_fields(self):
        fields = super(StockRule, self)._get_custom_move_fields()
        fields += ['picking_type_id']
        return fields

    @api.model
    def _run_buy(self, procurements):
        procurements_by_po_domain = defaultdict(list)
        errors = []
        for procurement, rule in procurements:
            # Get the schedule date in order to find a valid seller
            procurement_date_planned = fields.Datetime.from_string(procurement.values['date_planned'])

            supplier = False
            if procurement.values.get('supplierinfo_id'):
                supplier = procurement.values['supplierinfo_id']
            elif procurement.values.get('orderpoint_id') and procurement.values['orderpoint_id'].supplier_id:
                supplier = procurement.values['orderpoint_id'].supplier_id
            else:
                supplier = procurement.product_id.with_company(procurement.company_id.id)._select_seller(
                    partner_id=procurement.values.get("supplierinfo_name"),
                    quantity=procurement.product_qty,
                    date=procurement_date_planned.date(),
                    uom_id=procurement.product_uom)

            # Fall back on a supplier for which no price may be defined. Not ideal, but better than
            # blocking the user.
            supplier = supplier or procurement.product_id._prepare_sellers(False).filtered(
                lambda s: not s.company_id or s.company_id == procurement.company_id
            )[:1]

            if not supplier:
                msg = _(
                    'There is no matching vendor price to generate the purchase order for product %s (no vendor defined, minimum quantity not reached, dates not valid, ...). Go on the product form and complete the list of vendors.') % (
                          procurement.product_id.display_name)
                errors.append((procurement, msg))

            partner = supplier.name
            # we put `supplier_info` in values for extensibility purposes
            procurement.values['supplier'] = supplier
            procurement.values['propagate_cancel'] = rule.propagate_cancel

            domain = rule._make_po_get_domain(procurement.company_id, procurement.values, partner)
            procurements_by_po_domain[domain].append((procurement, rule))

        if errors:
            raise ProcurementException(errors)

        for domain, procurements_rules in procurements_by_po_domain.items():
            # Get the procurements for the current domain.
            # Get the rules for the current domain. Their only use is to create
            # the PO if it does not exist.
            procurements, rules = zip(*procurements_rules)

            # Get the set of procurement origin for the current domain.
            origins = set([p.origin for p in procurements])
            # Check if a PO exists for the current domain.
            po = self.env['purchase.order'].sudo().search([dom for dom in domain], limit=1)
            company_id = procurements[0].company_id
            if not po:
                positive_values = [p.values for p in procurements if
                                   float_compare(p.product_qty, 0.0, precision_rounding=p.product_uom.rounding) >= 0]
                if positive_values:
                    # We need a rule to generate the PO. However the rule generated
                    # the same domain for PO and the _prepare_purchase_order method
                    # should only uses the common rules's fields.
                    vals = rules[0]._prepare_purchase_order(company_id, origins, positive_values)
                    # The company_id is the same for all procurements since
                    # _make_po_get_domain add the company in the domain.
                    # We use SUPERUSER_ID since we don't want the current user to be follower of the PO.
                    # Indeed, the current user may be a user without access to Purchase, or even be a portal user.
                    po = self.env['purchase.order'].with_company(company_id).with_user(SUPERUSER_ID).create(vals)
            else:
                # If a purchase order is found, adapt its `origin` field.
                if po.origin:
                    missing_origins = origins - set(po.origin.split(', '))
                    if missing_origins:
                        po.write({'origin': po.origin + ', ' + ', '.join(missing_origins)})
                else:
                    po.write({'origin': ', '.join(origins)})

            procurements_to_merge = self._get_procurements_to_merge(procurements)
            procurements = self._merge_procurements(procurements_to_merge)

            po_lines_by_product = {}
            grouped_po_lines = groupby(
                po.order_line.filtered(lambda l: not l.display_type and l.product_uom == l.product_id.uom_po_id).sorted(
                    lambda l: l.product_id.id), key=lambda l: l.product_id.id)
            for product, po_lines in grouped_po_lines:
                po_lines_by_product[product] = self.env['purchase.order.line'].concat(*list(po_lines))
            po_line_values = []
            for procurement in procurements:
                po_lines = po_lines_by_product.get(procurement.product_id.id, self.env['purchase.order.line'])
                po_line = po_lines._find_candidate(*procurement)

                if po_line:
                    # If the procurement can be merge in an existing line. Directly
                    # write the new values on it.
                    vals = self._update_purchase_order_line(procurement.product_id,
                                                            procurement.product_qty, procurement.product_uom,
                                                            company_id,
                                                            procurement.values, po_line)
                    po_line.sudo().write(vals)
                else:
                    if float_compare(procurement.product_qty, 0,
                                     precision_rounding=procurement.product_uom.rounding) <= 0:
                        # If procurement contains negative quantity, don't create a new line that would contain negative qty
                        continue
                    # If it does not exist a PO line for current procurement.
                    # Generate the create values for it and add it to a list in
                    # order to create it in batch.
                    partner = procurement.values['supplier'].name
                    po_line_values.append(self.env['purchase.order.line']._prepare_purchase_order_line_from_procurement(
                        procurement.product_id, procurement.product_qty,
                        procurement.product_uom, procurement.company_id,
                        procurement.values, po))
                    # Check if we need to advance the order date for the new line
                    order_date_planned = procurement.values['date_planned'] - relativedelta(
                        days=procurement.values['supplier'].delay)
                    if fields.Date.to_date(order_date_planned) < fields.Date.to_date(po.date_order):
                        po.date_order = order_date_planned
            self.env['purchase.order.line'].sudo().create(po_line_values)

    def _get_lead_days(self, product, **values):
        """Add the company security lead time, days to purchase and the supplier
        delay to the cumulative delay and cumulative description. The days to
        purchase and company lead time are always displayed for onboarding
        purpose in order to indicate that those options are available.
        """
        delay, delay_description = super()._get_lead_days(product, **values)
        bypass_delay_description = self.env.context.get('bypass_delay_description')
        pickup_delay = 0
        buy_rule = self.filtered(lambda r: r.action == 'buy')
        seller = 'supplierinfo' in values and values['supplierinfo'] or product.with_company(
            buy_rule.company_id)._select_seller(quantity=None)
        if not buy_rule or not seller:
            return delay, delay_description
        buy_rule.ensure_one()
        supplier_delay = seller[0].delay
        security_delay = buy_rule.picking_type_id.company_id.po_lead
        days_to_purchase = buy_rule.company_id.days_to_purchase
        initial_delay = delay + supplier_delay + security_delay + days_to_purchase

        # Check if days on the seller is set
        if seller.name.mon or seller.name.tue or seller.name.wed or seller.name.thu or seller.name.fri or seller.name.sat or seller.name.sun:
            if 'picking' in values and values['picking'].scheduled_date:
                pickup_delay = self._get_close_pickup_date(values['picking'].scheduled_date, seller, initial_delay)
                delay_description.append((_('Pickup Date'), _('+ %d day(s)', pickup_delay)))
                return pickup_delay, delay_description
            else:
                pickup_delay = self._get_next_pickup_date(seller, initial_delay)
                delay_description.append((_('Pickup Date'), _('+ %d day(s)', pickup_delay)))
                return pickup_delay, delay_description
        return initial_delay, delay_description

    def _get_close_pickup_date(self, date_scheduled, seller, initial_delay):

        initial_date_delay = fields.Date.today() + relativedelta(days=initial_delay)

        date_scheduled = date_scheduled.date()
        day_of_week = date_scheduled.weekday()
        days = [seller.name.mon, seller.name.tue, seller.name.wed, seller.name.thu, seller.name.fri, seller.name.sat,
                seller.name.sun]

        if days[day_of_week]:
            return initial_delay + (date_scheduled - initial_date_delay).days
        else:
            for i in range(1, 7):
                if days[(day_of_week - i) % 7]:
                    return initial_delay + ((date_scheduled - relativedelta(days=i)) - initial_date_delay).days

    def _get_next_pickup_date(self, seller, initial_delay):
        today = fields.Date.today() + relativedelta(days=initial_delay)
        day_of_week = today.weekday()
        days = [seller.name.mon, seller.name.tue, seller.name.wed, seller.name.thu, seller.name.fri, seller.name.sat,
                seller.name.sun]

        if days[day_of_week]:
            return initial_delay
        else:
            for i in range(1, 7):
                if days[(day_of_week + i) % 7]:
                    return initial_delay + ((today + relativedelta(days=i)) - today).days

    def _make_po_get_domain(self, company_id, values, partner):
        gpo = self.group_propagation_option
        group = (gpo == 'fixed' and self.group_id) or \
                (gpo == 'propagate' and 'group_id' in values and values['group_id']) or False

        domain = (
            ('partner_id', '=', partner.id),
            ('state', '=', 'draft'),
            ('picking_type_id', '=', self.picking_type_id.id),
            ('company_id', '=', company_id.id),
            ('user_id', '=', False),
        )

        if gpo == 'group':
            domain += ('date_planned', '=', values['date_planned']),

        delta_days = self.env['ir.config_parameter'].sudo().get_param('purchase_stock.delta_days_merge')
        if values.get('orderpoint_id') and delta_days is not False:
            procurement_date = fields.Date.to_date(values['date_planned']) - relativedelta(
                days=int(values['supplier'].delay))
            delta_days = int(delta_days)
            domain += (
                ('date_order', '<=',
                 datetime.combine(procurement_date + relativedelta(days=delta_days), datetime.max.time())),
                ('date_order', '>=',
                 datetime.combine(procurement_date - relativedelta(days=delta_days), datetime.min.time()))
            )
        if group:
            domain += (('group_id', '=', group.id),)
        return domain
