import os
import tempfile
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Annotated

from pygnuplot.gnuplot import Gnuplot
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Candle
from tastytrade.utils import NYSE, TZ, now_in_new_york
from typer import Option

from ttcli.utils import AsyncTyper, RenewableSession

plot = AsyncTyper(help="Plot candle charts, portfolio P&L, or net liquidating value.")
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


@plot.command(help="Plot candle chart for the given symbol.")
async def stock(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
):
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
    start_time = datetime.combine(start_day, time(9, 30), TZ)
    sesh = RenewableSession()
    candles: list[str] = []
    ts = round(start_time.timestamp() * 1000)
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
