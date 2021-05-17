from cement import App, Controller, TestApp
from cement.core.exc import CaughtSignal
from cement.utils.version import get_version_banner

from .crypto.controller import CryptoController
from .future.controller import FutureController
from .option.controller import OptionController
from .order.controller import OrderController
from .plot.controller import PlotController
from .portfolio.controller import PortfolioController
from .quant.controller import QuantController
from .stock.controller import StockController
from .utils import TastyworksCLIError, get_version
from .watchlist.controller import WatchlistController

VERSION_BANNER = """
An easy-to-use command line interface for Tastyworks! %s
%s
""" % (get_version(), get_version_banner())


class BaseController(Controller):
    class Meta:
        label = 'tw'

        # text displayed at the top of --help output
        description = 'An easy-to-use command line interface for Tastyworks!'

        # text displayed at the bottom of --help output
        epilog = VERSION_BANNER

        # controller level arguments. ex: 'twcli --version'
        arguments = [
            # add a version banner
            (
                ['-v', '--version'],
                {
                    'action': 'version',
                    'version': VERSION_BANNER
                }
            ),
        ]

    def _default(self):
        """Default action if no sub-command is passed."""
        self.app.args.print_help()


class TastyworksCLI(App):
    """tastyworks-cli primary application."""

    class Meta:
        label = 'tw'

        # call sys.exit() on close
        exit_on_close = True

        # register handlers
        handlers = [
            BaseController,
            OptionController,
            StockController,
            FutureController,
            CryptoController,
            PortfolioController,
            WatchlistController,
            OrderController,
            QuantController,
            PlotController,
        ]


class TastyworksCLITest(TestApp, TastyworksCLI):
    """A sub-class of TastyworksCLI that is better suited for testing."""

    class Meta:
        label = 'tw'


def main():
    with TastyworksCLI() as app:
        try:
            app.run()

        except AssertionError as e:
            print('AssertionError > %s' % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback
                traceback.print_exc()

        except TastyworksCLIError as e:
            print('TastyworksCLIError > %s' % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback
                traceback.print_exc()

        except CaughtSignal as e:
            # Default Cement signals are SIGINT and SIGTERM, exit 0 (non-error)
            print('\n%s' % e)
            app.exit_code = 0


if __name__ == '__main__':
    main()
