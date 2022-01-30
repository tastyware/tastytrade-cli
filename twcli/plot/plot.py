import os
import subprocess
import sys
from datetime import datetime
from decimal import Decimal

import matplotlib.pyplot as plt
from dateutil.relativedelta import relativedelta
from matplotlib.dates import (DateFormatter, DayLocator, MonthLocator,
                              YearLocator)

from ..utils import ZERO, TastyworksCLIError

_month_fmt = DateFormatter('%b')
_year_fmt = DateFormatter('%Y')
_day_fmt = DateFormatter('%d')

_DURATIONS = ['all', '10y', '5y', '1y', 'ytd', '6m', '3m', '1m', '5d']


class Trade():
    '''
    Object to hold a specific trade and its notable properties.
    Contains the important information of one row of the table.
    '''
    def __init__(self, trade):
        self.date = trade[0].split('T')[0]  # we just want the date
        self.type = trade[1]
        self.action = trade[2]
        self.symbol = trade[3]
        self.value = Decimal(trade[4].replace(',', '')) * (-1 if trade[5] == 'Debit' else 1)
        self.quantity = Decimal(trade[6].replace(',', '')) if trade[6] else ZERO
        commission = -Decimal(trade[7]) if trade[7] else ZERO
        clearing_fees = -Decimal(trade[8]) if trade[8] else ZERO
        pio_fees = -Decimal(trade[9]) if trade[9] else ZERO
        regulatory_fees = -Decimal(trade[10]) if trade[10] else ZERO
        self.fees = commission + clearing_fees + pio_fees + regulatory_fees

    def __str__(self):
        return f'{self.date}: {self.symbol} x{self.quantity} at ${self.value}'


class Portfolio():
    '''
    Starting with the given table, runs forwards through
    time, tracking either realized P/L or net liquidity,
    and saving those results. Contains methods to process
    a petl table, handle date ranges, and draw a plot.
    '''
    def __init__(self, json, net_liq=False):
        # contains the P/L or net liquidity at a certain date
        self.values = []
        # contains the dates at which closing trades were placed
        self.dates = []
        # a dictionary of symbol -> Trade, used to close positions
        self.positions = {}
        self.last_value = ZERO
        # the given petl table
        self.json = json
        # whether or not to use net liq instead of realized P/L
        self.net_liq = net_liq

        self._calculate()

    def _process_dates(self, duration):
        if duration not in _DURATIONS:
            raise TastyworksCLIError('Not a valid duration!\t{all,10y,5y,1y,ytd,6m,3m,1m,5d}')

        # convert dates to datetimes
        self.dates = [datetime.strptime(date, '%Y-%m-%d') for date in self.dates]

        # when multiple transactions occur in a day, use only the last one
        final_dates = []
        final_price = []
        last_date = None
        for i in range(len(self.dates)):
            if last_date is None:
                final_dates.append(self.dates[i])
                final_price.append(self.values[i])
            elif self.dates[i] != last_date:
                final_dates.append(last_date)
                final_price.append(self.values[i - 1])
            last_date = self.dates[i]
        # method above omits the very last trade
        final_dates.append(last_date)
        final_price.append(self.values[-1])

        # update these lists to the cleaned versions
        self.dates = final_dates
        self.values = final_price

        if duration == 'all':
            start_date = self.dates[0]
        elif duration == '10y':
            start_date = datetime.now() - relativedelta(years=10)
        elif duration == '5y':
            start_date = datetime.now() - relativedelta(years=5)
        elif duration == '1y':
            start_date = datetime.now() - relativedelta(years=1)
        elif duration == 'ytd':
            # hack to get first day of current year in a datetime
            start_date = datetime.combine(
                datetime.now().date().replace(month=1, day=1),
                datetime.min.time()
            )
        elif duration == '6m':
            start_date = datetime.now() - relativedelta(months=6)
        elif duration == '3m':
            start_date = datetime.now() - relativedelta(months=3)
        elif duration == '1m':
            start_date = datetime.now() - relativedelta(months=1)
        else:
            start_date = datetime.now() - relativedelta(days=7)

        # if given range is longer than our portfolio history
        if start_date < self.dates[0]:
            start_date = self.dates[0]

        # get index of first date in our range
        start = -1
        for i in range(len(self.dates)):
            if self.dates[i] >= start_date:
                start = i
                break

        if self.dates[start] == self.dates[-1]:
            raise TastyworksCLIError('Not enough closing trades present! There must be at least two closing trades present in the given timeframe.')

        # change formatting based on scale
        delta = datetime.now() - self.dates[0]
        if delta.days <= 31:
            fun = _d_fmt
            loc = DayLocator()
        elif delta.days <= 365:
            fun = _m_fmt_long
            loc = MonthLocator()
        elif delta.days <= 1000:
            fun = _m_fmt_short
            loc = MonthLocator()
        else:
            fun = _y_fmt
            loc = YearLocator()

        return start, fun, loc

    def _get_starting_net_liq(self, duration):
        '''
        Calculates the net liquidity at the beginning of
        the given time period for use with the percentage
        argument. Modifies the state, so call this on a
        throwaway Portfolio instance.
        '''
        start, _, _ = self._process_dates(duration.lower())

        return self.values[start]

    def plot(self, duration, starting_net_liq=None, gen_img=True):
        start, fun, loc = self._process_dates(duration.lower())

        # graph percentages
        if starting_net_liq is not None:
            initial_value = self.values[start]
            for i in range(start, len(self.values)):
                self.values[i] = (self.values[i] - initial_value) / starting_net_liq * Decimal(100)
        # shift graph vertically so it starts at zero if doing P/L
        elif not self.net_liq:
            initial_value = self.values[start]
            for i in range(start, len(self.values)):
                self.values[i] -= initial_value

        if gen_img:
            fig, ax = plt.subplots()

            # color based on net liq or profitability
            if self.net_liq:
                color = 'steelblue'
            elif self.values[-1] < 0:
                color = 'crimson'  # :(
            else:
                color = 'mediumseagreen'

            plt.plot(self.dates[start:], self.values[start:], color=color)
            plt.title('Net Liquidity' if self.net_liq else 'Realized P/L')
            ax.xaxis.set_major_locator(loc)
            ax.xaxis.set_major_formatter(fun)

            # save plot to current directory
            fp = 'netliq.png' if self.net_liq else 'pandl.png'
            fig.savefig(fp)

            # open plot in default image viewer
            if sys.platform == 'win32':
                os.startfile(fp)
            else:
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                subprocess.call([opener, fp])

        # return either the final net liq or the change in P/L
        return (self.values[-1] if self.net_liq else self.values[-1] - self.values[start])

    def _calculate(self):
        for trade in self.json:
            t = Trade(trade)
            # we could allow the user to disable this adjustment
            self.last_value += t.fees

            if t.type == 'Trade':
                # futures are handled differently. instead of opening
                # or closing trades, you just have a number of long
                # or short contracts. we multiply short contract quantities
                # by -1 and whenever a symbol's number of contracts hits
                # 0, it's treated as realized.
                if t.symbol[0] == '/':
                    # symbol already in positions dict
                    if t.symbol in self.positions:
                        self.positions[t.symbol].quantity += t.quantity * (-1 if 'sell' in t.action.lower() else 1)
                        self.positions[t.symbol].value += t.value
                    else:
                        self.positions[t.symbol] = t
                        self.positions[t.symbol].quantity *= (-1 if 'sell' in t.action.lower() else 1)

                    # realize gain/loss here
                    if self.positions[t.symbol].quantity == 0:
                        self.dates.append(t.date)
                        self.last_value += self.positions[t.symbol].value
                        self.values.append(self.last_value)
                        del self.positions[t.symbol]
                # non-futures opening trades
                elif 'open' in t.action.lower():
                    # symbol already in positions dict
                    if t.symbol in self.positions:
                        self.positions[t.symbol].quantity += t.quantity
                        self.positions[t.symbol].value += t.value
                    else:
                        self.positions[t.symbol] = t
                # non-futures closing trades
                else:
                    if t.symbol not in self.positions:
                        raise TastyworksCLIError(f'Closing trade present but opening trade missing for trade:\n{t}')
                    else:
                        self.positions[t.symbol].quantity -= t.quantity
                        self.positions[t.symbol].value += t.value
                        # realize if position is *completely* closed out
                        if self.positions[t.symbol].quantity == 0:
                            self.dates.append(t.date)
                            # this brings up an interesting question:
                            # is this a good way to determine realized/unrealized?
                            # example: you buy 50 shares at $10 and 50 shares at $11.
                            # then you sell 50 shares at $12. should that count as:
                            # unrealized until whole position is closed? (current)
                            # realized at the average cost basis?
                            # or realized at a specific basis?
                            self.last_value += self.positions[t.symbol].value  # the line in question
                            self.values.append(self.last_value)
                            del self.positions[t.symbol]

            # TW uses this for several things. the ones we care
            # about are expiration, assignment, exercise, and awards.
            elif t.type == 'Receive Deliver':
                # exercise/awards
                if t.action == 'Buy to Open' or t.action == 'Sell to Open':
                    if t.symbol in self.positions:
                        self.positions[t.symbol].quantity += t.quantity
                        self.positions[t.symbol].value += t.value
                    else:
                        self.positions[t.symbol] = t

                # assignment/expiration/symbol change
                elif t.symbol in self.positions:
                    self.positions[t.symbol].quantity -= t.quantity
                    self.positions[t.symbol].value += t.value
                    # realize if position is closed
                    if self.positions[t.symbol].quantity == 0:
                        self.dates.append(t.date)
                        self.last_value += self.positions[t.symbol].value
                        self.values.append(self.last_value)
                        del self.positions[t.symbol]

            # apply mark-to-market even when not tracking net liq;
            # otherwise, this is only done if we're tracking net liq.
            elif t.type == 'Money Movement' and (self.net_liq or (t.symbol[0] == '/' if t.symbol else False)):
                self.dates.append(t.date)
                self.last_value += t.value
                self.values.append(self.last_value)


def _m_fmt_long(x, pos=None):
    if _month_fmt(x) == 'Jan':
        return _year_fmt(x)
    return _month_fmt(x)


def _m_fmt_short(x, pos=None):
    if _month_fmt(x) == 'Jan':
        return _year_fmt(x)[-2:]
    return _month_fmt(x)[0]


def _y_fmt(x, pos=None):
    return _year_fmt(x)


def _d_fmt(x, pos=None):
    if _day_fmt(x) == '01':
        return _month_fmt(x)
    return _day_fmt(x)
