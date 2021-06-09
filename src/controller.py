import pandas as pd
from cement import Controller, ex

from .plot.base import Portfolio
from .utils import VERSION


class BaseController(Controller):
    class Meta:
        label = 'tw'

        # text displayed at the top of --help output
        description = 'An easy-to-use command line interface for Tastyworks!'

        # text displayed at the bottom of --help output
        epilog = f'tastyworks-cli {VERSION}'

        # controller level arguments. ex: 'tw --version'
        arguments = [
            # add a version banner
            (
                ['-v', '--version'],
                {
                    'action': 'version',
                    'version': VERSION
                }
            ),
        ]

    def _default(self):
        """Default action if no sub-command is passed."""
        self.app.args.print_help()

    @ex(
        help='chart your portfolio\'s net liquidity or realized profit/loss over time',
        arguments=[
            (
                ['csv'],
                {
                    'action': 'store',
                    'help': 'path to .csv file containing full portfolio transaction history'
                }
            ),
            (
                ['-n', '--netliq'],
                {
                    'action': 'store_true',
                    'help': 'show net liquidity over time instead of realized profit/loss'
                }
            ),
            (
                ['-d', '--duration'],
                {
                    'action': 'store',
                    'help': '{all,10y,5y,1y,ytd,6m,3m,1m,5d}',
                    'default': 'ytd'
                }
            )
        ]
    )
    def plot(self):
        # read the given csv file and prepare it
        df = pd.read_csv(self.app.pargs.csv)
        df = df.reindex(index=df.index[::-1])
        df.index = range(len(df))

        # create a portfolio with the given history
        pf = Portfolio(df, net_liq=self.app.pargs.netliq)
        pf.calculate()
        # get the P/L or net liq and save the graph
        val = pf.plot(self.app.pargs.duration)

        # print current positions
        print(('Current net liquidity' if self.app.pargs.netliq else 'Realized P/L') + f': ${val:.2f}')
        print('Current positions:')
        for p in pf.positions.values():
            print(p)
