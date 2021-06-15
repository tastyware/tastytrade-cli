"""Convenience functions, class for optons price modeling with QuantLib"""
import pandas as pd
import QuantLib as ql


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


def build_volatility_curve(volatility):
    """Create volatility curve"""
    volatility = ql.SimpleQuote(volatility)
    volatility_curve = ql.BlackConstantVol(0, ql.TARGET(),
                                           ql.QuoteHandle(volatility),
                                           ql.Actual360())
    return volatility, volatility_curve


def build_interest_curve(rate_risk_free):
    """Create interest curve"""
    rate_risk_free = ql.SimpleQuote(rate_risk_free)
    rate_risk_free_curve = ql.FlatForward(0, ql.TARGET(),
                                          ql.QuoteHandle(rate_risk_free),
                                          ql.Actual360())

    return rate_risk_free_curve


def build_dates(date_expiration=None, date_evaluation=None, dte=None):
    """Create date objects for model input"""
    # setup dates
    if not date_expiration and not date_evaluation:
        date_evaluation = pd.Timestamp.utcnow().tz_convert('US/Central')
        date_expiration = date_evaluation + dte
    elif not dte and ((not date_expiration) or (not date_evaluation)):
        raise Exception('Must have either both exp and eval dates or days to '
                        'expiration. ')
    else:
        if date_evaluation == 'today':
            date_evaluation = pd.Timestamp.utcnow().tz_convert('US/Central')
        date_expiration = pd.to_datetime(date_expiration)
        date_evaluation = pd.to_datetime(date_evaluation)

    dte = (date_expiration - date_evaluation).days
    date_evaluation = ql.Date(date_evaluation.day, date_evaluation.month,
                              date_evaluation.year)
    date_expiration = ql.Date(date_expiration.day, date_expiration.month,
                              date_expiration.year)

    # set the global evaluation date
    ql.Settings.instance().evaluationDate = date_evaluation

    return date_expiration, date_evaluation, dte


class Model():
    """Create a class used to model option prices

    For dates, must pass either 'dte' that is 'days to expiration',
    where the current date will be used as eval date and a number of
    days will be added to calculate an expiration date; alternatively
    can pass an expiration date and optionally an evaluation date (else
    current date is used).

    """
    def __init__(self, price_underlying, price_strike, volatility,
                 rate_risk_free, date_expiration=None, date_evaluation=None,
                 dte=None, option_type='call', verbose=False, dividend_rate=0,
                 exercise_type='european', n_steps=200):
        self.price_underlying = ql.SimpleQuote(price_underlying)
        self.price_strike = price_strike
        volatility, volatility_curve = build_volatility_curve(volatility)
        self.volatility = volatility
        self.volatility_curve = volatility_curve
        rate_risk_free_curve = build_interest_curve(rate_risk_free)
        self.n_steps = n_steps
        self.rate_risk_free = rate_risk_free
        self.rate_risk_free_curve = rate_risk_free_curve
        date_expiration, date_evaluation, dte = \
            build_dates(date_expiration, date_evaluation, dte)
        self.date_expiration = date_expiration
        self.date_evaluation = date_evaluation
        self.dte = dte
        self.verbose = verbose
        self.dividend_rate = dividend_rate
        self.day_count = ql.Actual365Fixed()
        self.calendar = ql.UnitedStates()
        self.exercise_type = exercise_type

        if option_type == 'call':
            self.option_type = ql.Option.Call
        elif option_type == 'C' or option_type == 'c':
            self.option_type = ql.Option.Call
        elif option_type == 'P' or option_type == 'p':
            self.option_type = ql.Option.Put
        else:
            self.option_type = ql.Option.Put
        self.create_process()
        self.create_option()

    def calculate_imp_vol(self, price_option, minvol=0.001, maxvol=10):
        """Use model to calculate volatility implied by price"""
        volatility_implied = \
            self.option.impliedVolatility(price_option, self.process,
                                          minVol=minvol, maxVol=10,)

        return volatility_implied

    def create_process(self):
        """Create the process"""
        # create process, engine and option
        self.process = ql.BlackScholesProcess(
            ql.QuoteHandle(self.price_underlying),
            ql.YieldTermStructureHandle(self.rate_risk_free_curve),
            ql.BlackVolTermStructureHandle(self.volatility_curve))

    def create_engine(self):
        if self.exercise_type == 'european':
            self.exercise = ql.EuropeanExercise(self.date_expiration)
            self.engine = ql.AnalyticEuropeanEngine(self.process)
        elif self.exercise_type == 'american':
            self.exercise = ql.AmericanExercise(self.date_evaluation,
                                                self.date_expiration)
            self.engine = ql.BinomialVanillaEngine(self.process, 'crr',
                                                   self.n_steps)
        else:
            raise Exception("Received unexpected exercise type "
                            f"'{self.exercise_type}'.")

        self.option = ql.VanillaOption(self.payoff, self.exercise)
        self.option.setPricingEngine(self.engine)

    def create_option(self):
        """Create the option"""
        self.create_process()
        self.payoff = ql.PlainVanillaPayoff(self.option_type, self.price_strike)
        self.create_engine()
