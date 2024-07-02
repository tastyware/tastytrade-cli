import asyncio
import sys

import asyncclick as click

from ttcli.option import option
from ttcli.portfolio import portfolio
from ttcli.utils import CONTEXT_SETTINGS, VERSION, logger


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(VERSION)
async def app():
    pass


def main():
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logger.debug('Using Windows-specific event loop policy')

    app.add_command(option)
    app.add_command(portfolio, name='pf')

    app(_anyio_backend='asyncio')
