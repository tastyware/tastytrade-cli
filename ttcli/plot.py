import os, sys
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
from ttcli.option import chain_data_df


import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo
import shutil, tempfile, os

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
        # make the index here [0] so it shows and loads last five days and not only today
        start_day = valid_days[-1].date()
    return datetime.combine(start_day, time(9, 30), TZ)


def gnuplot(sesh: RenewableSession, symbol: str, candles: list[str], save: bool) -> None:
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
    first_dt = datetime.strptime(first, fmt)
    last_dt = datetime.strptime(last, fmt)
    total_time = last_dt - first_dt
    boxwidth = int(total_time.total_seconds() / len(candles) * 0.5)
    padding = timedelta(seconds=boxwidth)
    first_padded = (first_dt - padding).strftime(fmt)
    last_padded = (last_dt + padding).strftime(fmt)
    font = sesh.config.get("plot", "font", fallback="Courier New")
    font_size = sesh.config.getint("plot", "font-size", fallback=11)
    
    if sys.platform == "win32":
        terminal = "sixel size 1024,768"
        clear = "cls"
        
    elif sys.platform == "linux" or sys.platform == "darwin":
        terminal = f"kittycairo transparent font '{font},{font_size}'"
        clear = "clear"

    gnu.set(
        terminal=terminal,
        xdata="time",
        timefmt=f'"{fmt}"',
        xrange=f'["{first_padded}":"{last_padded}"]',
        yrange="[*:*]",
        datafile='separator ","',
        palette="defined (-1 '#D32F2F', 1 '#26BE81')",
        cbrange="[-1:1]",
        style="fill solid noborder",
        boxwidth=f"{boxwidth} absolute",
        title=f'"{symbol}" textcolor rgb "white"',
        border="3 lc rgb 'white'",
        xtics="nomirror rotate by -45 textcolor rgb 'white' scale 0",
        ytics="nomirror textcolor rgb 'white' scale 0",
    )
    gnu.unset("colorbox")
    os.system(clear)
    gnu.plot(
        f"'{tmp.name}' using (strptime('{fmt}', strcol(1))):2:4:3:5:($5 < $2 ? -1 : 1) with candlesticks palette notitle"
    )

    PLOT_DIR = "plots"
    timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    filename = f"{PLOT_DIR}/{symbol}/{timestamp}.png"

    if save:
        # Save as PNG
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        gnu.cmd(f"set terminal pngcairo size 1200,800 enhanced font 'Sans,12' background rgb 'black'")
        gnu.cmd(f"set output '{filename}'")
        gnu.plot(
                f"'{tmp.name}' using (strptime('{fmt}', strcol(1))):2:4:3:5:($5 < $2 ? -1 : 1) with candlesticks palette notitle"
            )        
        gnu.cmd("set output")  # close and save
        print("Plot saved in: ", filename)
    _ = input()
    os.system(clear)


def gnu_plot_greeks_histogram(
        df,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels,
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
        exp, 
        ticker,
        lower_bound,
        upper_bound,
        greek_filter = None,
        save = False

):

    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    filenames = []    
    GREEKS = [greek_filter] if greek_filter else ["delta", "gamma", "vanna", "charm"]
    VISUALIZATIONS = {
    "delta": ["Absolute Delta Exposure", "Delta Exposure By Calls/Puts", "Delta Exposure Profile"],
    "gamma": ["Absolute Gamma Exposure", "Gamma Exposure By Calls/Puts", "Gamma Exposure Profile"],
    "vanna": ["Absolute Vanna Exposure", "Implied Volatility Average", "Vanna Exposure Profile"],
    "charm": ["Absolute Charm Exposure", "Charm Exposure Profile"],
    }
    PLOT_DIR = "plots"
    timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    
    if sys.platform == "win32":
        terminal = "sixel size 1024,768"
        clear = "cls"
        
    elif sys.platform == "linux" or sys.platform == "darwin":
        terminal = f"kittycairo transparent font '{font},{font_size}'"
        clear = "clear"

    for greek in GREEKS:
        for value in VISUALIZATIONS[greek]:
            try:
                
                date_condition = not "Profile" in value
                if date_condition:
                    if not isinstance(from_strike, (int, float)) or not isinstance(to_strike, (int, float)):
                        print("Invalid: ", greek, value)
                        continue
                    df_agg = df.groupby(["strike_price"]).sum(numeric_only=True)
                    strikes_sorted = np.sort(df_agg.index.values)
                    strike_steps = np.diff(strikes_sorted)
                    if len(strike_steps) == 0:
                        step = 1  # fallback in case of just one strike
                    else:
                        step = np.min(strike_steps[strike_steps > 0])
                    
                    lower_strike = max(np.floor(lower_bound / step) * step, df_agg.index.min())
                    upper_strike = min(np.ceil(upper_bound / step) * step, df_agg.index.max())
                    strikes = np.arange(lower_strike, upper_strike + step, step)
                    df_agg = df_agg.reindex(strikes, method='ffill').fillna(0)
                    if df_agg.empty:
                        continue
                else:
                    df_agg = df.groupby(["expiration_date"]).sum(numeric_only=True)
                    if df_agg.empty:
                        continue

                if "Calls/Puts" in value or value == "Implied Volatility Average":
                    key = "strike" if date_condition else "exp"
                    if not (isinstance(call_ivs, dict) and isinstance(put_ivs, dict) and
                            key in call_ivs and key in put_ivs):
                        continue
                    call_ivs_data, put_ivs_data = call_ivs[key], put_ivs[key]
                else:
                    call_ivs_data, put_ivs_data = None, None


                name = value.split()[1] if "Absolute" in value else value.split()[0]
                
                if "Absolute" in value:
                    filename = f"{PLOT_DIR}/{ticker}/{exp}/{greek}/{value.replace(' ', '_')}/{timestamp}.png"
                    agg_by_strike = df_agg[f"total_{name.lower()}"]
                    
                    max_positive_strike = agg_by_strike.idxmax()
                    max_negative_strike = agg_by_strike.idxmin()
                    
                    # Find the transition point from positive to negative that it's close to the spot_price, ignore outliers
                    signs = np.sign(agg_by_strike.values)

                    # Find same sign
                    runs = []
                    if len(signs) > 0:
                        current_sign = signs[0]
                        start = 0
                        for j in range(1, len(signs)):
                            if signs[j] != current_sign:
                                runs.append((current_sign, start, j-1))
                                current_sign = signs[j]
                                start = j
                        runs.append((current_sign, start, len(signs)-1))

                    # Find valid transitions of sign
                    zero_strikes = []
                    for r in range(1, len(runs)):
                        prev_run = runs[r-1]
                        curr_run = runs[r]
                        prev_len = prev_run[2] - prev_run[1] + 1
                        curr_len = curr_run[2] - curr_run[1] + 1
                        if prev_len >= 2 and curr_len >= 2 and prev_run[0] != curr_run[0] and prev_run[0] != 0 and curr_run[0] != 0:
                            idx1 = prev_run[2]
                            idx2 = curr_run[1]
                            strike1 = agg_by_strike.index[idx1]
                            value1 = agg_by_strike.iloc[idx1]
                            strike2 = agg_by_strike.index[idx2]
                            value2 = agg_by_strike.iloc[idx2]
                            # Interpolate the position of the zero strike
                            zero_strike = strike2 - ((strike2 - strike1) * value2 / (value2 - value1))
                            zero_strikes.append(zero_strike)

                    # Find the closest one to the spot price
                    if zero_strikes:
                        zero_strikes = np.array(zero_strikes)
                        closest_idx = np.argmin(np.abs(zero_strikes - spot_price))
                        zero_strike = zero_strikes[closest_idx]
                    else:
                        zero_strike = None               
                    
                    # Net Exposure
                    net_value = agg_by_strike.sum() * 100
                    
                    if not shutil.which("gnuplot"):
                        print("Please install gnuplot to use this plot.")
                        return
                    
                    gnu = Gnuplot()
                    
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dat")
                    with open(tmp.name, "w") as f:
                        for strike, exposure in zip(df_agg.index, agg_by_strike):
                            f.write(f"{strike} {exposure}\n")

                    strikes = df_agg.index.to_numpy()
                    step = strikes[1] - strikes[0] if len(strikes) > 1 else 1
                    boxwidth = step * 0.9

                    # Set up gnuplot
                    gnu.set(
                        terminal=terminal,
                        style="fill solid",
                        boxwidth=f"{boxwidth} absolute",
                        border="3 lc rgb 'white'",
                        title=f'"{name} Exposure by Strike" textcolor rgb "white"',
                        xtics="textcolor rgb 'white'",
                        ytics="textcolor rgb 'white'",
                        grid="xtics ytics lc rgb 'black'",
                        xrange=f"[{strikes.min()-step}:{strikes.max()+step}]",
                        object="rectangle from screen 0,0 to screen 1,1 behind fc rgb 'black' fillstyle solid 1.0",
                    )   
            
                    # Horizontal line on 0
                    gnu.cmd("set arrow from graph 0, first 0 to graph 1, first 0 nohead lc rgb 'white' lw 1")

                    # Spot price
                    gnu.cmd(f"set arrow from {spot_price}, graph 0 to {spot_price}, graph 1 nohead lc rgb '#C0C0C0' lw 0.9 dt 2")
                    gnu.cmd(f"set label 'Spot price: {spot_price:.2f}' at graph 0.02, graph 0.79 tc rgb '#C0C0C0'")

                    if not pd.isna(max_positive_strike):
                        gnu.cmd(
                            f"set arrow from {max_positive_strike}, graph 0 to {max_positive_strike}, graph 1 nohead lc rgb '#00e400' lw 1.2 dt 2"
                        )
                        gnu.cmd(f"set label 'Max: {max_positive_strike:.2f}' at graph 0.02, graph 0.83 tc rgb '#00e400'")
                    if not pd.isna(max_negative_strike):
                        gnu.cmd(
                            f"set arrow from {max_negative_strike}, graph 0 to {max_negative_strike}, graph 1 nohead lc rgb '#da0000' lw 1.2 dt 2"
                        )
                        gnu.cmd(f"set label 'Min: {max_negative_strike:.2f}' at graph 0.02, graph 0.87 tc rgb '#da0000'")


                    if zero_strike is not None:
                        gnu.cmd(f"set arrow from {zero_strike}, graph 0 to {zero_strike}, graph 1 nohead lc rgb '#eeee00' lw 1.2 dt 2")
                        gnu.cmd(f"set label 'Flip: {zero_strike:.2f}' at graph 0.02, graph 0.91 tc rgb '#eeee00'")
                        
                    net_color = "#00e400" if net_value > 0 else "#da0000" if net_value < 0 else "white"
                    gnu.cmd(f"set label 'Net {name}: {net_value:,.2f}' at graph 0.02, graph 0.95 tc rgb '{net_color}'")

                    # Plot
                    os.system(clear)
                    gnu.plot(f"'{tmp.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#7bbad7' notitle")

                    if save:
                        # Save as PNG
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        gnu.cmd(f"set terminal pngcairo size 1200,800 enhanced font 'Sans,12' background rgb 'black'")
                        gnu.cmd(f"set output '{filename}'")
                        gnu.plot(f"'{tmp.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#7bbad7' notitle")
                        gnu.cmd("set output")  # close and save
                        filenames.append(filename)

                    input("Press Enter to close...")
                    os.system(clear)
                                        
                elif "Calls/Puts" in value:
                    value = value.replace('Calls/Puts', 'Calls Puts')
                    filename = f"{PLOT_DIR}/{ticker}/{exp}/{greek}/{value.replace(' ', '_')}/{timestamp}.png"
                    agg_by_strike = df_agg[f"total_{name.lower()}"]
                    
                    max_positive_strike = agg_by_strike.idxmax()
                    max_negative_strike = agg_by_strike.idxmin()
                    
                    signs = np.sign(agg_by_strike.values)

                    runs = []
                    if len(signs) > 0:
                        current_sign = signs[0]
                        start = 0
                        for j in range(1, len(signs)):
                            if signs[j] != current_sign:
                                runs.append((current_sign, start, j-1))
                                current_sign = signs[j]
                                start = j
                        runs.append((current_sign, start, len(signs)-1))

                    zero_strikes = []
                    for r in range(1, len(runs)):
                        prev_run = runs[r-1]
                        curr_run = runs[r]
                        prev_len = prev_run[2] - prev_run[1] + 1
                        curr_len = curr_run[2] - curr_run[1] + 1
                        if prev_len >= 2 and curr_len >= 2 and prev_run[0] != curr_run[0] and prev_run[0] != 0 and curr_run[0] != 0:
                            idx1 = prev_run[2]
                            idx2 = curr_run[1]
                            strike1 = agg_by_strike.index[idx1]
                            value1 = agg_by_strike.iloc[idx1]
                            strike2 = agg_by_strike.index[idx2]
                            value2 = agg_by_strike.iloc[idx2]
                            zero_strike = strike2 - ((strike2 - strike1) * value2 / (value2 - value1))
                            zero_strikes.append(zero_strike)
                    
                    if zero_strikes:
                        zero_strikes = np.array(zero_strikes)
                        closest_idx = np.argmin(np.abs(zero_strikes - spot_price))
                        zero_strike = zero_strikes[closest_idx]
                    else:
                        zero_strike = None

                    if not shutil.which("gnuplot"):
                        print("Please install gnuplot to use this plot.")
                        return
                    
                    gnu = Gnuplot()

                    tmp_calls = tempfile.NamedTemporaryFile(delete=False, suffix=".dat")
                    with open(tmp_calls.name, "w") as f:
                        for strike, exposure in zip(df_agg.index, df_agg[f"call_{name[:1].lower()}ex"]):
                            f.write(f"{strike} {exposure}\n")

                    tmp_puts = tempfile.NamedTemporaryFile(delete=False, suffix=".dat")
                    with open(tmp_puts.name, "w") as f:
                        for strike, exposure in zip(df_agg.index, df_agg[f"put_{name[:1].lower()}ex"]):
                            f.write(f"{strike} {exposure}\n")

                    strikes = df_agg.index.to_numpy()
                    step = strikes[1] - strikes[0] if len(strikes) > 1 else 1
                    boxwidth = step * 0.9

                    gnu.set(
                        terminal=terminal,
                        style="fill solid",
                        boxwidth=f"{boxwidth} absolute",
                        border="3 lc rgb 'white'",
                        title=f'"{name} Calls vs Puts" textcolor rgb "white"',
                        xtics="textcolor rgb 'white'",
                        ytics="textcolor rgb 'white'",
                        grid="xtics ytics lc rgb 'black'",
                        xrange=f"[{strikes.min()-step}:{strikes.max()+step}]",
                        object="rectangle from screen 0,0 to screen 1,1 behind fc rgb 'black' fillstyle solid 1.0",
                    )

                    gnu.cmd("set arrow from graph 0, first 0 to graph 1, first 0 nohead lc rgb 'white' lw 1")
                    
                    gnu.cmd(f"set arrow from {spot_price}, graph 0 to {spot_price}, graph 1 nohead lc rgb '#C0C0C0' lw 0.9 dt 2")
                    gnu.cmd(f"set label 'Spot price: {spot_price:.2f}' at graph 0.02, graph 0.79 tc rgb '#C0C0C0'")

                    if not pd.isna(max_positive_strike):
                        gnu.cmd(f"set arrow from {max_positive_strike}, graph 0 to {max_positive_strike}, graph 1 nohead lc rgb '#00e400' lw 1.2 dt 2")
                        gnu.cmd(f"set label 'Max: {max_positive_strike:.2f}' at graph 0.02, graph 0.83 tc rgb '#00e400'")

                    if not pd.isna(max_negative_strike):
                        gnu.cmd(f"set arrow from {max_negative_strike}, graph 0 to {max_negative_strike}, graph 1 nohead lc rgb '#da0000' lw 1.2 dt 2")
                        gnu.cmd(f"set label 'Min: {max_negative_strike:.2f}' at graph 0.02, graph 0.87 tc rgb '#da0000'")

                    if zero_strike is not None:
                        gnu.cmd(f"set arrow from {zero_strike}, graph 0 to {zero_strike}, graph 1 nohead lc rgb '#eeee00' lw 1.2 dt 2")
                        gnu.cmd(f"set label 'Flip: {zero_strike:.2f}' at graph 0.02, graph 0.91 tc rgb '#eeee00'")
                    
                    gnu.cmd(f"set label 'Calls ({name})' at graph 0.02, graph 0.95 tc rgb '#81d581'")
                    gnu.cmd(f"set label 'Puts ({name})' at graph 0.02, graph 0.99 tc rgb '#e57272'")

                    os.system(clear)
                    gnu.plot(
                        f"'{tmp_calls.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#81d581' title 'Calls', "
                        f"'{tmp_puts.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#e57272' title 'Puts'"
                    )

                    if save:
                        # Save as PNG
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        gnu.cmd(f"set terminal pngcairo size 1200,800 enhanced font 'Sans,12' background rgb 'black'")
                        gnu.cmd(f"set output '{filename}'")
                        gnu.plot(
                            f"'{tmp_calls.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#81d581' title 'Calls', "
                            f"'{tmp_puts.name}' using ($1+{boxwidth/2}):2 with boxes lc rgb '#e57272' title 'Puts'"
                        )
                        gnu.cmd("set output")
                        filenames.append(filename)

                    input("Press Enter to close...")
                    os.system(clear)

            except Exception as e:
                print(f"Error processing {ticker}/{exp}/{greek}/{value}: {e}")
    return filenames
         

@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def stock(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False
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
    gnuplot(sesh, symbol, candles, save)


@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def crypto(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False
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
    gnuplot(sesh, crypto.symbol, candles, save)


@plot.command(help="Plot candle chart for the given symbol.", no_args_is_help=True)
async def future(
    symbol: str,
    width: Annotated[
        CandleType, Option("--width", "-w", help="Interval of time for each candle.")
    ] = CandleType.HALF_HOUR,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False
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
    gnuplot(sesh, future.symbol, candles, save)

@plot.command(help="Plot GEX chart for the given symbol.", no_args_is_help=True)
async def gamma(
    symbol: str,
    days: Annotated[
        int, Option("--dte", "-d", help="Interval of days to calculate de gamma exposure.")
    ] = 0,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False 
):
    sesh = RenewableSession()

    exposure_data = await chain_data_df(symbol, None, days, "gamma", save)
    filenames = gnu_plot_greeks_histogram(*exposure_data)
    if save:
        print("Plots saved in ", filenames)

@plot.command(help="Plot vanna chart for the given symbol.", no_args_is_help=True)
async def vanna(
    symbol: str,
    days: Annotated[
        int, Option("--dte", "-d", help="Interval of days to calculate de gamma exposure.")
    ] = 0,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False 
):
    sesh = RenewableSession()

    exposure_data = await chain_data_df(symbol, None, days, "vanna", save)
    filenames = await gnu_plot_greeks_histogram(*exposure_data)
    if save:
        print("Plots saved in ", filenames)

@plot.command(help="Plot charm chart for the given symbol.", no_args_is_help=True)
async def charm(
    symbol: str,
    days: Annotated[
        int, Option("--dte", "-d", help="Interval of days to calculate de charm exposure.")
    ] = 0,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False 
):
    sesh = RenewableSession()

    exposure_data = await chain_data_df(symbol, None, days, "charm", save)
    filenames = gnu_plot_greeks_histogram(*exposure_data)
    if save:
        print("Plots saved in ", filenames)


@plot.command(help="Plot charm delta for the given symbol.", no_args_is_help=True)
async def delta(
    symbol: str,
    days: Annotated[
        int, Option("--dte", "-d", help="Interval of days to calculate de charm exposure.")
    ] = 0,
    save: Annotated[
        bool, Option("--save", "-s", is_flag=True, help="To save the generated plot")
    ] = False 
):
    sesh = RenewableSession()

    exposure_data = await chain_data_df(symbol, None, days, "delta", save)
    filenames = gnu_plot_greeks_histogram(*exposure_data)
    if save:
        print("Plots saved in ", filenames)