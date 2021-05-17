from cement import Controller, ex


class CryptoController(Controller):
    class Meta:
        label = 'crypto'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'buy, sell, and analyze cryptocurrencies'

    @ex(help='buy a cryptocurrency with the given parameters')
    def buy(self):
        print('Inside buy')

    @ex(help='sell a cryptocurrency with the given parameters')
    def sell(self):
        print('Inside sell')
