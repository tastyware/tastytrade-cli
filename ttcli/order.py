from datetime import datetime
from decimal import Decimal

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote
from tastytrade.instruments import Cryptocurrency, Equity, Future, FutureProduct
from tastytrade.order import (
    InstrumentType,
    NewOrder,
    OrderAction,
    OrderTimeInForce,
    OrderType,
)
from tastytrade.utils import TastytradeError

from ttcli.utils import (
    ZERO,
    RenewableSession,
    conditional_color,
    get_confirmation,
    print_error,
    print_warning,
    round_to_tick_size,
    round_to_width,
)


@click.group(chain=True, help="View, adjust, or cancel orders.")
async def order():
    pass


@order.command(help="List, adjust, or cancel orders.")
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def live(symbol: str, quantity: int, gtc: bool = False):
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


@order.command(help="Show order history.")
@click.option(
    "--start-date",
    type=click.DateTime(["%Y-%m-%d"]),
    help="The start date for the search date range.",
)
@click.option(
    "--end-date",
    type=click.DateTime(["%Y-%m-%d"]),
    help="The end date for the search date range.",
)
@click.option("-s", "--symbol", type=str, help="Filter by underlying symbol.")
@click.option(
    "-t",
    "--type",
    type=click.Choice(list(InstrumentType)),
    help="Filter by instrument type.",
)  # type: ignore
@click.option(
    "--asc", is_flag=True, help="Sort by ascending time instead of descending."
)
async def history(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    symbol: str | None = None,
    type: InstrumentType | None = None,
    asc: bool = False,
):
    sesh = RenewableSession()
    acc = sesh.get_account()
    history = acc.get_order_history(
        sesh,
        start_date=start_date.date() if start_date else None,
        end_date=end_date.date() if end_date else None,
        underlying_symbol=symbol if symbol and symbol[0] != "/" else None,
        futures_symbol=symbol if symbol and symbol[0] == "/" else None,
        underlying_instrument_type=type,
    )
    if asc:
        history.reverse()
    console = Console()
    table = Table(
        show_header=True,
        header_style="bold",
        title_style="bold",
        title=f"Order history for account {acc.nickname} ({acc.account_number})",
    )
    table.add_column("Date/Time")
    # table.add_column("Order ID")  # option
    table.add_column("Root Symbol")
    table.add_column("Type")
    # table.add_column("Time in Force")  # option
    table.add_column("Price", justify="right")
    table.add_column("Status")
    # leg info
    table.add_column("Quantity")
    table.add_column("Action")
    table.add_column("Symbol")
    for order in history:
        table.add_row(
            *[
                order.updated_at.strftime("%Y-%m-%d %H:%M"),
                order.underlying_symbol,
                order.order_type.value,
                conditional_color(order.price or ZERO),
                order.status.value,
                str(order.legs[0].quantity),
                order.legs[0].action.value,
                order.legs[0].symbol,
            ],
            end_section=(len(order.legs) == 1),
        )
        for i in range(1, len(order.legs)):
            table.add_row(
                *[
                    "",
                    "",
                    "",
                    "",
                    "",
                    str(order.legs[i].quantity),
                    order.legs[i].action.value,
                    order.legs[i].symbol,
                ],
                end_section=(i == len(order.legs) - 1),
            )
    console.print(table)
