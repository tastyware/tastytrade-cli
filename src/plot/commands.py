from datetime import datetime

import asyncclick as click
import petl
from dateutil import parser

from ..utils import RenewableTastyAPISession, choose_account
from .plot import Portfolio


@click.command(help='Chart your net liquidity or realized profit/loss over time.')
@click.option('-n', '--netliq', is_flag=True,
              help='Display net liquidity over time instead of realized profit/loss.')
@click.option('-p', '--percentage', is_flag=True,
              help='Whether to display percentages instead of absolute values in the chart.')
@click.option('-d', '--duration', default='ytd',
              help='Possible values: {all,10y,5y,1y,ytd,6m,3m,1m,5d}')
async def plot(netliq, percentage, duration):
    sesh = RenewableTastyAPISession()
    acc = await choose_account(sesh)
    start_date = parser.parse(acc.opened_at.split('T')[0])
    history = await acc.get_history(sesh, params={
        'start-date': start_date.isoformat() + 'Z',
        'end-date': datetime.now().isoformat() + 'Z',
    })

    table = petl.fromdicts(history).cut(
        'executed-at',
        'transaction-type',
        'action',
        'symbol',
        'value',
        'value-effect',
        'quantity',
        'commission',
        'clearing-fees',
        'proprietary-index-option-fees',
        'regulatory-fees'
    ).addfield('is-closing', lambda row: 'Close' in row['action'] if row['action'] else False) \
     .sort(['executed-at', 'is-closing'])

    # create a portfolio with the given history
    pf = Portfolio(petl.data(table), net_liq=netliq)

    # get initial net liq if we're using percentage
    nl = None
    if percentage:
        pf_tmp = Portfolio(petl.data(table), net_liq=True)
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
