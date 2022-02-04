from decimal import Decimal
from typing import Optional

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastyworks.models.option import Option, OptionType
from tastyworks.models.option_chain import get_option_chain
from tastyworks.models.order import (Order, OrderDetails, OrderPriceEffect,
                                     OrderType)
from tastyworks.models.underlying import Underlying, UnderlyingType
from tastyworks.streamer import DataStreamer

from ..utils import (RenewableTastyAPISession, TastyworksCLIError, get_account,
                     get_confirmation)
from .option import choose_expiration


@click.group(chain=True, help='Buy, sell, and analyze options.')
async def option():
    pass


@option.command(help='Buy or sell calls with the given parameters.')
@click.option('-s', '--strike', type=int, help='The chosen strike for the option.')
@click.option('-d', '--delta', type=int, help='The chosen delta for the option.')
@click.option('--all-expirations', is_flag=True, help='Show all expirations, not just monthlies.')
@click.argument('underlying', type=str)
@click.argument('quantity', type=int)
async def call(underlying: str, quantity: int, strike: Optional[int] = None,
               all_expirations: Optional[bool] = False, delta: Optional[int] = None):
    if strike is not None and delta is not None:
        raise TastyworksCLIError('Must specify either delta or strike, but not both.')
    elif not strike and not delta:
        raise TastyworksCLIError('Please specify either delta or strike for the option.')
    elif abs(delta) > 100:
        raise TastyworksCLIError('Delta value is too high, -100 <= delta <= 100')

    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)
    expiration = await choose_expiration(sesh, undl, all_expirations)
    streamer = await DataStreamer.create(sesh)

    if not strike:
        chain = await get_option_chain(sesh, undl, expiration)
        dxfeeds = [option.symbol_dxf for option in chain.options if option.option_type == OptionType.CALL]
        greeks = await streamer.stream('Greeks', dxfeeds)

        lowest = abs(greeks[0]['delta'] * 100.0 - delta)
        index = 0
        for i in range(1, len(greeks)):
            diff = abs(greeks[i]['delta'] * 100.0 - delta)
            if diff < lowest:
                index = i
                lowest = diff
        for option in chain.options:
            if option.symbol_dxf == greeks[index]['eventSymbol']:
                strike = option.strike
                break

    option = Option(
        ticker=underlying,
        quantity=abs(quantity),
        expiry=expiration,
        strike=strike,
        option_type=OptionType.CALL,
        underlying_type=UnderlyingType.EQUITY
    )
    quote = await streamer.stream('Quote', [option.symbol_dxf])
    bid = quote[0]['bidPrice']
    ask = quote[0]['askPrice']
    mid = (bid + ask) / 2

    await streamer.close()

    console = Console()
    table = Table(show_header=True, header_style='bold', title_style='bold',
                  title=f'Quote for {underlying} {strike}C {expiration}')
    table.add_column('Bid', style='green', width=8, justify='center')
    table.add_column('Mid', width=8, justify='center')
    table.add_column('Ask', style='red', width=8, justify='center')
    table.add_row(f'{bid:.2f}', f'{mid:.2f}', f'{ask:.2f}')
    console.print(table)

    price = input('Please enter a limit price for the entire order (default mid): ')
    if not price:
        price = round(mid * abs(quantity), 2)
    price = Decimal(price)

    details = OrderDetails(
        type=OrderType.LIMIT,
        price=price,
        price_effect=OrderPriceEffect.CREDIT if quantity < 0 else OrderPriceEffect.DEBIT
    )
    order = Order(details)
    order.add_leg(option)

    acct = await get_account(sesh)
    details = await acct.get_balance(sesh)
    nl = Decimal(details['net-liquidating-value'])

    data = await acct.execute_order(order, sesh, dry_run=True)
    bp = Decimal(data['buying-power-effect']['change-in-buying-power'])
    percent = bp / nl * Decimal(100)
    # bp_effect = data['buying-power-effect']['change-in-buying-power-effect']
    fees = Decimal(data['fee-calculation']['total-fees'])

    table = Table(show_header=True, header_style='bold', title_style='bold', title='Order Review')
    table.add_column('Quantity', width=8, justify='center')
    table.add_column('Symbol', width=8, justify='center')
    table.add_column('Strike', width=8, justify='center')
    table.add_column('Type', width=8, justify='center')
    table.add_column('Expiration', width=10, justify='center')
    table.add_column('Price', width=8, justify='center')
    table.add_column('BP', width=8, justify='center')
    table.add_column('% of NL', width=8, justify='center')
    table.add_column('Fees', width=8, justify='center')
    table.add_row(f'{quantity}', underlying, f'{strike:.2f}', 'CALL', f'{expiration}', f'${price:.2f}',
                  f'${bp:.2f}', f'{percent:.2f}%', f'${fees}')
    console.print(table)

    if data['warnings']:
        console.print('[bold orange]Warnings:[/bold orange]')
        for warning in data['warnings']:
            console.print(f'[i gray]{warning}[/i gray]')
    if get_confirmation('Send order? Y/n '):
        await acct.execute_order(order, sesh, dry_run=False)


@option.command(help='Buy or sell puts with the given parameters.')
@click.option('-s', '--strike', type=int, help='The chosen strike for the option.')
@click.option('-d', '--delta', type=int, help='The chosen delta for the option.')
@click.option('--all-expirations', is_flag=True, help='Show all expirations, not just monthlies.')
@click.argument('underlying', type=str)
@click.argument('quantity', type=int)
async def put(underlying: str, quantity: int, strike: Optional[int] = None,
              all_expirations: Optional[bool] = False, delta: Optional[int] = None):
    if strike is not None and delta is not None:
        raise TastyworksCLIError('Must specify either delta or strike, but not both.')
    elif not strike and not delta:
        raise TastyworksCLIError('Please specify either delta or strike for the option.')
    elif abs(delta) > 100:
        raise TastyworksCLIError('Delta value is too high, -100 <= delta <= 100')

    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)
    expiration = await choose_expiration(sesh, undl, all_expirations)
    streamer = await DataStreamer.create(sesh)

    if not strike:
        chain = await get_option_chain(sesh, undl, expiration)
        dxfeeds = [option.symbol_dxf for option in chain.options if option.option_type == OptionType.PUT]
        greeks = await streamer.stream('Greeks', dxfeeds)

        lowest = abs(greeks[0]['delta'] * 100.0 + delta)
        index = 0
        for i in range(1, len(greeks)):
            diff = abs(greeks[i]['delta'] * 100.0 + delta)
            if diff < lowest:
                index = i
                lowest = diff
        for option in chain.options:
            if option.symbol_dxf == greeks[index]['eventSymbol']:
                strike = option.strike
                break

    option = Option(
        ticker=underlying,
        quantity=abs(quantity),
        expiry=expiration,
        strike=strike,
        option_type=OptionType.PUT,
        underlying_type=UnderlyingType.EQUITY
    )
    quote = await streamer.stream('Quote', [option.symbol_dxf])
    bid = quote[0]['bidPrice']
    ask = quote[0]['askPrice']
    mid = (bid + ask) / 2

    await streamer.close()

    console = Console()
    table = Table(show_header=True, header_style='bold', title_style='bold',
                  title=f'Quote for {underlying} {strike}P {expiration}')
    table.add_column('Bid', style='green', width=8, justify='center')
    table.add_column('Mid', width=8, justify='center')
    table.add_column('Ask', style='red', width=8, justify='center')
    table.add_row(f'{bid:.2f}', f'{mid:.2f}', f'{ask:.2f}')
    console.print(table)

    price = input('Please enter a limit price for the entire order (default mid): ')
    if not price:
        price = round(mid * abs(quantity), 2)
    price = Decimal(price)

    details = OrderDetails(
        type=OrderType.LIMIT,
        price=price,
        price_effect=OrderPriceEffect.CREDIT if quantity < 0 else OrderPriceEffect.DEBIT
    )
    order = Order(details)
    order.add_leg(option)

    acct = await get_account(sesh)
    details = await acct.get_balance(sesh)
    nl = Decimal(details['net-liquidating-value'])

    data = await acct.execute_order(order, sesh, dry_run=True)
    bp = Decimal(data['buying-power-effect']['change-in-buying-power'])
    percent = bp / nl * Decimal(100)
    # bp_effect = data['buying-power-effect']['change-in-buying-power-effect']
    fees = Decimal(data['fee-calculation']['total-fees'])

    table = Table(show_header=True, header_style='bold', title_style='bold', title='Order Review')
    table.add_column('Quantity', width=8, justify='center')
    table.add_column('Symbol', width=8, justify='center')
    table.add_column('Strike', width=8, justify='center')
    table.add_column('Type', width=8, justify='center')
    table.add_column('Expiration', width=10, justify='center')
    table.add_column('Price', width=8, justify='center')
    table.add_column('BP', width=8, justify='center')
    table.add_column('% of NL', width=8, justify='center')
    table.add_column('Fees', width=8, justify='center')
    table.add_row(f'{quantity}', underlying, f'{strike:.2f}', 'PUT', f'{expiration}', f'${price:.2f}',
                  f'${bp:.2f}', f'{percent:.2f}%', f'${fees}')
    console.print(table)

    if data['warnings']:
        console.print('[bold orange]Warnings:[/bold orange]')
        for warning in data['warnings']:
            console.print(f'[i gray]{warning}[/i gray]')
    if get_confirmation('Send order? Y/n '):
        await acct.execute_order(order, sesh, dry_run=False)


@option.command(help='Fetch and display an options chain.')
@click.option('-s', '--strikes', type=int, default=8,
              help='The number of strikes to fetch above and below the spot price.')
@click.argument('underlying', type=str)
async def chain(underlying: str, strikes: Optional[int] = None):
    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)

    strike_price = 0
    streamer = await DataStreamer.create(sesh)
    quote = await streamer.stream('Quote', [underlying])
    bid = quote[0]['bidPrice']
    ask = quote[0]['askPrice']
    strike_price = (bid + ask) / 2

    expiration = await choose_expiration(sesh, undl)

    console = Console()
    table = Table(show_header=True, header_style='bold', title_style='bold',
                  title=f'Options chain for {underlying} on {expiration}')
    table.add_column('Delta', width=8, justify='center')
    table.add_column('Bid', style='red', width=8, justify='center')
    table.add_column('Ask', style='red', width=8, justify='center')
    table.add_column('Strike', width=8, justify='center')
    table.add_column('Bid', style='green', width=8, justify='center')
    table.add_column('Ask', style='green', width=8, justify='center')
    table.add_column('Delta', width=8, justify='center')

    chain = await get_option_chain(sesh, undl, expiration)
    puts = []
    calls = []
    for option in chain.options:
        if option.option_type == OptionType.CALL:
            calls.append(option)
        else:
            puts.append(option)

    puts_to_fetch = []
    calls_to_fetch = []
    if strikes * 2 < len(calls):
        mid_index = 0
        while calls[mid_index].strike < strike_price:
            mid_index += 1
        # handle weird edge scenarios here
        for call in calls[mid_index - strikes:mid_index + strikes]:
            calls_to_fetch.append(call)
        for put in puts[mid_index - strikes:mid_index + strikes]:
            puts_to_fetch.append(put)
    else:
        for call in calls:
            calls_to_fetch.append(call)
        for put in puts:
            puts_to_fetch.append(put)

    dxfeeds = [call.symbol_dxf for call in calls_to_fetch] + [put.symbol_dxf for put in puts_to_fetch]
    quotes = await streamer.stream('Quote', dxfeeds)
    greeks = await streamer.stream('Greeks', dxfeeds)

    for i in range(len(calls_to_fetch)):
        call_dxf = calls_to_fetch[i].symbol_dxf
        put_dxf = puts_to_fetch[i].symbol_dxf
        strike = calls_to_fetch[i].strike
        put_bid = 0
        put_ask = 0
        put_delta = 0
        call_bid = 0
        call_ask = 0
        call_delta = 0
        for item in quotes:
            if item['eventSymbol'] == put_dxf:
                put_bid = item['bidPrice']
                put_ask = item['askPrice']
                break
        for item in greeks:
            if item['eventSymbol'] == put_dxf:
                put_delta = int(item['delta'] * 100)
                break
        for item in quotes:
            if item['eventSymbol'] == call_dxf:
                call_bid = item['bidPrice']
                call_ask = item['askPrice']
                break
        for item in greeks:
            if item['eventSymbol'] == call_dxf:
                call_delta = int(item['delta'] * 100)
                break

        table.add_row(
            f'{put_delta:g}',
            f'{put_bid:.2f}',
            f'{put_ask:.2f}',
            f'{strike:.2f}',
            f'{call_bid:.2f}',
            f'{call_ask:.2f}',
            f'{call_delta:g}'
        )
        if i == strikes - 1:
            table.add_row('=======', 'ITM v', '=======', '=======', '=======', 'ITM ^', '=======', style='white')

    await streamer.close()
    console.print(table)
