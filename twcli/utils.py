from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta, FR
import getpass
import logging
import os
from decimal import Decimal as D

import requests
from tastyworks.models.session import TastyAPISession
from tastyworks.models.trading_account import TradingAccount
from tastyworks.utils import get_third_friday

VERSION = '0.4.0'
ZERO = D(0)
LOGGER = logging.getLogger(__name__)

_TOKEN_PATH = '.tastyworks/twcli/sesh'


class TastyworksCLIError(Exception):
    pass


class RenewableTastyAPISession(TastyAPISession):
    def __init__(self, API_url=None):
        path = os.path.join(os.path.expanduser('~'), _TOKEN_PATH)
        self.logged_in = False
        self.accounts = None

        # try to load token
        if os.path.exists(path):
            with open(path) as f:
                self.session_token = f.read().strip()

            self.API_url = API_url if API_url else 'https://api.tastyworks.com'

            # make sure token hasn't expired
            response = requests.post(f'{self.API_url}/sessions/validate', headers=self.get_request_headers())
            self.logged_in = (response.status_code == 201)

        if not self.logged_in:
            # either the token expired or doesn't exist
            username, password = self._get_credentials()
            TastyAPISession.__init__(self, username, password)

            # write session token to cache
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(self.session_token)
        else:
            LOGGER.debug('Logged in with cached session token.')

    def _get_credentials(self):
        username = os.getenv('TW_USER')
        if not username:
            username = getpass.getpass('Username: ')
        password = os.getenv('TW_PASS')
        if not password:
            password = getpass.getpass('Password: ')

        return username, password

    @classmethod
    async def create(cls):
        self = RenewableTastyAPISession()
        accounts = await TradingAccount.get_remote_accounts(self)
        self.accounts = [acc for acc in accounts if not acc.is_closed]

        return self


def get_tasty_monthly(date=date.today()):
    option1 = get_monthly(date + timedelta(weeks=4))
    option2 = get_monthly(date + timedelta(weeks=8))
    day45 = date + timedelta(days=45)
    return option1 if day45 - option1 < option2 - day45 else option2


def get_monthly(date=date.today()):
    date = date.replace(day=1)
    date += relativedelta(weeks=2, weekday=FR)
    return date
