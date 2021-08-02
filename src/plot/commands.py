import asyncclick as click
import pandas as pd

from .csv import Portfolio


@click.command(help='Chart your net liquidity or realized profit/loss over time.')
@click.option('-n', '--netliq', is_flag=True,
              help='Display net liquidity over time instead of realized profit/loss.')
@click.option('-p', '--percentage', is_flag=True,
              help='Whether to display percentages instead of absolute values in the chart.')
@click.option('-d', '--duration', default='ytd',
              help='Possible values: {all,10y,5y,1y,ytd,6m,3m,1m,5d}')
@click.argument('csv')
async def plot(netliq, percentage, duration, csv):
    # read the given csv file and prepare it
    df = pd.read_csv(csv)
    df = df.reindex(index=df.index[::-1])
    df = df.astype(str)

    # create a portfolio with the given history
    pf = Portfolio(df, net_liq=netliq)

    # get initial net liq if we're using percentage
    nl = None
    if percentage:
        pf_tmp = Portfolio(df, net_liq=True)
        nl = pf_tmp._get_starting_net_liq(duration)

    # get the P/L or net liq and save the graph
    val = pf.plot(duration, starting_net_liq=nl)

    # print current positions
    if nl is None:
        print(('Current net liquidity' if netliq else 'Realized P/L') + f': ${val:.2f}')
    else:
        print(('Change in net liquidity' if netliq else 'Realized P/L') + f': {val:.2f}%')
    print('Current positions:')
    for p in pf.positions.values():
        print(p)
