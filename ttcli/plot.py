import os
import shutil
import tempfile
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Annotated

from pygnuplot.gnuplot import Gnuplot
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Candle
from tastytrade.instruments import Cryptocurrency, Future, FutureProduct
from tastytrade.utils import NYSE, TZ, now_in_new_york
from typer import Option
from yaspin import yaspin

from ttcli.utils import AsyncTyper, RenewableSession, print_error

plot = AsyncTyper(help="Plot candle charts for any symbol.", no_args_is_help=True)
fmt = "%Y-%m-%d %H:%M:%S"


class CandleType(str, Enum):
    MINUTE = "1m"
    FIVE_MINUTES = "5m"
    TEN_MINUTES = "10m"
    FIFTEEN_MINUTES = "15m"
    HALF_HOUR = "30m"
    HOUR = "1h"
    DAY = "1d"
    MONTH = "1mo"
    YEAR = "1y"


def get_start_time(width: CandleType) -> datetime:
    now = now_in_new_york()
    today = now.date()
    end = today if now.time() > time(9, 30) else today - timedelta(days=1)
    if width == CandleType.DAY:
        valid_days = NYSE.valid_days(today - timedelta(days=30), end).to_pydatetime()  # type: ignore
        start_day = valid_days[0].date()
    elif width == CandleType.MONTH:
        valid_days = NYSE.valid_days(today - timedelta(days=365), end).to_pydatetime()  # type: ignore
        start_day = valid_days[0].date()
    elif width == CandleType.YEAR:
        valid_days = NYSE.valid_days(today - timedelta(days=3650), end).to_pydatetime()  # type: ignore
        start_day = valid_days[0].date()
    else:
        valid_days = NYSE.valid_days(today - timedelta(days=5), end).to_pydatetime()  # type: ignore
        start_day = valid_days[-1].date()
    return datetime.combine(start_day, time(9, 30), TZ)


def gnuplot(sesh: RenewableSession, symbol: str, candles: list[str]) -> None:
    if not shutil.which("gnuplot"):
        print_error(
            "Please install gnuplot on your system to use the plot module: "
            "[link=http://www.gnuplot.info]http://www.gnuplot.info[/link]"
        )
        return
    gnu = Gnuplot()
    tmp = tempfile.NamedTemporaryFile(delete=False)
    with open(tmp.name, "w") as f:
        f.write("\n".join(candles))
    first = candles[0].split(",")[0]
    last = candles[-1].split(",")[0]
    total_time = datetime.strptime(last, fmt) - datetime.strptime(first, fmt)
    boxwidth = int(total_time.total_seconds() / len(candles) * 0.5)
    font = sesh.config.get("plot", "font", fallback="Courier New")
    font_size = sesh.config.getint("plot", "font-size", fallback=11)
    gnu.set(
        terminal=f"kittycairo transparent font '{font},{font_size}'",
        xdata="time",
        timefmt=f'"{fmt}"',
        xrange=f'["{first}":"{last}"]',
        yrange="[*:*]",
        datafile='separator ","',
        palette="defined (-1 '#D32F2F', 1 '#26BE81')",
        cbrange="[-1:1]",
        style="fill solid noborder",
        boxwidth=f"{boxwidth} absolute",
        title=f'"{symbol}" textcolor rgb "white"',
        border="31 lc rgb 'white'",
        xtics="textcolor rgb 'white'",
        ytics="textcolor rgb 'white'",
    )
    gnu.unset("colorbox")
    os.system("clear")
    gnu.plot(
        f"'{tmp.name}' using (strptime('{fmt}', strcol(1))):2:4:3:5:($5 < $2 ? -1 : 1) with candlesticks palette notitle"
    )
    _ = input()
    os.system("clear")


@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def stock(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
):
    sesh = RenewableSession()
    candles: list[str] = []
    start_time = get_start_time(width)
    ts = round(start_time.timestamp() * 1000)
    with yaspin(color="green", text="Fetching candles..."):
        async with DXLinkStreamer(sesh) as streamer:
            await streamer.subscribe_candle([symbol], width.value, start_time)
            async for candle in streamer.listen(Candle):
                if candle.close:
                    date_str = datetime.strftime(
                        datetime.fromtimestamp(candle.time / 1000, TZ), fmt
                    )
                    candles.append(
                        f"{date_str},{candle.open},{candle.high},{candle.low},{candle.close}",
                    )
                if candle.time == ts:
                    break
    candles.sort()
    gnuplot(sesh, symbol, candles)


@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def crypto(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
):
    sesh = RenewableSession()
    symbol = symbol.upper()
    if "USD" not in symbol:
        symbol += "/USD"
    elif "/" not in symbol:
        symbol = symbol.split("USD")[0] + "/USD"
    crypto = Cryptocurrency.get(sesh, symbol)
    candles: list[str] = []
    start_time = get_start_time(width)
    ts = round(start_time.timestamp() * 1000)
    if not crypto.streamer_symbol:
        raise Exception("Missing streamer symbol for instrument!")
    with yaspin(color="green", text="Fetching candles..."):
        async with DXLinkStreamer(sesh) as streamer:
            await streamer.subscribe_candle(
                [crypto.streamer_symbol], width.value, start_time
            )
            async for candle in streamer.listen(Candle):
                if candle.close:
                    date_str = datetime.strftime(
                        datetime.fromtimestamp(candle.time / 1000, TZ), fmt
                    )
                    candles.append(
                        f"{date_str},{candle.open},{candle.high},{candle.low},{candle.close}",
                    )
                if candle.time == ts:
                    break
    candles.sort()
    gnuplot(sesh, crypto.symbol, candles)


@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def future(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
):
    sesh = RenewableSession()
    symbol = symbol.upper()
    if symbol[0] != "/":
        symbol = "/" + symbol
    if not any(c.isdigit() for c in symbol):
        product = FutureProduct.get(sesh, symbol)
        _fmt = ",".join([f" {m.name} ({m.value})" for m in product.active_months])
        print_error(
            f"Please enter the full futures symbol!\nCurrent active months:{_fmt}"
        )
        return
    future = Future.get(sesh, symbol)
    candles: list[str] = []
    start_time = get_start_time(width)
    ts = round(start_time.timestamp() * 1000)
    with yaspin(color="green", text="Fetching candles..."):
        async with DXLinkStreamer(sesh) as streamer:
            await streamer.subscribe_candle(
                [future.streamer_symbol], width.value, start_time
            )
            async for candle in streamer.listen(Candle):
                if candle.close:
                    date_str = datetime.strftime(
                        datetime.fromtimestamp(candle.time / 1000, TZ), fmt
                    )
                    candles.append(
                        f"{date_str},{candle.open},{candle.high},{candle.low},{candle.close}",
                    )
                if candle.time == ts:
                    break
    candles.sort()
    gnuplot(sesh, future.symbol, candles)
