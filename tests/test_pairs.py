from math import floor

from src.pairs import sizing


def test_sizing():
    """Apply test cases for pairs sizing"""

    args = dict(price_left=100, price_right=25, vol_left=2, vol_right=7,
                unit_size_left=100, multiplier_left=1, multiplier_right=1)

    def msg():
        return f"Expected {exp:.2f} units, but calculated {act:.2f}."

    pair_specs = sizing.size(**args)
    exp = 114
    act = floor(pair_specs['unit_size_right'])
    assert act == exp, msg()

    args['multiplier_left'] = 100
    args['multiplier_right'] = 10
    pair_specs = sizing.size(**args)
    exp = 1142
    act = floor(pair_specs['unit_size_right'])
    assert act == exp, msg()

    args['multiplier_left'] = 1
    args['multiplier_right'] = 100
    pair_specs = sizing.size(**args)
    exp = 1.14
    act = round(pair_specs['unit_size_right'], 2)
    assert act == exp, msg()
