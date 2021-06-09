from cement import App, TestApp
from cement.core.exc import CaughtSignal

from .controller import BaseController
from .crypto.controller import CryptoController
from .future.controller import FutureController
from .option.controller import OptionController
from .order.controller import OrderController
from .portfolio.controller import PortfolioController
from .quant.controller import QuantController
from .stock.controller import StockController
from .utils import TastyworksCLIError
from .watchlist.controller import WatchlistController


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
