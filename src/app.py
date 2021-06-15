import click

from .future.commands import future
from .option.commands import option
from .plot.commands import plot
from .utils import VERSION


@click.group()
@click.version_option(VERSION)
def app():
    pass


def main():
    app.add_command(future)
    app.add_command(option)
    app.add_command(plot)

    app()
