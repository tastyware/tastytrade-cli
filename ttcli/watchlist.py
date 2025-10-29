from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from itertools import islice
from typing import Annotated, Any, Iterable

from rich.console import Console
from rich.table import Table
from tastytrade.instruments import FutureMonthCode, FutureProduct
from tastytrade.market_data import MarketData, get_market_data_by_type
from tastytrade.metrics import MarketMetricInfo, get_market_metrics
from tastytrade.order import InstrumentType
from tastytrade.utils import today_in_new_york
from tastytrade.watchlists import PrivateWatchlist, PublicWatchlist
from typer import Option
from yaspin import yaspin

from ttcli.portfolio import get_indicators
from ttcli.utils import ZERO, AsyncTyper, RenewableSession, conditional_color

watchlist = AsyncTyper(
    help="Show prices and metrics for symbols in a watchlist.", no_args_is_help=True
)


def infer_futures_postfix(active_code: FutureMonthCode) -> str:
    today = today_in_new_york()
    current = list(FutureMonthCode)[today.month - 1]
    if current < active_code:
        year = today.year
    else:
        year = today.year + 1
    return f"{active_code.value}{year % 10}"


def batched(iterable: Iterable[Any], n: int):
    it = iter(iterable)
    while batch := list(islice(it, n)):
        yield batch


@watchlist.command(help="Show prices and metrics for symbols in a public watchlist.")
def public():
    sesh = RenewableSession()
    watchlists = PublicWatchlist.get(sesh)
    watchlists.sort(key=lambda w: w.name)
    # have user choose a watchlist
    chosen = watchlists[0]
    for i, wl in enumerate(watchlists):
        if wl.name == "tasty default":
            print(f"{i + 1}) {wl.name} (default)")
            chosen = wl
        else:
            print(f"{i + 1}) {wl.name}")
    choice = 0
    while choice not in range(1, len(watchlists) + 1):
        try:
            raw = input("Choose a watchlist: ")
            choice = int(raw)
        except ValueError:
            break
    else:
        chosen = watchlists[choice - 1]
    if not chosen.watchlist_entries:
        return
    # table settings
    console = Console()
    table = Table(header_style="bold", title_style="bold", title=chosen.name)
    table.add_column("Symbol", justify="left")
    table.add_column("Last", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("IV Rank", justify="right")
    table.add_column("Volume", justify="right")
    table_show_beta = sesh.config.getboolean("watchlist", "show-beta", fallback=False)
    table_show_yield = sesh.config.getboolean(
        "watchlist", "show-dividend-yield", fallback=False
    )
    table_show_indicators = sesh.config.getboolean(
        "watchlist", "show-indicators", fallback=False
    )
    if table_show_beta:
        table.add_column("Beta", justify="right")
    if table_show_yield:
        table.add_column("Yield %", justify="right")
    if table_show_indicators:
        table.add_column("Indicators", justify="center")
    future_symbols = {
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.FUTURE
    }
    products = [
        fp for fp in FutureProduct.get(sesh) if fp.root_symbol in future_symbols
    ]
    futures = [
        p.root_symbol + infer_futures_postfix(p.active_months[0]) for p in products
    ]
    equities = [
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.EQUITY
    ]
    cryptos = [
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.CRYPTOCURRENCY
    ]
    all_symbols = (
        [("future", f) for f in futures]
        + [("equity", e) for e in equities]
        + [("crypto", c) for c in cryptos]
    )
    with yaspin(color="green", text="Fetching metrics..."):
        data_dict: dict[str, MarketData] = {}
        for batch in batched(all_symbols, 100):
            data = get_market_data_by_type(
                sesh,
                cryptocurrencies=[s for t, s in batch if t == "crypto"],
                equities=[s for t, s in batch if t == "equity"],
                futures=[s for t, s in batch if t == "future"],
            )
            data_dict.update({d.symbol: d for d in data})
        metrics = get_market_metrics(sesh, list(data_dict.keys()))
        metrics_dict = defaultdict(
            lambda: MarketMetricInfo(
                symbol="", market_cap=ZERO, updated_at=datetime.now()
            )
        )
        metrics_dict.update({m.symbol: m for m in metrics})
    for key in sorted(data_dict):
        item = data_dict[key]
        metric = metrics_dict[key]
        row = [
            key,
            f"${item.last:.2f}",
            conditional_color(item.last - item.prev_close)
            if item.last and item.prev_close
            else "ERROR",
            str(round(100 * Decimal(metric.implied_volatility_index_rank)))
            if metric.implied_volatility_index_rank
            else "",
            str(round(item.volume or 0)),
        ]
        if table_show_beta:
            row.append(f"{metric.beta:.2f}" if metric.beta else "")
        if table_show_yield:
            row.append(
                f"{metric.dividend_yield * 100:.2f}" if metric.dividend_yield else ""
            )
        if table_show_indicators:
            indicators = get_indicators(today_in_new_york(), metric)
            row.append(indicators)
        table.add_row(*row)

    console.print(table)


@watchlist.command(help="Show prices and metrics for symbols in a private watchlist.")
def private():
    sesh = RenewableSession()
    watchlists = PrivateWatchlist.get(sesh)
    watchlists.sort(key=lambda w: w.name)
    # have user choose a watchlist
    chosen = watchlists[0]
    if len(watchlists) > 1:
        for i, wl in enumerate(watchlists):
            if wl == chosen:
                print(f"{i + 1}) {wl.name} (default)")
                chosen = wl
            else:
                print(f"{i + 1}) {wl.name}")
        choice = 0
        while choice not in range(1, len(watchlists) + 1):
            try:
                raw = input("Choose a watchlist: ")
                choice = int(raw)
            except ValueError:
                break
        else:
            chosen = watchlists[choice - 1]
    if not chosen.watchlist_entries:
        return
    # table settings
    console = Console()
    table = Table(header_style="bold", title_style="bold", title=chosen.name)
    table.add_column("Symbol", justify="left")
    table.add_column("Last", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("IV Rank", justify="right")
    table.add_column("Volume", justify="right")
    table_show_beta = sesh.config.getboolean("watchlist", "show-beta", fallback=False)
    table_show_yield = sesh.config.getboolean(
        "watchlist", "show-dividend-yield", fallback=False
    )
    table_show_indicators = sesh.config.getboolean(
        "watchlist", "show-indicators", fallback=False
    )
    if table_show_beta:
        table.add_column("Beta", justify="right")
    if table_show_yield:
        table.add_column("Yield %", justify="right")
    if table_show_indicators:
        table.add_column("Indicators", justify="center")
    future_symbols = {
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.FUTURE
    }
    products = [
        fp for fp in FutureProduct.get(sesh) if fp.root_symbol in future_symbols
    ]
    futures = [
        p.root_symbol + infer_futures_postfix(p.active_months[0]) for p in products
    ]
    equities = [
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.EQUITY
    ]
    cryptos = [
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.CRYPTOCURRENCY
    ]
    indices = [
        s["symbol"]
        for s in chosen.watchlist_entries
        if s["instrument-type"] == InstrumentType.INDEX
    ]
    all_symbols = (
        [("future", f) for f in futures]
        + [("equity", e) for e in equities]
        + [("crypto", c) for c in cryptos]
        + [("index", i) for i in indices]
    )
    with yaspin(color="green", text="Fetching metrics..."):
        data_dict: dict[str, MarketData] = {}
        for batch in batched(all_symbols, 100):
            data = get_market_data_by_type(
                sesh,
                cryptocurrencies=[s for t, s in batch if t == "crypto"],
                equities=[s for t, s in batch if t == "equity"],
                futures=[s for t, s in batch if t == "future"],
                indices=[s for t, s in batch if t == "index"],
            )
            data_dict.update({d.symbol: d for d in data})
        metrics = get_market_metrics(sesh, list(data_dict.keys()))
        metrics_dict = defaultdict(
            lambda: MarketMetricInfo(
                symbol="", market_cap=ZERO, updated_at=datetime.now()
            )
        )
        metrics_dict.update({m.symbol: m for m in metrics})
    for key in sorted(data_dict):
        item = data_dict[key]
        metric = metrics_dict[key]
        row = [
            key,
            f"${item.last:.2f}",
            conditional_color(item.last - item.prev_close)
            if item.last and item.prev_close
            else "ERROR",
            str(round(100 * Decimal(metric.implied_volatility_index_rank)))
            if metric.implied_volatility_index_rank
            else "",
            str(round(item.volume or 0)),
        ]
        if table_show_beta:
            row.append(f"{metric.beta:.2f}" if metric.beta else "")
        if table_show_yield:
            row.append(
                f"{metric.dividend_yield * 100:.2f}" if metric.dividend_yield else ""
            )
        if table_show_indicators:
            indicators = get_indicators(today_in_new_york(), metric)
            row.append(indicators)
        table.add_row(*row)

    console.print(table)


@watchlist.command(help="Add a symbol to a private watchlist.", no_args_is_help=True)
async def add(
    name: str,
    symbol: str,
    type: Annotated[
        InstrumentType,
        Option("--type", "-t", help="Type of instrument, defaults to 'Equity'"),
    ] = InstrumentType.EQUITY,
):
    sesh = RenewableSession()
    wl = PrivateWatchlist.get(sesh, name)
    wl.add_symbol(symbol, type)
    wl.update(sesh)


@watchlist.command(
    help="Remove a symbol from a private watchlist.", no_args_is_help=True
)
async def remove(
    name: str,
    symbol: str,
    type: Annotated[
        InstrumentType,
        Option("--type", "-t", help="Type of instrument, defaults to 'Equity'"),
    ] = InstrumentType.EQUITY,
):
    sesh = RenewableSession()
    wl = PrivateWatchlist.get(sesh, name)
    wl.remove_symbol(symbol, type)
    wl.update(sesh)


@watchlist.command(help="Create a new private watchlist.", no_args_is_help=True)
async def create(name: str):
    sesh = RenewableSession()
    wl = PrivateWatchlist(name=name)
    wl.add_symbol("VIX", InstrumentType.INDEX)
    wl.upload(sesh)


@watchlist.command(help="Delete a private watchlist.", no_args_is_help=True)
async def delete(name: str):
    sesh = RenewableSession()
    PrivateWatchlist.remove(sesh, name)
