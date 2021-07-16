import click


@click.group(chain=True, help='Buy, sell, and analyze options.')
def option():
    pass


@option.command(help='Buy or sell strangles with the given parameters.')
@click.argument('underlying', type=str)
@click.argument('quantity', type=int)
def strangle(underlying, quantity):
    default_date = 'jan'  # placeholder
    default_strike_put = 420  # placeholder
    default_strike_call = 440  # placeholder

    date = input(f'Please enter a date for the contracts (default {default_date}): ')
    strike_put = input(f'Please enter a strike for the put (default {default_strike_put}): ')
    strike_call = input(f'Please enter a strike for the call (default {default_strike_call}): ')

    bid, mid, ask = 4.20, 4.23, 4.25  # placeholder
    print(f'Bid: {bid:.2f}\tMid: {mid:.2f}\tAsk: {ask:.2f}')
    price = input('Please enter a limit price for the entire order (default mid): ')

    print('Order Review')
    print('============')
    print('{')
    for t in ['p', 'c']:
        print(f'\t{quantity}{t} {underlying} ~{strike_put} #{date}')
    print('}', f'@{price}')
    confirm = input('Send order? Y/n ')


if __name__ == '__main__':
    option()


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
