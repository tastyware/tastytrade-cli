from decimal import Decimal as D

import pandas as pd

from src.plot.csv import _DURATIONS, Portfolio

_CSV_PATH = 'tests/data/transactions.csv'
_NET_LIQUIDITY = D(6645.84)
_NET_LIQUIDITY_PERCENT = D(199.09)
_REALIZED_PANDL = D(-2186.87)
_REALIZED_PANDL_PERCENT = D(-98.42)
_PRECISION = D('1.00')


def gen_portfolio(net_liq=False):
    df = pd.read_csv(_CSV_PATH)
    df = df.reindex(index=df.index[::-1])
    df = df.astype(str)

    return Portfolio(df, net_liq=net_liq)


def test_plot_pandl():
    pf = gen_portfolio()
    val = pf.plot('all')

    print(val, type(val))
    assert val.quantize(_PRECISION) == _REALIZED_PANDL.quantize(_PRECISION)


def test_twcli_plot_netliq():
    # the value shouldn't change
    for duration in _DURATIONS:
        pf = gen_portfolio(True)
        val = pf.plot('all')

        assert val.quantize(_PRECISION) == _NET_LIQUIDITY.quantize(_PRECISION)


def test_plot_pandl_percent():
    pf = gen_portfolio()
    pf_tmp = gen_portfolio(True)
    nl = pf_tmp._get_starting_net_liq('all')
    val = pf.plot('all', starting_net_liq=nl)

    assert val.quantize(_PRECISION) == _REALIZED_PANDL_PERCENT.quantize(_PRECISION)


def test_plot_netliq_percent():
    pf = gen_portfolio(True)
    pf_tmp = gen_portfolio(True)
    nl = pf_tmp._get_starting_net_liq('all')
    val = pf.plot('all', starting_net_liq=nl)

    assert val.quantize(_PRECISION) == _NET_LIQUIDITY_PERCENT.quantize(_PRECISION)


def test_plot_positions():
    pf = gen_portfolio()
    _ = pf.plot('all')

    assert len(pf.positions) == 2
    for trade in pf.positions.values():
        assert 'GME' in trade.symbol
