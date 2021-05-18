"""Misc functions"""


def summarize_params(price_underlying, strike, interest, volatility, date_exp,
                     date_evl):
    """Display values that are inputs to option price"""
    msg = (f"* {price_underlying.value()} - underlying price\n"
           f"* {strike} - strike\n"
           f"* {interest} - interest\n"
           f"* {volatility.value()} - volatility\n"
           f"* {date_exp} - exp date\n"
           f"* {date_evl} - eval date\n")

    print(msg)
