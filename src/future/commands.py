import asyncclick as click


@click.group(chain=True, help='Buy, sell, and analyze futures.')
async def future():
    pass


@future.command()
@click.argument('quantity')
@click.argument('symbol')
@click.argument('price')
async def buy(quantity, symbol, price):
    """Buy QUANTITY contracts of SYMBOL.
    PRICE is the limit price per contract.
    """
    print(f'Buying {quantity}x {symbol} @ ${price}')


@future.command()
@click.argument('quantity')
@click.argument('symbol')
@click.argument('price')
async def sell(quantity, symbol, price):
    """Sell QUANTITY contracts of SYMBOL.
    PRICE is the limit price per contract.
    """
    print(f'Selling {quantity}x {symbol} @ ${price}')


@future.command()
@click.argument('symbol')
async def spot(symbol):
    """Look up the current bid/ask for SYMBOL.
    """
    print('Current price: Who the heck knows?')
