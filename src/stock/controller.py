from cement import Controller, ex


class StockController(Controller):
    class Meta:
        label = 'stock'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'buy, sell, and analyze stock'

    @ex(help='display current price and other data for a given symbol')
    def spot(self):
        print('Inside spot')

    @ex(help='buy shares with the given parameters')
    def buy(self):
        print('Inside buy')

    @ex(help='sell shares with the given parameters')
    def sell(self):
        print('Inside sell')
