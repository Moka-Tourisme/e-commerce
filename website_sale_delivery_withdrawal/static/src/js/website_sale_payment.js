odoo.define('website_sale_delivery_withdrawal.checkout', function (require) {
    'use strict';

    var core = require('web.core');
    var publicWidget = require('web.public.widget');

    var _t = core._t;

    publicWidget.registry.websiteSaleDeliveryWithdrawal = publicWidget.Widget.extend({
        selector: '.oe_website_sale',
        events: {
            'click #btn_confirm_withdrawal_point ': '_onDeliveryWithdrawalClick',
        },
        
        /**
         * @override
         */
        start: function () {
            setTimeout(() => {
                this.$carriers = $('#delivery_carrier input[name="delivery_type"]');
                this.$withdrawal = $('#btn_confirm_withdrawal_point');
                this.$withdrawal.on("click", () => {
                    // Your code to be executed when the element is clicked
                    this._onDeliveryWithdrawalClick();
                });
                this.$payButton = $('button[name="o_payment_submit_button"]');
                if (this.$withdrawal.length > 0) {
                    this.$payButton.prop('disabled', true);
                    this.$disabledReasons = this.$payButton.data('disabled_reasons') || {};
                    this.$disabledReasons.withdrawal_selection = true;
                    this.$payButton.data('disabled_reasons', this.$disabledReasons);
                }
            }, 100);
            return this._super.apply(this, arguments);
        },

        _onDeliveryWithdrawalClick: function (ev) {
            if (this.$withdrawal.data('withdrawal_point_id')) {
                this.$disabledReasons.withdrawal_selection = false;
                this.$payButton.data('disabled_reasons', this.$disabledReasons);
                this.$payButton.prop('disabled', _.contains(this.$payButton.data('disabled_reasons'), true));
            }
        }
    });
});
