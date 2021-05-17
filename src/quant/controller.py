from cement import Controller, ex


class QuantController(Controller):
    class Meta:
        label = 'quant'
        stacked_on = 'tw'
        stacked_type = 'nested'
        help = description = 'mathematical and statistical analysis'

    @ex(help='find theoretical pricing according to the Black-Scholes model')
    def bs(self):
        print('Inside bs')
