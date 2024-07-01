from datetime import date
from decimal import Decimal
from typing import Optional

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import EventType, Greeks, Quote
from tastytrade.instruments import NestedOptionChain, Option
from tastytrade.order import (NewOrder, OrderAction, OrderTimeInForce,
                              OrderType, PriceEffect)
from tastytrade.utils import get_tasty_monthly

from ttcli.utils import (RenewableSession, get_confirmation, is_monthly,
                         print_error, print_warning)


def choose_expiration(
    chain: NestedOptionChain,
    include_weeklies: bool = False
) -> date:
    exps = [e.expiration_date for e in chain.expirations]
    if not include_weeklies:
        exps = [e for e in exps if is_monthly(e)]
    default = exps.index(get_tasty_monthly())
    for i, exp in enumerate(exps):
        if i == default:
            print(f'{i + 1}) {exp} (default)')
        else:
            print(f'{i + 1}) {exp}')
    choice = 0
    while choice not in range(1, len(exps) + 1):
        try:
            raw = input('Please choose an expiration: ')
            choice = int(raw)
        except ValueError:
            if not raw:
                return exps[default]

    return exps[choice - 1]


async def listen_quotes(
    n_quotes: int,
    streamer: DXLinkStreamer,
    skip: str | None = None
) -> dict[str, Quote]:
    quote_dict = {}
    async for quote in streamer.listen(EventType.QUOTE):
        if quote.eventSymbol != skip:
            quote_dict[quote.eventSymbol] = quote
        if len(quote_dict) == n_quotes:
            return quote_dict


async def listen_greeks(
    n_greeks: int,
    streamer: DXLinkStreamer
) -> dict[str, Greeks]:
    greeks_dict = {}
    async for greeks in streamer.listen(EventType.GREEKS):
        greeks_dict[greeks.eventSymbol] = greeks
        if len(greeks_dict) == n_greeks:
            return greeks_dict


@click.group(chain=True, help='Buy, sell, and analyze options.')
async def option():
    pass


@option.command(help='Buy or sell calls with the given parameters.')
@click.option('-s', '--strike', type=int, help='The chosen strike for the option.')
@click.option('-d', '--delta', type=int, help='The chosen delta for the option.')
@click.option('--gtc', is_flag=True, help='Place a GTC order instead of a day order.')
@click.option('--weeklies', is_flag=True, help='Show all expirations, not just monthlies.')
@click.argument('symbol', type=str)
@click.argument('quantity', type=int)
async def call(symbol: str, quantity: int, strike: Optional[int] = None,
               gtc: bool = False, weeklies: bool = False, delta: Optional[int] = None):
    if strike is not None and delta is not None:
        print_error('Must specify either delta or strike, but not both.')
        return
    elif not strike and not delta:
        print_error('Please specify either delta or strike for the option.')
        return
    elif abs(delta) > 99:
        print_error('Delta value is too high, -99 <= delta <= 99')
        return

    sesh = RenewableSession()
    chain = NestedOptionChain.get_chain(sesh, symbol)
    expiration = choose_expiration(chain, weeklies)
    subchain = next(e for e in chain.expirations if e.expiration_date == expiration)

    async with DXLinkStreamer(sesh) as streamer:
        if not strike:
            dxfeeds = [s.call_streamer_symbol for s in subchain.strikes]
            await streamer.subscribe(EventType.GREEKS, dxfeeds)
            greeks_dict = await listen_greeks(len(dxfeeds), streamer)
            greeks = list(greeks_dict.values())

            lowest = 100
            selected = None
            for g in greeks:
                diff = abs(g.delta * Decimal(100) - delta)
                if diff < lowest:
                    selected = g
                    lowest = diff
            # set strike with the closest delta
            strike = next(s.strike_price for s in subchain.strikes
                          if s.call_streamer_symbol == selected.eventSymbol)

        await streamer.subscribe(EventType.QUOTE, [selected.eventSymbol])
        quote = await streamer.get_event(EventType.QUOTE)
        mid = (quote.bidPrice + quote.askPrice) / Decimal(2)

        console = Console()
        table = Table(show_header=True, header_style='bold', title_style='bold',
                    title=f'Quote for {symbol} {strike}C {expiration}')
        table.add_column('Bid', style='green', width=8, justify='center')
        table.add_column('Mid', width=8, justify='center')
        table.add_column('Ask', style='red', width=8, justify='center')
        table.add_row(f'{quote.bidPrice:.2f}', f'{mid:.2f}', f'{quote.askPrice:.2f}')
        console.print(table)

        price = input('Please enter a limit price per quantity (default mid): ')
        if not price:
            price = round(mid, 2)
        price = Decimal(price)

        call = Option.get_option(sesh, next(s.call for s in subchain.strikes if s.strike_price == strike))
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[call.build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN)],
            price=price,
            price_effect=PriceEffect.CREDIT if quantity < 0 else PriceEffect.DEBIT
        )
        acc = sesh.get_account()
        nl = acc.get_balances(sesh).net_liquidating_value

        data = acc.place_order(sesh, order, dry_run=True)
        bp = data.buying_power_effect.change_in_buying_power
        percent = bp / nl * Decimal(100)
        fees = data.fee_calculation.total_fees

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
        table.add_row(f'{quantity}', symbol, f'${strike:.2f}', 'CALL', f'{expiration}', f'${price:.2f}',
                      f'${bp:.2f}', f'{percent:.2f}%', f'${fees:.2f}')
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        if get_confirmation('Send order? Y/n '):
            acc.place_order(sesh, order, dry_run=False)


@option.command(help='Buy or sell puts with the given parameters.')
@click.option('-s', '--strike', type=Decimal, help='The chosen strike for the option.')
@click.option('-d', '--delta', type=int, help='The chosen delta for the option.')
@click.option('-w', '--width', type=int, help='Turns the order into a spread with the given width.')
@click.option('--gtc', is_flag=True, help='Place a GTC order instead of a day order.')
@click.option('--weeklies', is_flag=True, help='Show all expirations, not just monthlies.')
@click.argument('symbol', type=str)
@click.argument('quantity', type=int)
async def put(symbol: str, quantity: int, strike: Optional[int] = None, width: Optional[int] = None,
              gtc: bool = False, weeklies: bool = False, delta: Optional[int] = None):
    if strike is not None and delta is not None:
        print_error('Must specify either delta or strike, but not both.')
        return
    elif not strike and not delta:
        print_error('Please specify either delta or strike for the option.')
        return
    elif abs(delta) > 99:
        print_error('Delta value is too high, -99 <= delta <= 99')
        return

    sesh = RenewableSession()
    chain = NestedOptionChain.get_chain(sesh, symbol)
    expiration = choose_expiration(chain, weeklies)
    subchain = next(e for e in chain.expirations if e.expiration_date == expiration)

    async with DXLinkStreamer(sesh) as streamer:
        if not strike:
            dxfeeds = [s.put_streamer_symbol for s in subchain.strikes]
            await streamer.subscribe(EventType.GREEKS, dxfeeds)
            greeks_dict = await listen_greeks(len(dxfeeds), streamer)
            greeks = list(greeks_dict.values())

            lowest = 100
            selected = None
            for g in greeks:
                diff = abs(g.delta * Decimal(100) + delta)
                if diff < lowest:
                    selected = g
                    lowest = diff
            # set strike with the closest delta
            strike = next(s.strike_price for s in subchain.strikes
                          if s.put_streamer_symbol == selected.eventSymbol)

        if width:
            spread_strike = next(s for s in subchain.strikes if s.strike_price == strike - width)
            await streamer.subscribe(EventType.QUOTE, [selected.eventSymbol, spread_strike.put_streamer_symbol])
            quote_dict = await listen_quotes(2, streamer)
            bid = quote_dict[selected.eventSymbol].bidPrice - quote_dict[spread_strike.put_streamer_symbol].askPrice
            ask = quote_dict[selected.eventSymbol].askPrice - quote_dict[spread_strike.put_streamer_symbol].bidPrice
            mid = (bid + ask) / Decimal(2)
        else:
            await streamer.subscribe(EventType.QUOTE, [selected.eventSymbol])
            quote = await streamer.get_event(EventType.QUOTE)
            bid = quote.bidPrice
            ask = quote.askPrice
            mid = (bid + ask) / Decimal(2)

        console = Console()
        if width:
            table = Table(show_header=True, header_style='bold', title_style='bold',
                          title=f'Quote for {symbol} put spread {expiration}')
        else:
            table = Table(show_header=True, header_style='bold', title_style='bold',
                          title=f'Quote for {symbol} {strike}P {expiration}')
        table.add_column('Bid', style='green', width=8, justify='center')
        table.add_column('Mid', width=8, justify='center')
        table.add_column('Ask', style='red', width=8, justify='center')
        table.add_row(f'{bid:.2f}', f'{mid:.2f}', f'{ask:.2f}')
        console.print(table)

        price = input('Please enter a limit price per quantity (default mid): ')
        if not price:
            price = round(mid, 2)
        price = Decimal(price)

        short_symbol = next(s.put for s in subchain.strikes if s.strike_price == strike)
        if width:
            res = Option.get_options(sesh, [short_symbol, spread_strike.put])
            res.sort(key=lambda x: x.strike_price, reverse=True)
            legs = [
                res[0].build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN),
                res[1].build_leg(abs(quantity), OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN)
            ]
        else:
            put = Option.get_option(sesh, short_symbol)
            legs = [put.build_leg(abs(quantity), OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN)]
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=price,
            price_effect=PriceEffect.CREDIT if quantity < 0 else PriceEffect.DEBIT
        )
        acc = sesh.get_account()

        data = acc.place_order(sesh, order, dry_run=True)
        if data.errors:
            for error in data.errors:
                print_error(error.message)
            return

        nl = acc.get_balances(sesh).net_liquidating_value
        bp = data.buying_power_effect.change_in_buying_power
        percent = bp / nl * Decimal(100)
        fees = data.fee_calculation.total_fees

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
        table.add_row(f'{quantity:+}', symbol, f'${strike:.2f}', 'PUT', f'{expiration}', f'${price:.2f}',
                      f'${bp:.2f}', f'{percent:.2f}%', f'${fees:.2f}')
        if width:
            table.add_row(f'{-quantity:+}', symbol, f'${spread_strike.strike_price:.2f}',
                          'PUT', f'{expiration}', '-', '-', '-', '-')
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        if get_confirmation('Send order? Y/n '):
            acc.place_order(sesh, order, dry_run=False)


@option.command(help='Fetch and display an options chain.')
@click.option('-w', '--weeklies', is_flag=True,
              help='Show all expirations, not just monthlies.')
@click.option('-s', '--strikes', type=int, default=8,
              help='The number of strikes to fetch above and below the spot price.')
@click.argument('symbol', type=str)
async def chain(symbol: str, strikes: int = 8, weeklies: bool = False):
    sesh = RenewableSession()
    strike_price = None
    async with DXLinkStreamer(sesh) as streamer:
        await streamer.subscribe(EventType.QUOTE, [symbol])
        quote = await streamer.get_event(EventType.QUOTE)
        strike_price = (quote.bidPrice + quote.askPrice) / 2

        chain = NestedOptionChain.get_chain(sesh, symbol)
        expiration = choose_expiration(chain, weeklies)
        subchain = next(e for e in chain.expirations if e.expiration_date == expiration)

        console = Console()
        table = Table(show_header=True, header_style='bold', title_style='bold',
                      title=f'Options chain for {symbol} expiring {expiration}')
        table.add_column(u'Call \u03B4', width=8, justify='center')
        table.add_column('Bid', style='green', width=8, justify='center')
        table.add_column('Ask', style='red', width=8, justify='center')
        table.add_column('Strike', width=8, justify='center')
        table.add_column('Bid', style='green', width=8, justify='center')
        table.add_column('Ask', style='red', width=8, justify='center')
        table.add_column(u'Put \u03B4', width=8, justify='center')

        if strikes * 2 < len(subchain.strikes):
            mid_index = 0
            while subchain.strikes[mid_index].strike_price < strike_price:
                mid_index += 1
            all_strikes = subchain.strikes[mid_index - strikes:mid_index + strikes]
        else:
            all_strikes = subchain.strikes

        dxfeeds = ([s.call_streamer_symbol for s in all_strikes] +
                   [s.put_streamer_symbol for s in all_strikes])
        await streamer.subscribe(EventType.QUOTE, dxfeeds)
        await streamer.subscribe(EventType.GREEKS, dxfeeds)

        greeks_dict = await listen_greeks(len(dxfeeds), streamer)
        # take into account the symbol we subscribed to
        quote_dict = await listen_quotes(len(dxfeeds), streamer, skip=symbol)

        for i, strike in enumerate(all_strikes):
            put_bid = quote_dict[strike.put_streamer_symbol].bidPrice
            put_ask = quote_dict[strike.put_streamer_symbol].askPrice
            put_delta = int(greeks_dict[strike.put_streamer_symbol].delta * 100)
            call_bid = quote_dict[strike.call_streamer_symbol].bidPrice
            call_ask = quote_dict[strike.call_streamer_symbol].askPrice
            call_delta = int(greeks_dict[strike.call_streamer_symbol].delta * 100)

            table.add_row(
                f'{call_delta:g}',
                f'{call_bid:.2f}',
                f'{call_ask:.2f}',
                f'{strike.strike_price:.2f}',
                f'{put_bid:.2f}',
                f'{put_ask:.2f}',
                f'{put_delta:g}'
            )
            if i == strikes - 1:
                table.add_row('=======', 'ITM ^', '=======', '=======',
                              '=======', 'ITM v', '=======', style='white')

        console.print(table)
