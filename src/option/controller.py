from cement import Controller, ex


class OptionController(Controller):
    class Meta:
        label = 'option'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'buy, sell, and analyze options'

    @ex(help='display current price and other data for a given symbol')
    def spot(self):
        print('Inside spot')

    @ex(help='display the options chain for a given symbol')
    def chain(self):
        print('Inside chain')

    @ex(help='buy an option with the given parameters')
    def buy(self):
        print('Inside buy')

    @ex(help='sell an option with the given parameters')
    def sell(self):
        print('Inside sell')
