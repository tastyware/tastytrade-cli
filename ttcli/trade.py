from decimal import Decimal

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote
from tastytrade.instruments import Cryptocurrency, Equity, Future, FutureProduct
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
from tastytrade.utils import TastytradeError

from ttcli.utils import (
    RenewableSession,
    conditional_color,
    get_confirmation,
    print_error,
    print_warning,
    round_to_tick_size,
    round_to_width,
)


@click.group(chain=True, help="Buy or sell stocks/ETFs, crypto, and futures.")
async def trade():
    pass


@trade.command(help="Buy or sell stocks/ETFs.")
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def stock(symbol: str, quantity: int, gtc: bool = False):
    sesh = RenewableSession()
    symbol = symbol.upper()
    equity = Equity.get_equity(sesh, symbol)
    fmt = lambda x: round_to_tick_size(x, equity.tick_sizes or [])

    async with DXLinkStreamer(sesh) as streamer:
        await streamer.subscribe(Quote, [symbol])
        quote = await streamer.get_event(Quote)
        bid = quote.bid_price
        ask = quote.ask_price
        mid = fmt((bid + ask) / Decimal(2))

        console = Console()
        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title=f"Quote for {symbol}",
        )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per share (default mid): ")
        price = mid if not price else Decimal(price)

        leg = equity.build_leg(
            Decimal(abs(quantity)),
            OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
        )
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[leg],
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

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title="Order Review",
        )
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
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


@trade.command(help="Buy cryptocurrency.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=Decimal)
async def crypto(symbol: str, quantity: Decimal):
    sesh = RenewableSession()
    symbol = symbol.upper()
    if "USD" not in symbol:
        symbol += "/USD"
    elif "/" not in symbol:
        symbol = symbol.split("USD")[0] + "/USD"
    crypto = Cryptocurrency.get_cryptocurrency(sesh, symbol)
    fmt = lambda x: round_to_width(x, crypto.tick_size)

    async with DXLinkStreamer(sesh) as streamer:
        await streamer.subscribe(Quote, [crypto.streamer_symbol])  # type: ignore
        quote = await streamer.get_event(Quote)
        bid = quote.bid_price
        ask = quote.ask_price
        mid = fmt((bid + ask) / Decimal(2))

        console = Console()
        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title=f"Quote for {symbol}",
        )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per unit (default mid): ")
        price = mid if not price else Decimal(price)

        leg = crypto.build_leg(
            Decimal(abs(quantity)),
            OrderAction.SELL_TO_OPEN if quantity < 0 else OrderAction.BUY_TO_OPEN,
        )
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC,
            order_type=OrderType.LIMIT,
            legs=[leg],
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

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title="Order Review",
        )
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
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


@trade.command(help="Buy or sell futures.")
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def future(symbol: str, quantity: int, gtc: bool = False):
    sesh = RenewableSession()
    symbol = symbol.upper()
    if not any(c.isdigit() for c in symbol):
        product = FutureProduct.get_future_product(sesh, symbol)
        fmt = ",".join([f" {m.name} ({m.value})" for m in product.active_months])
        print_error(
            f"Please enter the full futures symbol!\nCurrent active months:{fmt}"
        )
        return
    future = Future.get_future(sesh, symbol)
    fmt = lambda x: round_to_width(x, future.tick_size)

    async with DXLinkStreamer(sesh) as streamer:
        await streamer.subscribe(Quote, [future.streamer_symbol])
        quote = await streamer.get_event(Quote)
        bid = quote.bid_price
        ask = quote.ask_price
        mid = fmt((bid + ask) / Decimal(2))

        console = Console()
        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title=f"Quote for {symbol}",
        )
        table.add_column("Bid", style="green", justify="center")
        table.add_column("Mid", justify="center")
        table.add_column("Ask", style="red", justify="center")
        table.add_row(f"{fmt(bid)}", f"{fmt(mid)}", f"{fmt(ask)}")
        console.print(table)

        price = input("Please enter a limit price per share (default mid): ")
        price = mid if not price else Decimal(price)

        leg = future.build_leg(
            Decimal(abs(quantity)),
            OrderAction.SELL if quantity < 0 else OrderAction.BUY,
        )
        m = 1 if quantity < 0 else -1
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC if gtc else OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[leg],
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

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            title="Order Review",
        )
        table.add_column("Quantity", justify="center")
        table.add_column("Symbol", justify="center")
        table.add_column("Expiration", justify="center")
        table.add_column("Multiplier", justify="center")
        table.add_column("Price", justify="center")
        table.add_column("BP", justify="center")
        table.add_column("BP %", justify="center")
        table.add_column("Fees", justify="center")
        table.add_row(
            f"{quantity:+}",
            symbol,
            f"{future.expiration_date}",
            f"{future.notional_multiplier:.2f}",
            conditional_color(fmt(price), round=False),
            conditional_color(bp),
            f"{percent:.2f}%",
            conditional_color(fees),
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