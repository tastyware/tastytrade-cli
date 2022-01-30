from decimal import Decimal
from typing import Optional

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastyworks.models.option import Option, OptionType
from tastyworks.models.option_chain import get_option_chain
from tastyworks.models.order import (Order, OrderDetails, OrderPriceEffect,
                                     OrderType)
from tastyworks.models.trading_account import TradingAccount
from tastyworks.models.underlying import Underlying, UnderlyingType
from tastyworks.streamer import DataStreamer

from .option import choose_expiration
from ..utils import RenewableTastyAPISession, get_tasty_monthly, get_confirmation


@click.group(chain=True, help='Buy, sell, and analyze options.')
async def option():
    pass


@option.command(help='Buy or sell strangles with the given parameters.')
@click.argument('underlying', type=str)
@click.argument('quantity', type=int)
async def strangle(underlying: str, quantity: int):
    '''
    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)
    expiration = await choose_expiration(sesh, undl)

    strike_put = input(f'Please choose a strike for the put (default 16 delta): ')
    strike_call = input(f'Please choose a strike for the call (default 16 delta): ')

    bid, mid, ask = 4.20, 4.23, 4.25  # placeholder
    print(f'Bid: {bid:.2f}\tMid: {mid:.2f}\tAsk: {ask:.2f}')
    price = input('Please enter a limit price for the entire order (default mid): ')

    print('Order Review')
    print('============')
    print('[')
    print(f'\t{quantity} {underlying} {strike_put}p {expiration}')
    print(f'\t{quantity} {underlying} {strike_call}c {expiration}')
    print(']', f'@ {price}')

    if get_confirmation('Send order? Y/n '):
        pass
    '''
    pass


@option.command(help='Buy or sell puts with the given parameters.')
@click.option('-s', '--strike', type=int, help='The chosen strike for the option.')
@click.argument('underlying', type=str)
@click.argument('quantity', type=int)
async def put(underlying: str, quantity: int, strike: Optional[int] = None):
    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)
    expiration = await choose_expiration(sesh, undl)

    #strike = input(f'Please choose a strike for the put (default 16 delta): ')

    option = Option(
        ticker=underlying,
        quantity=abs(quantity),
        expiry=expiration,
        strike=strike,
        option_type=OptionType.PUT,
        underlying_type=UnderlyingType.EQUITY
    )
    sub_values = {'Quote': [option.symbol_dxf]}
    streamer = await DataStreamer.create(sesh)
    await streamer.add_data_sub(sub_values)
    async for item in streamer.listen():
        quote = item.data[0]
        bid = quote['bidPrice']
        ask = quote['askPrice']
        mid = (bid + ask) / 2
        break
    await streamer.remove_data_sub(sub_values)

    print(f'Bid: {bid:.2f}\tMid: {mid:.2f}\tAsk: {ask:.2f}')
    price = input('Please enter a limit price for the entire order (default mid): ')
    if not price:
        price = mid

    details = OrderDetails(
        type=OrderType.LIMIT,
        price=Decimal(price),
        price_effect=OrderPriceEffect.CREDIT if quantity < 0 else OrderPriceEffect.DEBIT
    )
    order = Order(details)
    order.add_leg(option)

    accounts = await TradingAccount.get_remote_accounts(sesh)
    acct = accounts[1]  # TODO: choose account here, bypassed by environment var

    print('Order Review')
    print('============')
    print(f'\t{quantity} {underlying} {strike}p {expiration}')
    print(f'@ {price}')

    if get_confirmation('Send order? Y/n '):
        res = await acct.execute_order(order, sesh, dry_run=True)
        print(res)

    await streamer.close()


@option.command(help='Fetch and display an options chain.')
@click.option('-s', '--strikes', type=int, default=8,
              help='The number of strikes to fetch above and below the spot price.')
@click.argument('underlying', type=str)
async def chain(underlying: str, strikes: Optional[int] = None):
    sub_values = {'Quote': [underlying]}

    sesh = await RenewableTastyAPISession.create()
    undl = Underlying(underlying)

    strike_price = 0
    streamer = await DataStreamer.create(sesh)
    await streamer.add_data_sub(sub_values)
    async for item in streamer.listen():
        quote = item.data[0]
        bid = quote['bidPrice']
        ask = quote['askPrice']
        strike_price = (bid + ask) / 2
        break
    await streamer.remove_data_sub(sub_values)

    expiration = await choose_expiration(sesh, undl)

    console = Console()
    table = Table(show_header=True, header_style='bold', title=f'Options chain for {underlying} on {expiration}')
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
    options_sub_values = {
        'Quote': dxfeeds,
        'Greeks': dxfeeds
    }
    await streamer.add_data_sub(options_sub_values)
    data = []
    async for item in streamer.listen():
        data.append(item.data)
        if len(data) == 2:
            break
    await streamer.remove_data_sub(options_sub_values)

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
        for item in data[0]:
            if item['eventSymbol'] == put_dxf:
                put_bid = item['bidPrice']
                put_ask = item['askPrice']
                break
        for item in data[1]:
            if item['eventSymbol'] == put_dxf:
                put_delta = int(item['delta'] * 100)
                break
        for item in data[0]:
            if item['eventSymbol'] == call_dxf:
                call_bid = item['bidPrice']
                call_ask = item['askPrice']
                break
        for item in data[1]:
            if item['eventSymbol'] == call_dxf:
                call_delta = int(item['delta'] * 100)
                break

        if call_bid == 0.0:
            print(call_dxf, data[0])
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
