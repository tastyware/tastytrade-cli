import os
import shutil
from importlib.resources import as_file, files
from typing import Annotated

from typer import Exit, Option, Typer, echo

from ttcli import VERSION
from ttcli.option import option
from ttcli.order import order
from ttcli.plot import plot
from ttcli.portfolio import portfolio
from ttcli.trade import trade
from ttcli.utils import config_path
from ttcli.watchlist import watchlist

cli = Typer()


@cli.callback(invoke_without_command=True, no_args_is_help=True)
def main(
    version: Annotated[
        bool, Option("--version", "-v", help="Show the installed version:")
    ] = False,
):
    # create ttcli.cfg if it doesn't exist
    if not os.path.exists(config_path):
        data_file = files("ttcli.data").joinpath("ttcli.cfg")
        with as_file(data_file) as path:
            # copy default config to user home dir
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            shutil.copyfile(path, config_path)
    if version:
        echo(f"tastyware/tastytrade-cli:v{VERSION}")
        raise Exit()


cli.add_typer(option, name="option")
cli.add_typer(order, name="order")
cli.add_typer(plot, name="plot")
cli.add_typer(portfolio, name="pf")
cli.add_typer(trade, name="trade")
cli.add_typer(watchlist, name=None)


if __name__ == "__main__":
    cli()
