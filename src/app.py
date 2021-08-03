import sys

import asyncclick as click
import asyncio

from .future.commands import future
from .option.commands import option
from .pairs.commands import pairs
from .plot.commands import plot
from .utils import VERSION


@click.group()
@click.version_option(VERSION)
async def app():
    pass


def main():
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app.add_command(future)
    app.add_command(option)
    app.add_command(plot)
    app.add_command(pairs)

    app(_anyio_backend='asyncio')
