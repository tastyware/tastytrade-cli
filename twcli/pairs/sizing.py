"""Funcs to calculate size of pair"""


def size(price_left=1, price_right=1, vol_left=1, vol_right=1, unit_size_left=1,
         multiplier_left=1, multiplier_right=1):
    """Calculate volatility weighted size for each leg of pairs trade

    Calculate the number of units for each leg of a pairs trade by
    passing the price of both legs and optionally the share size of one
    leg and multipliers in the case of futures. Returns a dict with the
    given arguments and the number of units for each leg.

    It is often desirable to equate the level of risk for each leg of a
    pairs trade. This risk depends on both the equity value and the
    volatility of each leg.

    For example, suppose a pairs trade consists of two legs. The first
    leg is long stock ABC, which trades for $100 per share and has a
    30-day historical standard deviation of 2%. The second leg is a
    short position in stock XYZ, which trades for $25 per share and has
    a standard deviation of 7%. How many shares of each stock should be
    traded to create a neutral pairs trade?

    Clearly, if 100 shares of each leg were traded, the risk in one leg
    would be much greater than the other. So, we want to equate the
    equity of each leg:

        abc_shares * abc_price = xyz_shares * xyz_price
        left_shares * left_price = right_shares * right_price

    ...where we have arbitrarily defined ABC as the "left" side of the
    trade.

    However, the above equation fails to adequately equate the risk in
    each leg; since the volatility of XYZ is 7% and the volatility of
    ABC is 2%, sizing the trade based on the above equation would put
    more risk in the XYZ leg than the ABC leg.

    So, to equate the risk in each leg, we add a measure of volatility
    to the prior equation:

        left_shares * left_price * left_vol = right_shares * right_price * right_vol

    Compared to the prior equation, this equation reduces the number of
    shares traded in XYZ, since the risk is larger in each unit of
    equity for XYZ, because XYZ has higher volatility.

    Now, suppose that we're comfortable trading 100 shares of ABC and we
    want to now calculate the quantity of XYZ shares to trade. We can do
    a simple algebriac manipulation to calculate the number of shares:

        right_shares = (left_shares * left_price * left_vol) / (right_price * right_vol)
                     = (100 * 100 * 2) / (25 * 7)
                     = 114.28

    ..and this can be plugged back into the original equation as a
    check.

    In the case of a futures contract, the *notional value* must be
    calculated in order to volatility-weight each leg:

        left_units * left_multiplier * left_price * left_vol =
            right_units * right_multiplier * right_price * right_vol

    ...where the multiplier is a number used to convert the futures
    price into the notional value of the futures contract. In the case
    where both legs are a stock, the multipliers are simply 1. To
    calculate the number of units for the right leg:

        left_units =
            (right_units * right_multiplier * right_price * right_vol) /
            (left_multiplier * left_price * left_vol)

    Parameters
    ----------
    price_left, price_right : float
        The entry prices for each leg of the pair, left and right.

    vol_left, vol_right : float
        A measure of volatility for each leg of the pair, left and
        right.

    unit_size_left : float
        The number of units (e.g. shares) that compose the left leg of
        the pair. Optional, default is 1 unit.

    multiplier_left, multiplier_right : float
        Multiplier for each leg of the pair, left and right. The
        multiplier is a number that translates the asset price into the
        notional (equity) value of one unit of the asset. In the case of
        a stock, the mulitplier is simply 1. The multiplier for futures
        contracts depends on the specifications of the contract.
        Optional, default is 1.

    Returns
    -------
    pair_specs : dict
        Dict with keys multiplier_left, multiplier_right, price_left,
        price_right, unit_size_left, unit_size_right, vol_left,
        and vol_right.

    """
    unit_size_right = \
        (vol_left * price_left * multiplier_left * unit_size_left) / \
        (vol_right * price_right * multiplier_right)

    pair_specs = dict(vol_left=vol_left, price_left=price_left,
                      multiplier_left=multiplier_left,
                      multiplier_right=multiplier_right,
                      unit_size_left=unit_size_left, vol_right=vol_right,
                      price_right=price_right, unit_size_right=unit_size_right)

    return pair_specs
