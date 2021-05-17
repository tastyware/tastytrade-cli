from cement import Controller, ex


@ex(help='buy, sell, and analyze futures')
class FutureController(Controller):
    class Meta:
        label = 'future'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'buy, sell, and analyze futures'

    @ex(help='display current price and other data for a given symbol')
    def spot(self):
        print('Inside spot')

    @ex(help='buy a contract with the given parameters')
    def buy(self):
        print('Inside buy')

    @ex(help='sell a contract with the given parameters')
    def sell(self):
        print('Inside sell')
