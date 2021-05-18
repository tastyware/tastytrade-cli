from cement import Controller, ex
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
        help='chart your portfolio\'s net liquidity and realized profit/loss over time',
        arguments=[
            (
                ['csv'],
                {
                    'action': 'store',
                    'help': 'csv file containing full portfolio transaction history'
                }
            ),
            (
                ['-d', '--duration'],
                {
                    'action': 'store',
                    'help': '{all,10y,5y,1y,ytd,6m,3m,1m,5d}',
                    'default': 'ytd'
                }
            ),
            (
                ['-o', '--output'],
                {
                    'action': 'store',
                    'help': 'where to place the output png'
                }
            )
        ]
    )
    def plot(self):
        print('csv:', self.app.pargs.csv, self.app.pargs.duration)
