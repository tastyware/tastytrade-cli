from decimal import Decimal as D

import petl

from twcli.plot.plot import _DURATIONS, Portfolio

_DATABASE_PATH = 'tests/data/transactions.json'
_NET_LIQUIDITY = D(7018.60)
_NET_LIQUIDITY_PERCENT = D(215.87)
_REALIZED_PANDL = D(-1816.92)
_REALIZED_PANDL_PERCENT = D(-81.77)
_PRECISION = D('1.00')


def gen_portfolio(net_liq=False):
    table = petl.fromjson(_DATABASE_PATH)

    return Portfolio(petl.data(table), net_liq=net_liq)


def test_plot_pandl():
    pf = gen_portfolio()
    val = pf.plot('all', gen_img=False)

    print(val, type(val))
    assert val.quantize(_PRECISION) == _REALIZED_PANDL.quantize(_PRECISION)


def test_twcli_plot_netliq():
    # the value shouldn't change
    for duration in _DURATIONS:
        pf = gen_portfolio(True)
        val = pf.plot('all', gen_img=False)

        assert val.quantize(_PRECISION) == _NET_LIQUIDITY.quantize(_PRECISION)


def test_plot_pandl_percent():
    pf = gen_portfolio()
    pf_tmp = gen_portfolio(True)
    nl = pf_tmp._get_starting_net_liq('all')
    val = pf.plot('all', starting_net_liq=nl, gen_img=False)

    assert val.quantize(_PRECISION) == _REALIZED_PANDL_PERCENT.quantize(_PRECISION)


def test_plot_netliq_percent():
    pf = gen_portfolio(True)
    pf_tmp = gen_portfolio(True)
    nl = pf_tmp._get_starting_net_liq('all')
    val = pf.plot('all', starting_net_liq=nl, gen_img=False)

    assert val.quantize(_PRECISION) == _NET_LIQUIDITY_PERCENT.quantize(_PRECISION)


def test_plot_positions():
    pf = gen_portfolio()
    _ = pf.plot('all', gen_img=False)

    assert len(pf.positions) == 10
