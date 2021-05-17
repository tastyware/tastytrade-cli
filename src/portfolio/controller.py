from cement import Controller


class PortfolioController(Controller):
    class Meta:
        label = 'portfolio'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'view statistics and risk metrics for your portfolio'

    def _default(self):
        """Default action if no sub-command is passed."""
        self._show_stats()

    def _show_stats(self):
        print('stats galore!')
