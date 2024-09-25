from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import cast

import asyncclick as click
from rich.console import Console
from rich.table import Table
from tastytrade import (DXLinkStreamer, Equity, NewOrder, OrderAction,
                        OrderTimeInForce, PriceEffect)
from tastytrade.dxfeed import EventType, Greeks, Summary, Trade
from tastytrade.instruments import Cryptocurrency, Future, FutureOption, Option
from tastytrade.metrics import MarketMetricInfo, get_market_metrics
from tastytrade.order import (InstrumentType, OrderType,
                              TradeableTastytradeJsonDataclass)
from tastytrade.utils import today_in_new_york

from ttcli.utils import (RenewableSession, get_confirmation, print_warning,
                         test_order_handle_errors)


@click.group(help='View positions and stats for your portfolio.')
async def portfolio():
    pass


def conditional_color(value: Decimal, dollars: bool = True) -> str:
    d = '$' if dollars else ''
    return (f'[red]{d}{value:.2f}[/red]'
            if value < 0
            else f'[green]{d}{value:.2f}[/green]')


def get_indicators(today: date, metrics: MarketMetricInfo) -> str:
    indicators = []
    if metrics.dividend_next_date and metrics.dividend_next_date > today:
        days_til = (metrics.dividend_next_date - today).days
        indicators.append(f'[deep_sky_blue2]D {days_til}[/deep_sky_blue2]')
    if (
        metrics.earnings and
        metrics.earnings.expected_report_date and
        metrics.earnings.expected_report_date > today
    ):
        days_til = (metrics.earnings.expected_report_date - today).days
        indicators.append(f'[medium_orchid]E {days_til}[/medium_orchid]')
    return ' '.join(indicators) if indicators else ''


def get_day_open(summary: Summary) -> Decimal:
    return summary.dayOpenPrice or summary.prevDayClosePrice or Decimal(0)


@portfolio.command(help='View your current positions.')
@click.option('--all', is_flag=True, help='Show positions for all accounts.')
async def positions(all: bool = False):
    sesh = RenewableSession()
    console = Console()
    table = Table(header_style='bold', title_style='bold', title='Positions')
    table.add_column('#', justify='left')
    today = today_in_new_york()
    if all:
        table.add_column('Account', justify='left')
        positions = []
        account_dict = {}
        for account in sesh.accounts:
            account_dict[account.account_number] = account.nickname
            positions.extend(account.get_positions(sesh, include_marks=True))
    else:
        account = sesh.get_account()
        positions = account.get_positions(sesh, include_marks=True)
    positions.sort(key=lambda pos: pos.symbol)
    pos_dict = {pos.symbol: pos for pos in positions}
    options_symbols = [
        p.symbol
        for p in positions
        if p.instrument_type == InstrumentType.EQUITY_OPTION
    ]
    options = (Option.get_options(sesh, options_symbols)
               if options_symbols else [])
    options_dict = {o.symbol: o for o in options}
    future_options_symbols = [
        p.symbol
        for p in positions
        if p.instrument_type == InstrumentType.FUTURE_OPTION
    ]
    future_options = (
        FutureOption.get_future_options(sesh, future_options_symbols)
        if future_options_symbols else []
    )
    future_options_dict = {fo.symbol: fo for fo in future_options}
    futures_symbols = [
        p.symbol
        for p in positions
        if p.instrument_type == InstrumentType.FUTURE
    ] + [fo.underlying_symbol for fo in future_options]
    futures = (Future.get_futures(sesh, futures_symbols)
               if futures_symbols else [])
    futures_dict = {f.symbol: f for f in futures}
    crypto_symbols = [
        p.symbol
        for p in positions
        if p.instrument_type == InstrumentType.CRYPTOCURRENCY
    ]
    cryptos = (Cryptocurrency.get_cryptocurrencies(sesh, crypto_symbols)
               if crypto_symbols else [])
    crypto_dict = {c.symbol: c for c in cryptos}
    greeks_symbols = ([o.streamer_symbol for o in options] +
                      [fo.streamer_symbol for fo in future_options])
    equity_symbols = [p.symbol for p in positions
                      if p.instrument_type == InstrumentType.EQUITY]
    equities = Equity.get_equities(sesh, equity_symbols)
    equity_dict = {e.symbol: e for e in equities}
    streamer_symbols = list(set(
        [o.underlying_symbol for o in options] +
        [c.streamer_symbol for c in cryptos] +
        equity_symbols +
        [f.streamer_symbol for f in futures]
    )) + greeks_symbols
    # get greeks for options
    greeks_dict = {}
    summary_dict = {}
    async with DXLinkStreamer(sesh) as streamer:
        if greeks_symbols != []:
            await streamer.subscribe(EventType.GREEKS, greeks_symbols)  # type: ignore
        await streamer.subscribe(EventType.SUMMARY, streamer_symbols)  # type: ignore
        await streamer.subscribe(EventType.TRADE, ['SPY'])
        if greeks_symbols != []:
            async for greeks in streamer.listen(EventType.GREEKS):
                greeks = cast(Greeks, greeks)
                greeks_dict[greeks.eventSymbol] = greeks
                if len(greeks_dict) == len(greeks_symbols):
                    break
        async for summary in streamer.listen(EventType.SUMMARY):
            summary = cast(Summary, summary)
            summary_dict[summary.eventSymbol] = summary
            if len(summary_dict) == len(streamer_symbols):
                break
        spy = await streamer.get_event(EventType.TRADE)
        spy = cast(Trade, spy)
    spy_price = spy.price or 0
    tt_symbols = set(pos.symbol for pos in positions)
    tt_symbols.update(set(o.underlying_symbol for o in options))
    tt_symbols.update(set(o.underlying_symbol for o in future_options))
    metrics = get_market_metrics(sesh, list(tt_symbols))
    metrics_dict = {metric.symbol: metric for metric in metrics}

    table_show_mark = sesh.config.getboolean('portfolio', 'table-show-mark-price', fallback=False)
    table_show_trade = sesh.config.getboolean('portfolio', 'table-show-trade-price', fallback=False)
    table_show_delta = sesh.config.getboolean('portfolio', 'table-show-delta', fallback=False)
    table_show_theta = sesh.config.getboolean('portfolio', 'table-show-theta', fallback=False)
    table_show_gamma = sesh.config.getboolean('portfolio', 'table-show-gamma', fallback=False)
    table.add_column('Symbol', justify='left')
    table.add_column('Qty', justify='right')
    table.add_column('Day P/L', justify='right')
    table.add_column('Total P/L', justify='right')
    if table_show_mark:
        table.add_column('Mark Price', justify='right')
    if table_show_trade:
        table.add_column('Trade Price', justify='right')
    table.add_column('IV Rank', justify='right')
    if table_show_delta:
        table.add_column('Delta', justify='right')
    if table_show_theta:
        table.add_column('Theta', justify='right')
    if table_show_gamma:
        table.add_column('Gamma', justify='right')
    table.add_column(u'\u03B2 Delta', justify='right')
    table.add_column('Net Liq', justify='right')
    table.add_column('Indicators', justify='center')
    sums = defaultdict(lambda: Decimal(0))
    closing: dict[int, TradeableTastytradeJsonDataclass] = {}
    for i, pos in enumerate(positions):
        row = [f'{i+1}']
        mark = pos.mark or 0
        m = (1 if pos.quantity_direction == 'Long' else -1)
        mark_price = mark / pos.quantity
        pos_mark_price = pos.mark_price or 0
        if all:
            row.append(account_dict[pos.account_number])  # type: ignore
        net_liq = Decimal(mark * m)
        pnl_day = 0
        # instrument-specific calculations
        if pos.instrument_type == InstrumentType.EQUITY_OPTION:
            o = options_dict[pos.symbol]
            closing[i + 1] = o
            # BWD = beta * stock price * delta / index price
            delta = greeks_dict[o.streamer_symbol].delta * 100 * m
            theta = greeks_dict[o.streamer_symbol].theta * 100 * m
            gamma = greeks_dict[o.streamer_symbol].gamma * 100 * m
            metrics = metrics_dict[o.underlying_symbol]
            beta = metrics.beta or 0
            bwd = beta *  mark * delta / spy_price
            ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            indicators = get_indicators(today, metrics)
            pnl = m * (mark_price - pos.average_open_price * pos.multiplier)
            trade_price = pos.average_open_price * pos.multiplier
            open_price = get_day_open(summary_dict[o.streamer_symbol])
            day_change = pos_mark_price - open_price
            pnl_day = day_change * pos.quantity * pos.multiplier
        elif pos.instrument_type == InstrumentType.FUTURE_OPTION:
            o = future_options_dict[pos.symbol]
            closing[i + 1] = o
            delta = greeks_dict[o.streamer_symbol].delta * 100 * m
            theta = greeks_dict[o.streamer_symbol].theta * 100 * m
            gamma = greeks_dict[o.streamer_symbol].gamma * 100 * m
            # BWD = beta * stock price * delta / index price
            f = futures_dict[o.underlying_symbol]
            metrics = metrics_dict[o.root_symbol]
            indicators = get_indicators(today, metrics)
            bwd = (get_day_open(summary_dict[f.streamer_symbol]) *
                   metrics.beta * delta / spy_price) if metrics.beta else 0
            ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            trade_price = pos.average_open_price / f.display_factor
            pnl = (mark_price - trade_price) * m
            open_price = get_day_open(summary_dict[o.streamer_symbol])
            day_change = pos_mark_price - open_price
            pnl_day = day_change * pos.quantity * pos.multiplier
        elif pos.instrument_type == InstrumentType.EQUITY:
            theta = 0
            gamma = 0
            delta = pos.quantity * m
            # BWD = beta * stock price * delta / index price
            metrics = metrics_dict[pos.symbol]
            closing[i + 1] = equity_dict[pos.symbol]
            beta = metrics.beta or 0
            indicators = get_indicators(today, metrics)
            bwd = beta * mark_price * delta / spy_price
            ivr = (metrics.tos_implied_volatility_index_rank or 0) * 100
            pnl = mark - pos.average_open_price * pos.quantity * m
            trade_price = pos.average_open_price
            open_price = get_day_open(summary_dict[pos.symbol])
            day_change = pos_mark_price - open_price
            pnl_day = day_change * pos.quantity
        elif pos.instrument_type == InstrumentType.FUTURE:
            theta = 0
            gamma = 0
            delta = pos.quantity * m * 100
            f = futures_dict[pos.symbol]
            closing[i + 1] = f
            # BWD = beta * stock price * delta / index price
            metrics = metrics_dict[f.future_product.root_symbol]  # type: ignore
            indicators = get_indicators(today, metrics)
            bwd = (metrics.beta * mark_price * delta / spy_price) if metrics.beta else 0
            ivr = (metrics.tw_implied_volatility_index_rank or 0) * 100
            trade_price = pos.average_open_price * f.notional_multiplier
            pnl = (mark_price - trade_price) * pos.quantity * m
            open_price = get_day_open(summary_dict[f.streamer_symbol])
            day_change = pos_mark_price - open_price
            pnl_day = day_change * pos.quantity * pos.multiplier
            net_liq = pnl_day
        elif pos.instrument_type == InstrumentType.CRYPTOCURRENCY:
            theta = 0
            gamma = 0
            delta = 0
            bwd = 0
            ivr = None
            pnl = mark - pos.average_open_price * pos.quantity * m
            trade_price = pos.average_open_price
            indicators = ''
            pos.quantity = round(pos.quantity, 2)
            c = crypto_dict[pos.symbol]
            closing[i + 1] = c
            open_price = get_day_open(summary_dict[c.streamer_symbol])
            day_change = pos_mark_price - open_price
            pnl_day = day_change * pos.quantity * pos.multiplier
        else:
            print(f'Skipping {pos.symbol}, unknown instrument type '
                  f'{pos.instrument_type}!')
            continue
        if pos.created_at.date() == today:
            pnl_day = pnl
        sums['pnl'] += pnl
        sums['pnl_day'] += pnl_day
        sums['bwd'] += bwd
        sums['net_liq'] += net_liq
        row.extend([
            pos.symbol,
            f'{pos.quantity * m:g}',
            conditional_color(pnl_day),
            conditional_color(pnl)
        ])
        if table_show_mark:
            row.append(f'${mark_price:.2f}')
        if table_show_trade:
            row.append(f'${trade_price:.2f}')
        row.append(f'{ivr:.1f}' if ivr else '--')
        if table_show_delta:
            row.append(f'{delta:.2f}')
        if table_show_theta:
            row.append(f'{theta:.2f}')
        if table_show_gamma:
            row.append(f'{gamma:.2f}')
        row.extend([
            f'{bwd:.2f}',
            conditional_color(net_liq),
            indicators
        ])
        table.add_row(*row, end_section=(i == len(positions) - 1))
    # summary
    final_row = ['']
    if all:
        final_row.append('')
    final_row.extend([
        '',
        '',
        conditional_color(sums['pnl_day']),
        conditional_color(sums['pnl'])
    ])
    if table_show_mark:
        final_row.append('')
    if table_show_trade:
        final_row.append('')
    final_row.append('')
    if table_show_delta:
        final_row.append('')
    if table_show_theta:
        final_row.append('')
    if table_show_gamma:
        final_row.append('')
    final_row.extend([
        f"{sums['bwd']:.2f}",
        conditional_color(sums['net_liq']),
        ''
    ])
    table.add_row(*final_row)
    console.print(table)
    close = get_confirmation('Close out a position? y/N ', default=False)
    if not close:
        return
    # get the position(s) to close
    to_close = input('Enter the number(s) of the leg(s) to include in closing order, separated by commas: ')
    if not to_close:
        return
    to_close = [int(i) for i in to_close.split(',')]
    close_objs = [closing[i] for i in to_close]
    account_number = pos_dict[close_objs[0].symbol].account_number
    if any(pos_dict[o.symbol].account_number != account_number for o in close_objs):
        print('All legs must be in the same account!')
        return
    account = next(a for a in sesh.accounts if a.account_number == account_number)
    legs = []
    total_price = Decimal(0)
    tif = OrderTimeInForce.DAY
    for o in close_objs:
        pos = pos_dict[o.symbol]
        total_price += pos.mark_price * (1 if pos.quantity_direction == 'Long' else -1)
        if isinstance(o, Future):
            action = (OrderAction.SELL
                      if pos.quantity_direction == 'Long'
                      else OrderAction.BUY)
        else:
            action = (OrderAction.SELL_TO_CLOSE
                      if pos.quantity_direction == 'Long'
                      else OrderAction.BUY_TO_CLOSE)
        if isinstance(o, Cryptocurrency):
            tif = OrderTimeInForce.GTC
        legs.append(o.build_leg(pos.quantity, action))

    console.print(f'Mark price for trade: {conditional_color(total_price)}')
    price = input('Please enter a limit price per quantity (default mark): ')
    if price:
        total_price = Decimal(price)
    else:
        total_price = round(total_price, 2)
    
    order = NewOrder(
        time_in_force=tif,
        order_type=OrderType.LIMIT,
        legs=legs,
        price=abs(total_price),
        price_effect=PriceEffect.CREDIT if total_price > 0 else PriceEffect.DEBIT
    )
    data = test_order_handle_errors(account, sesh, order)
    if not data:
        return

    bp = data.buying_power_effect.change_in_buying_power
    bp *= -1 if data.buying_power_effect.change_in_buying_power_effect == PriceEffect.DEBIT else 1
    fees = data.fee_calculation.total_fees if data.fee_calculation else 0

    table = Table(show_header=True, header_style='bold', title_style='bold', title='Order Review')
    table.add_column('Symbol', justify='center')
    table.add_column('Price', justify='center')
    table.add_column('BP Effect', justify='center')
    table.add_column('Fees', justify='center')
    table.add_row(order.legs[0].symbol, conditional_color(total_price),
                  conditional_color(bp), f'[red]${fees:.2f}[/red]')
    for i in range(1, len(order.legs)):
        table.add_row(order.legs[i].symbol, '-', '-', '-')
    console.print(table)

    if data.warnings:
        for warning in data.warnings:
            print_warning(warning.message)
    if get_confirmation('Send order? Y/n '):
        account.place_order(sesh, order, dry_run=False)


@portfolio.command(help='View your previous positions.')
async def history():
    pass


@portfolio.command(help='View margin usage for an account.')
async def margin():
    pass

