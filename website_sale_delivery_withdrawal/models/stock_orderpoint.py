# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from collections import defaultdict
from datetime import datetime, time
from dateutil import relativedelta
from itertools import groupby
from psycopg2 import OperationalError

from odoo import SUPERUSER_ID, _, api, fields, models, registry
from odoo.addons.stock.models.stock_rule import ProcurementException
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import add, float_compare, frozendict, split_every

_logger = logging.getLogger(__name__)


class StockWarehouseOrderpoint(models.Model):
    """ Defines Minimum stock rules. """
    _inherit = "stock.warehouse.orderpoint"

    # Create a field that create a relation between the orderpoint and delivery_carrier


    @api.depends('rule_ids', 'product_id.seller_ids', 'product_id.seller_ids.delay')
    def _compute_lead_days(self):
        # Get the last stock.picking created
        # Search for a picking with the same product in move_ids_without_package
        picking = self.env['stock.picking'].search([('move_ids_without_package.product_id', 'in', self.product_id)], order='id desc', limit=1)
        for orderpoint in self.with_context(bypass_delay_description=True):
            if not orderpoint.product_id or not orderpoint.location_id:
                orderpoint.lead_days_date = False
                continue
            values = orderpoint._get_lead_days_values()
            # Add picking to values to be able to compute the lead days
            if picking.carrier_id.withdrawal_point_ids:
                values['picking'] = picking
            lead_days, dummy = orderpoint.rule_ids._get_lead_days(orderpoint.product_id, **values)
            lead_days_date = fields.Date.today() + relativedelta.relativedelta(days=lead_days)
            orderpoint.lead_days_date = lead_days_date

    def _get_product_context(self):
        """Used to call `virtual_available` when running an orderpoint."""
        self.ensure_one()

        if self.rule_ids[0].group_propagation_option == 'group':
            return {
                'location': self.location_id.id,
                'to_date': datetime.combine(self.lead_days_date, time.max) + relativedelta.relativedelta(weeks=1)
            }
        else:
            return {
                'location': self.location_id.id,
                'to_date': datetime.combine(self.lead_days_date, time.max)
            }

