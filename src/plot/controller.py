from cement import Controller


class PlotController(Controller):
    class Meta:
        label = 'plot'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'chart your portfolio\'s net liquidity or profit/loss over time'

    def _default(self):
        """Default action if no sub-command is passed."""
        self._show_stats()

    def _show_stats(self):
        print('stats galore!')
