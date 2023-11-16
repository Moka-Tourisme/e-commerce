# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.onchange('route_ids')
    def _create_replanishment_route(self):
        print("ICI MODIFICATION ROUTE")
          # Check route_ids to see if it contains the route with rule_ids.group_propagation_option == 'group' and it wasn't there before
        if self.route_ids.filtered(lambda route: route.rule_ids.filtered(lambda rule: rule.group_propagation_option == 'group')) and not self._origin.route_ids.filtered(lambda route: route.rule_ids.filtered(lambda rule: rule.group_propagation_option == 'group')):
            print("MODIFICATION ROUTE")
            print("oui")