from decimal import Decimal

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote
from tastytrade.instruments import Equity
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
from tastytrade.utils import TastytradeError

from ttcli.utils import (
    ZERO,
    RenewableSession,
    get_confirmation,
    print_error,
    print_warning,
    round_to_tick_size,
)


@click.group(chain=True, help="Buy, sell, and analyze stocks/ETFs.")
async def stock():
    pass


@stock.command(help="Buy or sell stocks/ETFs.")
@click.option("--gtc", is_flag=True, help="Place a GTC order instead of a day order.")
@click.argument("symbol", type=str)
@click.argument("quantity", type=int)
async def trade(symbol: str, quantity: int, gtc: bool = False):
    sesh = RenewableSession()
    symbol = symbol.upper()
    equity = Equity.get_equity(sesh, symbol)

    def fmt(x: Decimal | None) -> Decimal:
        return round_to_tick_size(x, equity.tick_sizes or []) if x is not None else ZERO

    async with DXLinkStreamer(sesh) as streamer:
        await streamer.subscribe(Quote, [symbol])
        quote = await streamer.get_event(Quote)
        bid = quote.bidPrice
        ask = quote.askPrice
        mid = fmt((bid + ask) / Decimal(2))  # type: ignore

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
        percent = bp / nl * Decimal(100)
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
            f"${fmt(price)}",
            f"${bp:.2f}",
            f"{percent:.2f}%",
            f"${fees:.2f}",
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