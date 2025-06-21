import asyncio
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Annotated

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
    Option as TastytradeOption,
)
from tastytrade.market_data import get_market_data, get_market_data_by_type
from tastytrade.order import (
    InstrumentType,
    NewOrder,
    OrderAction,
    OrderTimeInForce,
    OrderType,
)
from tastytrade.utils import TastytradeError, get_tasty_monthly
from typer import Option
from yaspin import yaspin

from ttcli.utils import (
    ZERO,
    AsyncTyper,
    RenewableSession,
    conditional_color,
    decimalify,
    get_confirmation,
    is_monthly,
    listen_events,
    print_error,
    print_warning,
    round_to_tick_size,
)


def choose_expiration(
    chain: NestedOptionChain,
    dte: int | None,
    weeklies: bool,
) -> NestedOptionChainExpiration:
    if weeklies:
        exps = chain.expirations
    else:
        exps = [e for e in chain.expirations if is_monthly(e.expiration_date)]
    if dte is not None:
        return min(
            exps,
            key=lambda exp: abs(
                (exp.expiration_date - datetime.now().date()).days - dte
            ),
        )
    exps.sort(key=lambda e: e.expiration_date)
    tasty_monthly = get_tasty_monthly()
    default = exps[0]
    for i, exp in enumerate(exps):
        if exp.expiration_date == tasty_monthly:
            default = exp
            print(f"{i + 1}) {exp.expiration_date} (default)")
        else:
            print(f"{i + 1}) {exp.expiration_date}")
    choice = 0
    while choice not in range(1, len(exps) + 1):
        try:
            raw = input("Please choose an expiration: ")
            choice = int(raw)
        except ValueError:
            return default

    return exps[choice - 1]


def choose_futures_expiration(
    chain: NestedFutureOptionChain,
    dte: int | None,
    weeklies: bool,
) -> NestedFutureOptionChainExpiration:
    subchain = chain.option_chains[0]
    if weeklies:
        exps = subchain.expirations
    else:
        exps = [e for e in subchain.expirations if e.expiration_type != "Weekly"]
    if dte is not None:
        return min(
            exps,
            key=lambda exp: abs(exp.days_to_expiration - dte),
        )
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


option = AsyncTyper(help="Buy, sell, and analyze options.", no_args_is_help=True)


@option.command(
    help="Buy or sell calls with the given parameters.",
    context_settings={"ignore_unknown_options": True},
    no_args_is_help=True,
)
async def call(
    symbol: str,
    quantity: int,
    strike: Annotated[
        Decimal | None,
        Option(
            "--strike",
            "-s",
            help="The chosen strike for the option.",
            parser=decimalify,
        ),
    ] = None,
    width: Annotated[
        int | None,
        Option(
            "--width", "-w", help="Turns the order into a spread with the given width."
        ),
    ] = None,
    gtc: Annotated[
        bool, Option("--gtc", help="Place a GTC order instead of a day order.")
    ] = False,
    delta: Annotated[
        int | None, Option("--delta", "-d", help="The chosen delta for the option.")
    ] = None,
    weeklies: Annotated[
        bool, Option("--weeklies", help="Show all expirations, not just monthlies.")
    ] = False,
    dte: Annotated[
        int | None, Option("--dte", help="Days to expiration for the option.")
    ] = None,
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
    if dte is None:
        dte = sesh.config.getint("option", "default-dte", fallback=None)
    symbol = symbol.upper()
    is_future = symbol[0] == "/"
    if is_future:  # futures options
        chain = NestedFutureOptionChain.get(sesh, symbol)
        subchain = choose_futures_expiration(chain, dte, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get(sesh, symbol)[0]
        subchain = choose_expiration(chain, dte, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    dxfeeds = [s.call_streamer_symbol for s in subchain.strikes]
    greeks_dict: dict[str, Greeks] = {}

    if not strike:
        with yaspin(color="green", text="Fetching greeks..."):
            async with DXLinkStreamer(sesh) as streamer:
                await streamer.subscribe(Greeks, dxfeeds)
                async for greek in streamer.listen(Greeks):
                    greeks_dict[greek.event_symbol] = greek
                    if len(greeks_dict) == len(dxfeeds):
                        break
        greeks = list(greeks_dict.values())
        selected = min(greeks, key=lambda g: abs(g.delta * 100 - Decimal(delta or 0)))
        # set strike with the closest delta
        strike = next(
            s.strike_price
            for s in subchain.strikes
            if s.call_streamer_symbol == selected.event_symbol
        )

    strike_symbol = next(s.call for s in subchain.strikes if s.strike_price == strike)
    if width:
        try:
            spread_strike = next(
                s for s in subchain.strikes if s.strike_price == strike + width
            )
        except StopIteration:
            print_error(f"Unable to locate option at strike {strike + width}!")
            return
        dxfeeds = [strike_symbol, spread_strike.call]
        data = get_market_data_by_type(
            sesh,
            options=dxfeeds if not is_future else None,
            future_options=dxfeeds if is_future else None,
        )
        data_dict = {d.symbol: d for d in data}
        bid = data_dict[strike_symbol].bid - data_dict[spread_strike.call].ask  # type: ignore
        ask = data_dict[strike_symbol].ask - data_dict[spread_strike.call].bid  # type: ignore
    else:
        data = get_market_data(
            sesh,
            strike_symbol,
            InstrumentType.FUTURE_OPTION if is_future else InstrumentType.EQUITY_OPTION,
        )
        bid = data.bid or 0
        ask = data.ask or 0
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

    short_symbol = next(s.call for s in subchain.strikes if s.strike_price == strike)
    if width:
        if is_future:  # futures options
            res = FutureOption.get(
                sesh,
                [short_symbol, spread_strike.call],  # type: ignore
            )
        else:
            res = TastytradeOption.get(sesh, [short_symbol, spread_strike.call])  # type: ignore
        res.sort(key=lambda x: x.strike_price)
        legs = [
            res[0].build_leg(
                Decimal(abs(quantity)),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
            ),
            res[1].build_leg(
                Decimal(abs(quantity)),
                OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN,
            ),
        ]
    else:
        if is_future:
            call = FutureOption.get(sesh, short_symbol)
        else:
            call = TastytradeOption.get(sesh, short_symbol)
        legs = [
            call.build_leg(
                Decimal(abs(quantity)),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
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
    fees = data.fee_calculation.total_fees if data.fee_calculation else ZERO

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


@option.command(
    help="Buy or sell puts with the given parameters.",
    context_settings={"ignore_unknown_options": True},
    no_args_is_help=True,
)
async def put(
    symbol: str,
    quantity: int,
    strike: Annotated[
        Decimal | None,
        Option(
            "--strike",
            "-s",
            help="The chosen strike for the option.",
            parser=decimalify,
        ),
    ] = None,
    width: Annotated[
        int | None,
        Option(
            "--width", "-w", help="Turns the order into a spread with the given width."
        ),
    ] = None,
    gtc: Annotated[
        bool, Option("--gtc", help="Place a GTC order instead of a day order.")
    ] = False,
    delta: Annotated[
        int | None, Option("--delta", "-d", help="The chosen delta for the option.")
    ] = None,
    weeklies: Annotated[
        bool, Option("--weeklies", help="Show all expirations, not just monthlies.")
    ] = False,
    dte: Annotated[
        int | None, Option("--dte", help="Days to expiration for the option.")
    ] = None,
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
    if dte is None:
        dte = sesh.config.getint("option", "default-dte", fallback=None)
    symbol = symbol.upper()
    is_future = symbol[0] == "/"
    if is_future:  # futures options
        chain = NestedFutureOptionChain.get(sesh, symbol)
        subchain = choose_futures_expiration(chain, dte, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get(sesh, symbol)[0]
        subchain = choose_expiration(chain, dte, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    dxfeeds = [s.put_streamer_symbol for s in subchain.strikes]
    greeks_dict: dict[str, Greeks] = {}

    if not strike:
        with yaspin(color="green", text="Fetching greeks..."):
            async with DXLinkStreamer(sesh) as streamer:
                await streamer.subscribe(Greeks, dxfeeds)
                async for greek in streamer.listen(Greeks):
                    greeks_dict[greek.event_symbol] = greek
                    if len(greeks_dict) == len(dxfeeds):
                        break
        greeks = list(greeks_dict.values())
        selected = min(greeks, key=lambda g: abs(g.delta * 100 + Decimal(delta or 0)))
        # set strike with the closest delta
        strike = next(
            s.strike_price
            for s in subchain.strikes
            if s.put_streamer_symbol == selected.event_symbol
        )

    strike_symbol = next(s.put for s in subchain.strikes if s.strike_price == strike)
    if width:
        try:
            spread_strike = next(
                s for s in subchain.strikes if s.strike_price == strike - width
            )
        except StopIteration:
            print_error(f"Unable to locate option at strike {strike - width}!")
            return
        dxfeeds = [strike_symbol, spread_strike.put]
        data = get_market_data_by_type(
            sesh,
            options=dxfeeds if not is_future else None,
            future_options=dxfeeds if is_future else None,
        )
        data_dict = {d.symbol: d for d in data}
        bid = data_dict[strike_symbol].bid - data_dict[spread_strike.call].ask  # type: ignore
        ask = data_dict[strike_symbol].ask - data_dict[spread_strike.call].bid  # type: ignore
    else:
        data = get_market_data(
            sesh,
            strike_symbol,
            InstrumentType.FUTURE_OPTION if is_future else InstrumentType.EQUITY_OPTION,
        )
        bid = data.bid or 0
        ask = data.ask or 0
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
        if is_future:  # futures options
            res = FutureOption.get(
                sesh,
                [short_symbol, spread_strike.put],  # type: ignore
            )
        else:
            res = TastytradeOption.get(sesh, [short_symbol, spread_strike.put])  # type: ignore
        res.sort(key=lambda x: x.strike_price, reverse=True)
        legs = [
            res[0].build_leg(
                Decimal(abs(quantity)),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
            ),
            res[1].build_leg(
                Decimal(abs(quantity)),
                OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN,
            ),
        ]
    else:
        if is_future:  # futures options
            put = FutureOption.get(sesh, short_symbol)
        else:
            put = TastytradeOption.get(sesh, short_symbol)
        legs = [
            put.build_leg(
                Decimal(abs(quantity)),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
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
    fees = data.fee_calculation.total_fees if data.fee_calculation else ZERO

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


@option.command(
    help="Buy or sell strangles with the given parameters.",
    context_settings={"ignore_unknown_options": True},
    no_args_is_help=True,
)
async def strangle(
    symbol: str,
    quantity: int,
    call: Annotated[
        Decimal | None,
        Option(
            "--call",
            "-c",
            help="The chosen strike for the call option.",
            parser=decimalify,
        ),
    ] = None,
    put: Annotated[
        Decimal | None,
        Option(
            "--put",
            "-p",
            help="The chosen strike for the put option.",
            parser=decimalify,
        ),
    ] = None,
    width: Annotated[
        int | None,
        Option(
            "--width",
            "-w",
            help="Turns the order into an iron condor with the given width.",
        ),
    ] = None,
    gtc: Annotated[
        bool, Option("--gtc", help="Place a GTC order instead of a day order.")
    ] = False,
    delta: Annotated[
        int | None, Option("--delta", "-d", help="The chosen delta for both options.")
    ] = None,
    weeklies: Annotated[
        bool, Option("--weeklies", help="Show all expirations, not just monthlies.")
    ] = False,
    dte: Annotated[
        int | None, Option("--dte", help="Days to expiration for the strangle.")
    ] = None,
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
    if dte is None:
        dte = sesh.config.getint("option", "default-dte", fallback=None)
    symbol = symbol.upper()
    is_future = symbol[0] == "/"
    if is_future:  # futures options
        chain = NestedFutureOptionChain.get(sesh, symbol)
        subchain = choose_futures_expiration(chain, dte, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get(sesh, symbol)[0]
        subchain = choose_expiration(chain, dte, weeklies)
        ticks = chain.tick_sizes
    fmt = lambda x: round_to_tick_size(x, ticks)

    put_dxf = [s.put_streamer_symbol for s in subchain.strikes]
    call_dxf = [s.call_streamer_symbol for s in subchain.strikes]
    dxfeeds = put_dxf + call_dxf
    greeks_dict: dict[str, Greeks] = {}

    if delta is not None:
        with yaspin(color="green", text="Fetching greeks..."):
            async with DXLinkStreamer(sesh) as streamer:
                await streamer.subscribe(Greeks, dxfeeds)
                async for greek in streamer.listen(Greeks):
                    greeks_dict[greek.event_symbol] = greek
                    if len(greeks_dict) == len(dxfeeds):
                        break
        put_greeks = [v for v in greeks_dict.values() if v.event_symbol in put_dxf]
        call_greeks = [v for v in greeks_dict.values() if v.event_symbol in call_dxf]

        selected_put = min(
            put_greeks, key=lambda g: abs(g.delta * 100 + Decimal(delta))
        )
        selected_call = min(
            call_greeks, key=lambda g: abs(g.delta * 100 - Decimal(delta))
        )
        # set strike with the closest delta
        put_strike = next(
            s
            for s in subchain.strikes
            if s.put_streamer_symbol == selected_put.event_symbol
        )
        call_strike = next(
            s
            for s in subchain.strikes
            if s.call_streamer_symbol == selected_call.event_symbol
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
                f"Unable to locate option at strike {put_strike.strike_price - width}!"
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
            call_strike.call,
            put_strike.put,
            put_spread_strike.put,
            call_spread_strike.call,
        ]
        data = get_market_data_by_type(
            sesh,
            options=dxfeeds if not is_future else None,
            future_options=dxfeeds if is_future else None,
        )
        data_dict = {d.symbol: d for d in data}
        bid = (
            data_dict[call_strike.call].bid  # type: ignore
            + data_dict[put_strike.put].bid
            - data_dict[put_spread_strike.put].ask
            - data_dict[call_spread_strike.call].ask
        )
        ask = (
            data_dict[call_strike.call].ask  # type: ignore
            + data_dict[put_strike.put].ask
            - data_dict[put_spread_strike.put].bid
            - data_dict[call_spread_strike.call].bid
        )
    else:
        dxfeeds = [put_strike.put, call_strike.call]
        data = get_market_data_by_type(
            sesh,
            options=dxfeeds if not is_future else None,
            future_options=dxfeeds if is_future else None,
        )
        data_dict = {d.symbol: d for d in data}
        bid = sum([q.bid or 0 for q in data_dict.values()])
        ask = sum([q.ask or 0 for q in data_dict.values()])
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
    if is_future:  # futures options
        options = FutureOption.get(sesh, tt_symbols)
    else:
        options = TastytradeOption.get(sesh, tt_symbols)
    options.sort(key=lambda o: o.strike_price)
    q = Decimal(quantity)
    if width:
        legs = [
            options[0].build_leg(
                abs(q),
                OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN,
            ),
            options[1].build_leg(
                abs(q),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
            ),
            options[2].build_leg(
                abs(q),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
            ),
            options[3].build_leg(
                abs(q),
                OrderAction.BUY_TO_OPEN if quantity < 0 else OrderAction.SELL_TO_OPEN,
            ),
        ]
    else:
        legs = [
            options[0].build_leg(
                abs(q),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
            ),
            options[1].build_leg(
                abs(q),
                OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
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
    fees = data.fee_calculation.total_fees if data.fee_calculation else ZERO

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


@option.command(help="Fetch and display an options chain.", no_args_is_help=True)
async def chain(
    symbol: str,
    strikes: Annotated[
        int | None, Option("--strikes", "-s", help="The number of strikes to fetch.")
    ] = None,
    weeklies: Annotated[
        bool, Option("--weeklies", help="Show all expirations, not just monthlies.")
    ] = False,
    dte: Annotated[
        int | None, Option("--dte", help="Days to expiration for the chain.")
    ] = None,
):
    sesh = RenewableSession()
    symbol = symbol.upper()

    if dte is None:
        dte = sesh.config.getint("option", "default-dte", fallback=None)
    if strikes is None:
        strikes = sesh.config.getint("option", "strike-count", fallback=16)
    is_future = symbol[0] == "/"
    if is_future:  # futures options
        chain = NestedFutureOptionChain.get(sesh, symbol)
        subchain = choose_futures_expiration(chain, dte, weeklies)
        ticks = subchain.tick_sizes
    else:
        chain = NestedOptionChain.get(sesh, symbol)[0]
        subchain = choose_expiration(chain, dte, weeklies)
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
    show_theta = sesh.config.getboolean("option.chain", "show-theta", fallback=False)
    show_oi = sesh.config.getboolean(
        "option.chain", "show-open-interest", fallback=False
    )
    show_volume = sesh.config.getboolean("option.chain", "show-volume", fallback=False)
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

    with yaspin(color="green", text="Fetching quotes..."):
        async with DXLinkStreamer(sesh) as streamer:
            if is_future:  # futures options
                future = Future.get(sesh, subchain.underlying_symbol)  # type: ignore
                await streamer.subscribe(Trade, [future.streamer_symbol])
            else:
                await streamer.subscribe(Trade, [symbol])
            trade = await streamer.get_event(Trade)

            subchain.strikes.sort(key=lambda s: s.strike_price)
            mid_index = 0
            if strikes < len(subchain.strikes):
                while subchain.strikes[mid_index].strike_price < trade.price:
                    mid_index += 1
                half = strikes // 2
                all_strikes = subchain.strikes[mid_index - half : mid_index + half]
            else:
                all_strikes = subchain.strikes
            mid_index = 0
            while all_strikes[mid_index].strike_price < trade.price:
                mid_index += 1

            dxfeeds = [s.call_streamer_symbol for s in all_strikes] + [
                s.put_streamer_symbol for s in all_strikes
            ]

            # take into account the symbol we subscribed to
            streamer_symbol = symbol if symbol[0] != "/" else future.streamer_symbol  # type: ignore
            trade_dict = defaultdict(lambda: 0)
            trade_dict[streamer_symbol] = trade.day_volume or 0

            greeks_task = asyncio.create_task(listen_events(dxfeeds, Greeks, streamer))
            quote_task = asyncio.create_task(listen_events(dxfeeds, Quote, streamer))
            tasks = [greeks_task, quote_task]
            if show_oi:
                summary_task = asyncio.create_task(
                    listen_events(dxfeeds, Summary, streamer)
                )
                tasks.append(summary_task)
            if show_volume:
                trade_task = asyncio.create_task(
                    listen_events(dxfeeds, Trade, streamer)
                )
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
            prepend.append(f"{abs(greeks_dict[strike.call_streamer_symbol].theta):.2f}")
            row.append(f"{abs(greeks_dict[strike.put_streamer_symbol].theta):.2f}")
        if show_oi:
            prepend.append(
                f"{summary_dict[strike.call_streamer_symbol].open_interest}"  # type: ignore
            )
            row.append(f"{summary_dict[strike.put_streamer_symbol].open_interest}")  # type: ignore
        if show_volume:
            prepend.append(f"{trade_dict[strike.call_streamer_symbol].day_volume}")  # type: ignore
            row.append(f"{trade_dict[strike.put_streamer_symbol].day_volume}")  # type: ignore

        prepend.reverse()
        table.add_row(*(prepend + row), end_section=(i == mid_index - 1))

    console.print(table)
