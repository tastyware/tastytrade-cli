import asyncio
from decimal import Decimal

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Greeks, Summary, Quote, Trade
from tastytrade.instruments import (
    Future,
    FutureOption,
    NestedFutureOptionChain,
    NestedFutureOptionChainExpiration,
    NestedOptionChain,
    NestedOptionChainExpiration,
    Option,
)
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
from tastytrade.utils import TastytradeError, get_tasty_monthly, today_in_new_york
from datetime import datetime

from ttcli.utils import (
    RenewableSession,
    conditional_color,
    get_confirmation,
    is_monthly,
    listen_events,
    print_error,
    print_warning,
    round_to_tick_size,
)


def choose_expiration(
    chain: NestedOptionChain, include_weeklies: bool = False
) -> NestedOptionChainExpiration:
    exps = [e for e in chain.expirations]
    if not include_weeklies:
        exps = [e for e in exps if is_monthly(e.expiration_date)]
    exps.sort(key=lambda e: e.expiration_date)
    default = get_tasty_monthly()
    default_option: NestedOptionChainExpiration
    for i, exp in enumerate(exps):
        if exp.expiration_date == default:
            default_option = exp
            print(f"{i + 1}) {exp.expiration_date} (default)")
        else:
            print(f"{i + 1}) {exp.expiration_date}")
    choice = 0
    while choice not in range(1, len(exps) + 1):
        try:
            raw = input("Please choose an expiration: ")
            choice = int(raw)
        except ValueError:
            return default_option  # type: ignore

    return exps[choice - 1]


def choose_futures_expiration(
    chain: NestedFutureOptionChain, include_weeklies: bool = False
) -> NestedFutureOptionChainExpiration:
    subchain = chain.option_chains[0]
    if include_weeklies:
        exps = [e for e in subchain.expirations]
    else:
        exps = [e for e in subchain.expirations if e.expiration_type != "Weekly"]
    exps.sort(key=lambda e: e.expiration_date)
    # find closest to 45 DTE
    default = min(exps, key=lambda e: abs(e.days_to_expiration - 45))
    for i, exp in enumerate(exps):
        if exp == default:
            print(f"{i + 1}) {exp.expiration_date} [{exp.underlying_symbol}] (default)")
        else:
            print(f"{i + 1}) {exp.expiration_date} [{exp.underlying_symbol}]")
    choice = 0
    while choice not in range(1, len(exps) + 1):
        try:
            raw = input("Please choose an expiration: ")
            choice = int(raw)
        except ValueError:
            return default

    return exps[choice - 1]


@click.group(chain=True, help="Buy, sell, and analyze options.")
async def option():
    pass


@option.command(help="Buy or sell calls with the given parameters.")
@click.option("-s", "--strike", type=Decimal, help="The chosen strike for the option.")
@click.option("-d", "--delta", type=int, help="The chosen delta for the option.")
@click.option(
    "-w",
    "--width",
    type=int,
    help="Turns the order into a spread with the given width.",
)
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.option(
    "--weeklies", is_flag=True, help="Show all expirations, not just monthlies."
)
@click.option("--dte", type=int, help="Days to expiration for the option.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def call(
    symbol: str,
    quantity: int,
    strike: Decimal | None = None,
    width: int | None = None,
    gtc: bool = False,
    weeklies: bool = False,
    delta: int | None = None,
    dte: int | None = None,
):
    if strike is not None and delta is not None:
        print_error("Must specify either delta or strike, but not both.")
        return
    elif not strike and not delta:
        print_error("Please specify either delta or strike for the option.")
        return
    elif delta is not None and abs(delta) > 99:
        print_error("Delta value is too high, -99 <= delta <= 99")
        return

    sesh = RenewableSession()
    symbol = symbol.upper()
    if symbol[0] == "/":  # futures options
        chain = NestedFutureOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.option_chains[0].expirations,
                key=lambda exp: abs(exp.days_to_expiration - dte),
            )
        else:
            subchain = choose_futures_expiration(chain, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.expirations,
                key=lambda exp: abs(
                    (exp.expiration_date - datetime.now().date()).days - dte
                ),
            )
        else:
            subchain = choose_expiration(chain, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    async with DXLinkStreamer(sesh) as streamer:
        if not strike:
            dxfeeds = [s.call_streamer_symbol for s in subchain.strikes]
            greeks_dict = await listen_events(dxfeeds, Greeks, streamer)
            greeks = list(greeks_dict.values())

            lowest = 100
            selected = None
            for g in greeks:
                diff = abs(g.delta * 100 - Decimal(delta))  # type: ignore
                if diff < lowest:
                    selected = g
                    lowest = diff
            # set strike with the closest delta
            strike = next(
                s.strike_price
                for s in subchain.strikes
                if s.call_streamer_symbol == selected.event_symbol  # type: ignore
            )

        strike_symbol = next(
            s.call_streamer_symbol for s in subchain.strikes if s.strike_price == strike
        )
        if width:
            try:
                spread_strike = next(
                    s for s in subchain.strikes if s.strike_price == strike + width
                )
            except StopIteration:
                print_error(f"Unable to locate option at strike {strike + width}!")
                return
            dxfeeds = [strike_symbol, spread_strike.call_streamer_symbol]
            quote_dict = await listen_events(dxfeeds, Quote, streamer)
            bid = (
                quote_dict[strike_symbol].bid_price
                - quote_dict[spread_strike.call_streamer_symbol].ask_price
            )
            ask = (
                quote_dict[strike_symbol].ask_price
                - quote_dict[spread_strike.call_streamer_symbol].bid_price
            )
        else:
            await streamer.subscribe(Quote, [strike_symbol])
            quote = await streamer.get_event(Quote)
            bid = quote.bid_price
            ask = quote.ask_price
        mid = fmt((bid + ask) / Decimal(2))
        console = Console()
        if width:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} call spread {subchain.expiration_date}",
            )
        else:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} {strike}C {subchain.expiration_date}",
            )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per quantity (default mid): ")
        price = mid if not price else Decimal(price)

        short_symbol = next(
            s.call for s in subchain.strikes if s.strike_price == strike
        )
        if width:
            if symbol[0] == "/":  # futures options
                res = FutureOption.get_future_options(
                    sesh,
                    [short_symbol, spread_strike.call],  # type: ignore
                )
            else:
                res = Option.get_options(sesh, [short_symbol, spread_strike.call])  # type: ignore
            res.sort(key=lambda x: x.strike_price)
            legs = [
                res[0].build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
                res[1].build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.BUY_TO_OPEN
                    if quantity < 0
                    else OrderAction.SELL_TO_OPEN,
                ),
            ]
        else:
            if symbol[0] == "/":
                call = FutureOption.get_future_option(sesh, short_symbol)
            else:
                call = Option.get_option(sesh, short_symbol)
            legs = [
                call.build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                )
            ]
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=fmt(price * m),
        )
        acc = sesh.get_account()
        try:
            data = acc.place_order(sesh, order, dry_run=True)
        except TastytradeError as e:
            print_error(str(e))
            return

        nl = acc.get_balances(sesh).net_liquidating_value
        bp = data.buying_power_effect.change_in_buying_power
        percent = abs(bp) / nl * Decimal(100)
        fees = data.fee_calculation.total_fees  # type: ignore

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title="Order Review",
        )
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Strike", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Expiration", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            f"${fmt(strike)}",
            "CALL",
            f"{subchain.expiration_date}",
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
        )
        if width:
            table.add_row(
                f"{-quantity:+}",
                symbol,
                f"${fmt(spread_strike.strike_price)}",  # type: ignore
                "CALL",
                f"{subchain.expiration_date}",
                "-",
                "-",
                "-",
                "-",
            )
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        warn_percent = sesh.config.getfloat(
            "portfolio", "bp-max-percent-per-position", fallback=None
        )
        if warn_percent and percent > warn_percent:
            print_warning(
                f"Buying power usage is above per-position target of {warn_percent}%!"
            )
        if get_confirmation("Send order? Y/n "):
            acc.place_order(sesh, order, dry_run=False)


@option.command(help="Buy or sell puts with the given parameters.")
@click.option("-s", "--strike", type=Decimal, help="The chosen strike for the option.")
@click.option("-d", "--delta", type=int, help="The chosen delta for the option.")
@click.option(
    "-w",
    "--width",
    type=int,
    help="Turns the order into a spread with the given width.",
)
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.option(
    "--weeklies", is_flag=True, help="Show all expirations, not just monthlies."
)
@click.option("--dte", type=int, help="Days to expiration for the option.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def put(
    symbol: str,
    quantity: int,
    strike: Decimal | None = None,
    width: int | None = None,
    gtc: bool = False,
    weeklies: bool = False,
    delta: int | None = None,
    dte: int | None = None,
):
    if strike is not None and delta is not None:
        print_error("Must specify either delta or strike, but not both.")
        return
    elif not strike and not delta:
        print_error("Please specify either delta or strike for the option.")
        return
    elif delta is not None and abs(delta) > 99:
        print_error("Delta value is too high, -99 <= delta <= 99")
        return

    sesh = RenewableSession()
    symbol = symbol.upper()
    if symbol[0] == "/":  # futures options
        chain = NestedFutureOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.option_chains[0].expirations,
                key=lambda exp: abs(exp.days_to_expiration - dte),
            )
        else:
            subchain = choose_futures_expiration(chain, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.expirations,
                key=lambda exp: abs(
                    (exp.expiration_date - datetime.now().date()).days - dte
                ),
            )
        else:
            subchain = choose_expiration(chain, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    async with DXLinkStreamer(sesh) as streamer:
        if not strike:
            dxfeeds = [s.put_streamer_symbol for s in subchain.strikes]
            greeks_dict = await listen_events(dxfeeds, Greeks, streamer)
            greeks = list(greeks_dict.values())

            lowest = 100
            selected = None
            for g in greeks:
                diff = abs(g.delta * 100 + Decimal(delta))  # type: ignore
                if diff < lowest:
                    selected = g
                    lowest = diff
            # set strike with the closest delta
            strike = next(
                s.strike_price
                for s in subchain.strikes
                if s.put_streamer_symbol == selected.event_symbol  # type: ignore
            )

        strike_symbol = next(
            s.put_streamer_symbol for s in subchain.strikes if s.strike_price == strike
        )
        if width:
            try:
                spread_strike = next(
                    s for s in subchain.strikes if s.strike_price == strike - width
                )
            except StopIteration:
                print_error(f"Unable to locate option at strike {strike - width}!")
                return
            dxfeeds = [strike_symbol, spread_strike.put_streamer_symbol]
            quote_dict = await listen_events(dxfeeds, Quote, streamer)
            bid = (
                quote_dict[strike_symbol].bid_price
                - quote_dict[spread_strike.put_streamer_symbol].ask_price
            )
            ask = (
                quote_dict[strike_symbol].ask_price
                - quote_dict[spread_strike.put_streamer_symbol].bid_price
            )
        else:
            await streamer.subscribe(Quote, [strike_symbol])
            quote = await streamer.get_event(Quote)
            bid = quote.bid_price
            ask = quote.ask_price
        mid = fmt((bid + ask) / Decimal(2))
        console = Console()
        if width:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} put spread {subchain.expiration_date}",
            )
        else:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} {strike}P {subchain.expiration_date}",
            )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per quantity (default mid): ")
        price = mid if not price else Decimal(price)

        short_symbol = next(s.put for s in subchain.strikes if s.strike_price == strike)
        if width:
            if symbol[0] == "/":  # futures options
                res = FutureOption.get_future_options(
                    sesh,
                    [short_symbol, spread_strike.put],  # type: ignore
                )
            else:
                res = Option.get_options(sesh, [short_symbol, spread_strike.put])  # type: ignore
            res.sort(key=lambda x: x.strike_price, reverse=True)
            legs = [
                res[0].build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
                res[1].build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.BUY_TO_OPEN
                    if quantity < 0
                    else OrderAction.SELL_TO_OPEN,
                ),
            ]
        else:
            if symbol[0] == "/":  # futures options
                put = FutureOption.get_future_option(sesh, short_symbol)
            else:
                put = Option.get_option(sesh, short_symbol)
            legs = [
                put.build_leg(
                    Decimal(abs(quantity)),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                )
            ]
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=fmt(price * m),
        )
        acc = sesh.get_account()

        try:
            data = acc.place_order(sesh, order, dry_run=True)
        except TastytradeError as e:
            print_error(str(e))
            return

        nl = acc.get_balances(sesh).net_liquidating_value
        bp = data.buying_power_effect.change_in_buying_power
        percent = abs(bp) / nl * Decimal(100)
        fees = data.fee_calculation.total_fees  # type: ignore

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title="Order Review",
        )
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Strike", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Expiration", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            f"${fmt(strike)}",
            "PUT",
            f"{subchain.expiration_date}",
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
        )
        if width:
            table.add_row(
                f"{-quantity:+}",
                symbol,
                f"${fmt(spread_strike.strike_price)}",  # type: ignore
                "PUT",
                f"{subchain.expiration_date}",
                "-",
                "-",
                "-",
                "-",
            )
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        warn_percent = sesh.config.getfloat(
            "portfolio", "bp-max-percent-per-position", fallback=None
        )
        if warn_percent and percent > warn_percent:
            print_warning(
                f"Buying power usage is above per-position target of {warn_percent}%!"
            )
        if get_confirmation("Send order? Y/n "):
            acc.place_order(sesh, order, dry_run=False)


@option.command(help="Buy or sell strangles with the given parameters.")
@click.option(
    "-c", "--call", type=Decimal, help="The chosen strike for the call option."
)
@click.option("-p", "--put", type=Decimal, help="The chosen strike for the put option.")
@click.option("-d", "--delta", type=int, help="The chosen delta for both options.")
@click.option(
    "-w",
    "--width",
    type=int,
    help="Turns the order into an iron condor with the given width.",
)
@click.option("--dte", type=int, help="Days to expiration for the option.")
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.option(
    "--weeklies", is_flag=True, help="Show all expirations, not just monthlies."
)
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def strangle(
    symbol: str,
    quantity: int,
    call: Decimal | None = None,
    width: int | None = None,
    dte: int | None = None,
    gtc: bool = False,
    weeklies: bool = False,
    delta: int | None = None,
    put: Decimal | None = None,
):
    if (call is not None or put is not None) and delta is not None:
        print_error("Must specify either delta or strike, but not both.")
        return
    elif delta is not None and (call is not None or put is not None):
        print_error("Please specify either delta, or strikes for both options.")
        return
    elif delta is not None and abs(delta) > 99:
        print_error("Delta value is too high, -99 <= delta <= 99")
        return

    sesh = RenewableSession()
    symbol = symbol.upper()
    if symbol[0] == "/":  # futures options
        chain = NestedFutureOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.option_chains[0].expirations,
                key=lambda exp: abs(exp.days_to_expiration - dte),
            )
        else:
            subchain = choose_futures_expiration(chain, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get_chain(sesh, symbol)
        if dte is not None:
            subchain = min(
                chain.expirations,
                key=lambda exp: abs(
                    (exp.expiration_date - today_in_new_york()).days - dte
                ),
            )
        else:
            subchain = choose_expiration(chain, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    async with DXLinkStreamer(sesh) as streamer:
        if delta is not None:
            put_dxf = [s.put_streamer_symbol for s in subchain.strikes]
            call_dxf = [s.call_streamer_symbol for s in subchain.strikes]
            dxfeeds = put_dxf + call_dxf
            greeks_dict = await listen_events(dxfeeds, Greeks, streamer)
            put_greeks = [v for v in greeks_dict.values() if v.event_symbol in put_dxf]
            call_greeks = [
                v for v in greeks_dict.values() if v.event_symbol in call_dxf
            ]

            lowest = 100
            selected_put = None
            for g in put_greeks:
                diff = abs(g.delta * 100 + delta)
                if diff < lowest:
                    selected_put = g.event_symbol
                    lowest = diff
            lowest = 100
            selected_call = None
            for g in call_greeks:
                diff = abs(g.delta * 100 - delta)
                if diff < lowest:
                    selected_call = g.event_symbol
                    lowest = diff
            # set strike with the closest delta
            put_strike = next(
                s for s in subchain.strikes if s.put_streamer_symbol == selected_put
            )
            call_strike = next(
                s for s in subchain.strikes if s.call_streamer_symbol == selected_call
            )
        else:
            put_strike = next(s for s in subchain.strikes if s.strike_price == put)
            call_strike = next(s for s in subchain.strikes if s.strike_price == call)

        if width:
            try:
                put_spread_strike = next(
                    s
                    for s in subchain.strikes
                    if s.strike_price == put_strike.strike_price - width
                )
            except StopIteration:
                print_error(
                    f"Unable to locate option at strike {put_strike.strike_price + width}!"
                )
                return
            try:
                call_spread_strike = next(
                    s
                    for s in subchain.strikes
                    if s.strike_price == call_strike.strike_price + width
                )
            except StopIteration:
                print_error(
                    f"Unable to locate option at strike {call_strike.strike_price + width}!"
                )
                return

            dxfeeds = [
                call_strike.call_streamer_symbol,
                put_strike.put_streamer_symbol,
                put_spread_strike.put_streamer_symbol,
                call_spread_strike.call_streamer_symbol,
            ]
            quote_dict = await listen_events(dxfeeds, Quote, streamer)
            bid = (
                quote_dict[call_strike.call_streamer_symbol].bid_price
                + quote_dict[put_strike.put_streamer_symbol].bid_price
                - quote_dict[put_spread_strike.put_streamer_symbol].ask_price
                - quote_dict[call_spread_strike.call_streamer_symbol].ask_price
            )
            ask = (
                quote_dict[call_strike.call_streamer_symbol].ask_price
                + quote_dict[put_strike.put_streamer_symbol].ask_price
                - quote_dict[put_spread_strike.put_streamer_symbol].bid_price
                - quote_dict[call_spread_strike.call_streamer_symbol].bid_price
            )
        else:
            dxfeeds = [put_strike.put_streamer_symbol, call_strike.call_streamer_symbol]
            quote_dict = await listen_events(dxfeeds, Quote, streamer)
            bid = sum([q.bid_price for q in quote_dict.values()])
            ask = sum([q.ask_price for q in quote_dict.values()])
        mid = fmt((bid + ask) / Decimal(2))

        console = Console()
        if width:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} iron condor {subchain.expiration_date}",
            )
        else:
            table = Table(
                show_header=True,
                header_style="bold",
                title_style="bold",
                title=f"Quote for {symbol} {put_strike.strike_price}/{call_strike.strike_price} strangle {subchain.expiration_date}",
            )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per quantity (default mid): ")
        price = mid if not price else Decimal(price)

        tt_symbols = [put_strike.put, call_strike.call]
        if width:
            tt_symbols += [put_spread_strike.put, call_spread_strike.call]  # type: ignore
        if symbol[0] == "/":  # futures options
            options = FutureOption.get_future_options(sesh, tt_symbols)
        else:
            options = Option.get_options(sesh, tt_symbols)
        options.sort(key=lambda o: o.strike_price)
        q = Decimal(quantity)
        if width:
            legs = [
                options[0].build_leg(
                    abs(q),
                    OrderAction.BUY_TO_OPEN
                    if quantity < 0
                    else OrderAction.SELL_TO_OPEN,
                ),
                options[1].build_leg(
                    abs(q),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
                options[2].build_leg(
                    abs(q),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
                options[3].build_leg(
                    abs(q),
                    OrderAction.BUY_TO_OPEN
                    if quantity < 0
                    else OrderAction.SELL_TO_OPEN,
                ),
            ]
        else:
            legs = [
                options[0].build_leg(
                    abs(q),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
                options[1].build_leg(
                    abs(q),
                    OrderAction.SELL_TO_OPEN
                    if quantity < 0
                    else OrderAction.BUY_TO_OPEN,
                ),
            ]
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=price * m,
        )
        acc = sesh.get_account()

        try:
            data = acc.place_order(sesh, order, dry_run=True)
        except TastytradeError as e:
            print_error(str(e))
            return

        nl = acc.get_balances(sesh).net_liquidating_value
        bp = data.buying_power_effect.change_in_buying_power
        percent = abs(bp) / nl * Decimal(100)
        fees = data.fee_calculation.total_fees  # type: ignore

        table = Table(header_style="bold", title_style="bold", title="Order Review")
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Strike", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Expiration", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            f"${fmt(put_strike.strike_price)}",
            "PUT",
            f"{subchain.expiration_date}",
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
        )
        table.add_row(
            f"{quantity:+}",
            symbol,
            f"${fmt(call_strike.strike_price)}",
            "CALL",
            f"{subchain.expiration_date}",
            "-",
            "-",
            "-",
            "-",
        )
        if width:
            table.add_row(
                f"{-quantity:+}",
                symbol,
                f"${fmt(put_spread_strike.strike_price)}",  # type: ignore
                "PUT",
                f"{subchain.expiration_date}",
                "-",
                "-",
                "-",
                "-",
            )
            table.add_row(
                f"{-quantity:+}",
                symbol,
                f"${fmt(call_spread_strike.strike_price)}",  # type: ignore
                "CALL",
                f"{subchain.expiration_date}",
                "-",
                "-",
                "-",
                "-",
            )
        console.print(table)

        if data.warnings:
            for warning in data.warnings:
                print_warning(warning.message)
        warn_percent = sesh.config.getint(
            "portfolio", "bp-max-percent-per-position", fallback=None
        )
        if warn_percent and percent > warn_percent:
            print_warning(
                f"Buying power usage is above per-position target of {warn_percent}%!"
            )
        if get_confirmation("Send order? Y/n "):
            acc.place_order(sesh, order, dry_run=False)


@option.command(help="Fetch and display an options chain.")
@click.option(
    "-w", "--weeklies", is_flag=True, help="Show all expirations, not just monthlies."
)
@click.option("--dte", type=int, help="Days to expiration for the option.")
@click.option(
    "-s",
    "--strikes",
    type=int,
    default=8,
    help="The number of strikes to fetch above and below the spot price.",
)
@click.argument("symbol", type=str)
async def chain(
    symbol: str, strikes: int = 8, weeklies: bool = False, dte: int | None = None
):
    sesh = RenewableSession()
    symbol = symbol.upper()

    async with DXLinkStreamer(sesh) as streamer:
        if symbol[0] == "/":  # futures options
            chain = NestedFutureOptionChain.get_chain(sesh, symbol)
            if dte is not None:
                subchain = min(
                    chain.option_chains[0].expirations,
                    key=lambda exp: abs(exp.days_to_expiration - dte),
                )
            else:
                subchain = choose_futures_expiration(chain, weeklies)
            ticks = subchain.tick_sizes
        else:
            chain = NestedOptionChain.get_chain(sesh, symbol)
            if dte is not None:
                subchain = min(
                    chain.expirations,
                    key=lambda exp: abs(
                        (exp.expiration_date - today_in_new_york()).days - dte
                    ),
                )
            else:
                subchain = choose_expiration(chain, weeklies)
            ticks = chain.tick_sizes
        fmt = lambda x: round_to_tick_size(x, ticks)

        console = Console()
        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title=f"Options chain for {symbol} expiring {subchain.expiration_date}",
        )

        show_delta = sesh.config.getboolean("option.chain", "show-delta", fallback=True)
        show_theta = sesh.config.getboolean(
            "option.chain", "show-theta", fallback=False
        )
        show_oi = sesh.config.getboolean(
            "option.chain", "show-open-interest", fallback=False
        )
        show_volume = sesh.config.getboolean(
            "option.chain", "show-volume", fallback=False
        )
        if show_volume:
            table.add_column("Volume", justify="right")
        if show_oi:
            table.add_column("Open Int", justify="right")
        if show_theta:
            table.add_column("Call \u03b8", justify="center")
        if show_delta:
            table.add_column("Call \u0394", justify="center")
        table.add_column("Bid", style="green", justify="right")
        table.add_column("Ask", style="red", justify="right")
        table.add_column("Strike", justify="center")
        table.add_column("Bid", style="green", justify="right")
        table.add_column("Ask", style="red", justify="right")
        if show_delta:
            table.add_column("Put \u0394", justify="center")
        if show_theta:
            table.add_column("Put \u03b8", justify="center")
        if show_oi:
            table.add_column("Open Int", justify="right")
        if show_volume:
            table.add_column("Volume", justify="right")

        if symbol[0] == "/":  # futures options
            future = Future.get_future(sesh, subchain.underlying_symbol)  # type: ignore
            await streamer.subscribe(Trade, [future.streamer_symbol])
        else:
            await streamer.subscribe(Trade, [symbol])
        trade = await streamer.get_event(Trade)

        subchain.strikes.sort(key=lambda s: s.strike_price)
        if strikes * 2 < len(subchain.strikes):
            mid_index = 0
            while subchain.strikes[mid_index].strike_price < trade.price:  # type: ignore
                mid_index += 1
            all_strikes = subchain.strikes[mid_index - strikes : mid_index + strikes]
        else:
            all_strikes = subchain.strikes

        dxfeeds = [s.call_streamer_symbol for s in all_strikes] + [
            s.put_streamer_symbol for s in all_strikes
        ]

        # take into account the symbol we subscribed to
        streamer_symbol = symbol if symbol[0] != "/" else future.streamer_symbol  # type: ignore

        async def listen_trades(trade: Trade, symbol: str) -> dict[str, Trade]:
            trade_dict = {symbol: trade}
            await streamer.subscribe(Trade, dxfeeds)
            async for trade in streamer.listen(Trade):
                trade_dict[trade.event_symbol] = trade
                if len(trade_dict) == len(dxfeeds) + 1:
                    return trade_dict
            return trade_dict  # unreachable

        greeks_task = asyncio.create_task(listen_events(dxfeeds, Greeks, streamer))
        quote_task = asyncio.create_task(listen_events(dxfeeds, Quote, streamer))
        tasks = [greeks_task, quote_task]
        if show_oi:
            summary_task = asyncio.create_task(
                listen_events(dxfeeds, Summary, streamer)
            )
            tasks.append(summary_task)
        if show_volume:
            trade_task = asyncio.create_task(listen_trades(trade, streamer_symbol))
            tasks.append(trade_task)
        await asyncio.gather(*tasks)  # wait for all tasks
        greeks_dict = greeks_task.result()
        quote_dict = quote_task.result()
        if show_oi:
            summary_dict = summary_task.result()  # type: ignore
        if show_volume:
            trade_dict = trade_task.result()  # type: ignore

        for i, strike in enumerate(all_strikes):
            put_bid = quote_dict[strike.put_streamer_symbol].bid_price
            put_ask = quote_dict[strike.put_streamer_symbol].ask_price
            call_bid = quote_dict[strike.call_streamer_symbol].bid_price
            call_ask = quote_dict[strike.call_streamer_symbol].ask_price
            row = [
                f"{fmt(call_bid)}",
                f"{fmt(call_ask)}",
                f"{fmt(strike.strike_price)}",
                f"{fmt(put_bid)}",
                f"{fmt(put_ask)}",
            ]
            prepend = []
            if show_delta:
                put_delta = int(greeks_dict[strike.put_streamer_symbol].delta * 100)
                call_delta = int(greeks_dict[strike.call_streamer_symbol].delta * 100)
                prepend.append(f"{call_delta:g}")
                row.append(f"{put_delta:g}")

            if show_theta:
                prepend.append(
                    f"{abs(greeks_dict[strike.put_streamer_symbol].theta):.2f}"
                )
                row.append(f"{abs(greeks_dict[strike.call_streamer_symbol].theta):.2f}")
            if show_oi:
                prepend.append(
                    f"{summary_dict[strike.put_streamer_symbol].open_interest}"  # type: ignore
                )
                row.append(f"{summary_dict[strike.call_streamer_symbol].open_interest}")  # type: ignore
            if show_volume:
                prepend.append(f"{trade_dict[strike.put_streamer_symbol].day_volume}")  # type: ignore
                row.append(f"{trade_dict[strike.call_streamer_symbol].day_volume}")  # type: ignore

            prepend.reverse()
            table.add_row(*(prepend + row), end_section=(i == strikes - 1))

        console.print(table)
