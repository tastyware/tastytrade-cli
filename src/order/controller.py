from cement import Controller


class OrderController(Controller):
    class Meta:
        label = 'order'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'view, replace, and cancel orders'

    def _default(self):
        """Default action if no sub-command is passed."""
        self._list_orders()

    def _list_orders(self):
        print('look at all these orders!')
