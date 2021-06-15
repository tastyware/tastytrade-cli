import click


@click.group(chain=True, help='Buy, sell, and analyze options.')
def option():
    pass


@option.command(help='Buy an option with the given parameters.')
@click.option('-s', '--strike', type=float)
@click.argument('quantity', type=int)
@click.argument('underlying', type=str)
@click.argument('price', type=float)
def buy(quantity, underlying, price, strike):
    print(f'Buying {quantity}x {underlying} ~ {strike:.2f} @ ${price:.2f}')


@option.command()
@click.option('-d', '--delta', type=int, help='Sell the contract at the given delta.', default=16)
@click.option('-s', '--strike', type=float, help='Sell the contract at the given strike.')
@click.argument('quantity', type=int)
@click.argument('underlying', type=str)
@click.argument('price', type=float)
def sell(delta, strike, quantity, underlying, price):
    """Sell QUANTITY contracts on UNDERLYING.
    PRICE is the limit price for each individual contract.

    If neither delta nor strike is provided, will default to 16 delta.
    """
    strike = 420  # lookup strike based on delta if not provided
    print(f'Selling {quantity}x {underlying} ~ {strike:.2f} @ ${price:.2f}')


@option.command(help='Fetch and display an options chain.')
@click.option('-e', '--expiration', type=str,
              help='The expiration date for the chain. Defaults to the closest monthly to 45 DTE.')
@click.argument('underlying', type=str)
def chain(underlying, expiration):
    print(f'Options chain for {underlying} on {expiration}:')
