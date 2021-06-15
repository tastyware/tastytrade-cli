import click


@click.group(chain=True, help='Buy, sell, and analyze futures.')
def future():
    pass


@future.command()
@click.argument('quantity')
@click.argument('symbol')
@click.argument('price')
def buy(quantity, symbol, price):
    """Buy QUANTITY contracts of SYMBOL.
    PRICE is the limit price per contract.
    """
    print(f'Buying {quantity}x {symbol} @ ${price}')


@future.command()
@click.argument('quantity')
@click.argument('symbol')
@click.argument('price')
def sell(quantity, symbol, price):
    """Sell QUANTITY contracts of SYMBOL.
    PRICE is the limit price per contract.
    """
    print(f'Selling {quantity}x {symbol} @ ${price}')


@future.command()
@click.argument('symbol')
def spot(symbol):
    """Look up the current bid/ask for SYMBOL.
    """
    print('Current price: Who the heck knows?')
