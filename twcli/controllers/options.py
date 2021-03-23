from cement import Controller, ex

class Option(Controller):
    class Meta:
        label = 'option'
        stacked_type = 'embedded'
        stacked_on = 'base'

    @ex(help='long option')
    def long(self):
        pass

    @ex(help='short option')
    def short(self):
        pass
