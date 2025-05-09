from typer import Typer

from ttcli.utils import print_warning


watchlist = Typer()


@watchlist.command(
    name="wl",
    help="Show prices and metrics for symbols in the given watchlist.",
    no_args_is_help=True,
)
def filter(name: str):
    print_warning("This functionality hasn't been implemented yet!")
