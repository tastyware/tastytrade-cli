import asyncclick as click

from ttcli.option import option
from ttcli.portfolio import portfolio
from ttcli.utils import CONTEXT_SETTINGS, VERSION


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(VERSION)
async def app():
    pass


def main():
    app.add_command(option)
    app.add_command(portfolio, name="pf")

    app(_anyio_backend="asyncio")
