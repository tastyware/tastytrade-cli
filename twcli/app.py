import asyncio
import logging
import sys

import asyncclick as click

from .option.commands import option
from .plot.commands import plot
from .utils import VERSION

LOGGER = logging.getLogger(__name__)


@click.group()
@click.version_option(VERSION)
async def app():
    pass


def main():
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        LOGGER.debug('Using Windows-specific event loop policy')

    app.add_command(option)
    app.add_command(plot)

    app(_anyio_backend='asyncio')
