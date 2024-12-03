import os
import shutil
from importlib.resources import as_file, files

import asyncclick as click

from ttcli.option import option
from ttcli.portfolio import portfolio
from ttcli.stock import stock
from ttcli.utils import CONTEXT_SETTINGS, VERSION, config_path


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(VERSION)
async def app():
    pass


def main():
    app.add_command(option)
    app.add_command(portfolio, name="pf")
    app.add_command(stock)

    # create ttcli.cfg if it doesn't exist
    if not os.path.exists(config_path):
        data_file = files("ttcli.data").joinpath("ttcli.cfg")
        with as_file(data_file) as path:
            # copy default config to user home dir
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            shutil.copyfile(path, config_path)

    app(_anyio_backend="asyncio")
