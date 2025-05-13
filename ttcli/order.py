from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from math import gcd
from typing import Annotated

from rich.console import Console
from rich.table import Table
from tastytrade.market_data import get_market_data_by_type
from tastytrade.order import InstrumentType, NewOrder, OrderStatus
from tastytrade.utils import TastytradeError
from typer import Option, Typer
from yaspin import yaspin

from ttcli.utils import (
    ZERO,
    RenewableSession,
    conditional_color,
    conditional_quantity,
    get_confirmation,
    print_error,
)

order = Typer(help="List, adjust, or cancel orders.", no_args_is_help=True)


@order.command(help="List, adjust, or cancel live orders.")
def live(
    all: Annotated[
        bool, Option("--all", help="Show orders for all accounts, not just one.")
    ] = False,
):
    sesh = RenewableSession()
    if all:
        orders = []
        for acc in sesh.accounts:
            orders.extend(acc.get_live_orders(sesh))
    else:
        acc = sesh.get_account()
        orders = acc.get_live_orders(sesh)
    orders = [
        o
        for o in orders
        if o.status == OrderStatus.LIVE or o.status == OrderStatus.RECEIVED
    ]
    instrument_dict: dict[InstrumentType, set[str]] = defaultdict(set)
    for o in orders:
        for leg in o.legs:
            instrument_dict[leg.instrument_type].add(leg.symbol)
    data = get_market_data_by_type(
        sesh,
        cryptocurrencies=list(instrument_dict[InstrumentType.CRYPTOCURRENCY]) or None,
        equities=list(instrument_dict[InstrumentType.EQUITY]) or None,
        futures=list(instrument_dict[InstrumentType.FUTURE]) or None,
        future_options=list(instrument_dict[InstrumentType.FUTURE_OPTION]) or None,
        options=list(instrument_dict[InstrumentType.EQUITY_OPTION]) or None,
    )
    marks = {d.symbol: d.mark for d in data}
    console = Console()
    table = Table(
        show_header=True,
        header_style="bold",
        title_style="bold",
        title="Live Orders",
    )
    table.add_column("#", justify="left")
    if all:
        table.add_column("Account")
    table.add_column("Date/Time")
    table.add_column("Order ID")
    table.add_column("Symbol")
    table.add_column("Type")
    table.add_column("TIF")
    table.add_column("Price", justify="right")
    table.add_column("Mark", justify="right")
    # leg info
    table.add_column("Qty", justify="right")
    table.add_column("Legs")

    for i, order in enumerate(orders):
        total_price = ZERO
        # handle ratio spreads
        quantity = gcd(*[int(leg.quantity or 0) for leg in order.legs])
        for leg in order.legs:
            if leg.quantity:
                m = 1 if "Sell" in leg.action.value else -1
                total_price += m * marks[leg.symbol] * leg.quantity / quantity
        row = [
            str(i + 1),
            order.updated_at.strftime("%Y-%m-%d %H:%M"),
            str(order.id),
            order.underlying_symbol,
            order.order_type.value,
            order.time_in_force.value,
            conditional_color(order.price) if order.price else "--",
            conditional_color(total_price),
            conditional_quantity(order.legs[0].quantity or ZERO, order.legs[0].action),
            order.legs[0].symbol,
        ]
        if all:
            row.insert(1, order.account_number)
        table.add_row(*row, end_section=(len(order.legs) == 1))
        for i in range(1, len(order.legs)):
            row = [
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                conditional_quantity(
                    order.legs[i].quantity or ZERO, order.legs[i].action
                ),
                order.legs[i].symbol,
            ]
            if all:
                row.insert(1, "")
            table.add_row(*row, end_section=(i == len(order.legs) - 1))
    console.print(table)
    if not get_confirmation("Modify an order? y/N ", default=False):
        return
    if len(orders) > 1:
        order_id = input("Enter the number (not the order ID) of the order to modify: ")
        if not order_id:
            return
        order = orders[int(order_id) - 1]
    else:
        print("Auto-selected the only order available.")
        order = orders[0]
    acc = next(a for a in sesh.accounts if a.account_number == order.account_number)
    price = input("Enter a new price for the order, or nothing to cancel it: $")
    if not price:  # cancel the order
        try:
            acc.delete_order(sesh, order.id)
            print(f"Order {order.id} cancelled successfully!")
        except TastytradeError as e:
            print_error(str(e))
        return
    sign = -1 if (order.price or 0) < 0 else 1
    # modify the order, ensuring price keeps the same sign
    new_order = NewOrder(
        time_in_force=order.time_in_force,
        order_type=order.order_type,
        legs=order.legs,
        gtc_date=order.gtc_date,
        stop_trigger=Decimal(order.stop_trigger) if order.stop_trigger else None,
        price=sign * abs(Decimal(price)),
    )
    try:
        acc.replace_order(sesh, order.id, new_order)
    except TastytradeError as e:
        print_error(str(e))


@order.command(help="Show order history.")
def history(
    start_date: Annotated[
        datetime | None,
        Option("--start", help="The start date for the search date range."),
    ] = None,
    end_date: Annotated[
        datetime | None, Option("--end", help="The end date for the search date range.")
    ] = None,
    symbol: Annotated[
        str | None, Option("--symbol", "-s", help="Filter by underlying symbol.")
    ] = None,
    type: Annotated[
        InstrumentType | None, Option("--type", "-t", help="Filter by instrument type.")
    ] = None,
    asc: Annotated[
        bool, Option("--asc", help="Sort by ascending time instead of descending.")
    ] = False,
    status: Annotated[
        list[OrderStatus] | None, Option("--status", help="Filter by order status.")
    ] = None,
):
    sesh = RenewableSession()
    acc = sesh.get_account()
    with yaspin(color="green", text="Fetching history..."):
        history = acc.get_order_history(
            sesh,
            start_date=start_date.date() if start_date else None,
            end_date=end_date.date() if end_date else None,
            underlying_symbol=symbol if symbol and symbol[0] != "/" else None,
            futures_symbol=symbol if symbol and symbol[0] == "/" else None,
            underlying_instrument_type=type,
            statuses=status,
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
    table.add_column("Order ID")
    table.add_column("Symbol")
    table.add_column("Type")
    table.add_column("TIF")
    table.add_column("Status")
    table.add_column("Price", justify="right")
    # leg info
    table.add_column("Qty", justify="right")
    table.add_column("Legs")
    for order in history:
        table.add_row(
            *[
                order.updated_at.strftime("%Y-%m-%d %H:%M"),
                str(order.id),
                order.underlying_symbol,
                order.order_type.value,
                order.time_in_force.value,
                order.status.value,
                conditional_color(order.price) if order.price else "--",
                str(
                    (order.legs[0].quantity or 0)
                    * (-1 if "Sell" in order.legs[0].action.value else 1)
                ),
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
                    "",
                    "",
                    str(
                        (order.legs[i].quantity or 0)
                        * (-1 if "Sell" in order.legs[i].action.value else 1)
                    ),
                    order.legs[i].symbol,
                ],
                end_section=(i == len(order.legs) - 1),
            )
    console.print(table)
