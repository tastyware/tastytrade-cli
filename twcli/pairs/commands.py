import asyncclick as click

from .sizing import size as size_pair


def summarize(pair_specs):
    """Summarize pairs calculation"""
    print(f"\nFor {pair_specs['unit_size_right']:,.2f} units in the left "
          f"leg, trade {pair_specs['unit_size_left']:,.2f} in the right "
          f"leg. \n")


@click.group(chain=True, help='Evaluate and size pairs trades.')
async def pairs():
    pass


@pairs.command(help='Calculate volatility-weighted size for each leg. ')
@click.option('-i', '--interactive-mode', is_flag=True,
              help='Query inputs from user.')
@click.option('-l', '--price-left', type=float, default=1,
              help='Price of left leg.')
@click.option('-r', '--price-right', type=float, default=1,
              help='Price of right leg.')
@click.option('-v', '--vol-left', type=float, default=1,
              help='Volatility measure of left leg.')
@click.option('-o', '--vol-right', type=float, default=1,
              help='Volatility measure of right leg.')
@click.option('-s', '--unit-size-left', type=float, default=1,
              help='Number of units for left leg.')
@click.option('-m', '--multiplier-left', type=float, default=1,
              help='Unit multplier for left leg.')
@click.option('-u', '--multiplier-right', type=float, default=1,
              help='Unit multplier for right leg.')
async def size(interactive_mode, price_left, price_right, vol_left, vol_right,
               unit_size_left, multiplier_left, multiplier_right):
    if interactive_mode:
        args = dict()
        args['unit_size_left'] = 1
        args['multiplier_left'] = 1
        args['multiplier_right'] = 1
        c = ['unit_size_left', 'price_left', 'vol_left', 'multiplier_left',
             'price_right', 'vol_right', 'multiplier_right', ]
        for k in c:
            if k in args:
                v = input(f"enter value for {k} (default={args[k]:.2f}) > ")
                if v:
                    args[k] = float(v)
            else:
                args[k] = float(input(f"enter value for {k} > "))
        pair_specs = size_pair(**args)
        summarize(pair_specs)
        print('Below are the arguments to replicate: \n')
        print(
            f"    tw pairs size "
            f"-s {pair_specs['unit_size_left']:.2f} "
            f"-l {pair_specs['price_left']:.2f} "
            f"-v {pair_specs['vol_left']:.2f} "
            f"-m {pair_specs['multiplier_left']:.2f} "
            f"-r {pair_specs['price_right']:.2f} "
            f"-o {pair_specs['vol_right']:.2f} "
            f"-u {pair_specs['multiplier_right']:.2f} \n"
        )

    else:
        pair_specs = size_pair(price_left, price_right, vol_left, vol_right,
                               unit_size_left, multiplier_left,
                               multiplier_right)
        summarize(pair_specs)
