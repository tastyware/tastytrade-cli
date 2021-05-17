from cement import Controller, ex


class WatchlistController(Controller):
    class Meta:
        label = 'watchlist'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'view current prices and other data for symbols in your watchlists'

    @ex(
        help='example sub command1',

        # sub-command level arguments. ex: 'twcli command1 --foo bar'
        arguments=[
            # add a sample foo option under subcommand namespace
            (
                ['-f', '--foo'],
                {
                    'help': 'notorious foo option',
                    'action': 'store',
                    'dest': 'foo'
                }
            ),
        ],
    )
    def command1(self):
        """Example sub-command."""
        data = {
            'foo': 'bar',
        }

        # do something with arguments
        if self.app.pargs.foo is not None:
            data['foo'] = self.app.pargs.foo

        self.app.render(data, 'command1.jinja2')
