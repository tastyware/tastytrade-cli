import getpass
import logging
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import requests
from dateutil.relativedelta import FR, relativedelta
from tastyworks.models.session import TastyAPISession
from tastyworks.models.trading_account import TradingAccount

VERSION = '1.0.0'
ZERO = Decimal(0)
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


def get_tasty_monthly(day: Optional[date] = date.today()) -> date:
    option1 = get_monthly(day + timedelta(weeks=4))
    option2 = get_monthly(day + timedelta(weeks=8))
    day45 = day + timedelta(days=45)
    return option1 if day45 - option1 < option2 - day45 else option2


def get_monthly(day: Optional[date] = date.today()) -> date:
    day = day.replace(day=1)
    day += relativedelta(weeks=2, weekday=FR)
    return day


def is_monthly(day: date) -> bool:
    return day.weekday() == 4 and 15 <= day.day <= 21


def get_confirmation(prompt: str) -> bool:
    while True:
        answer = input(prompt).lower()
        if not answer:
            return True
        if answer[0] == 'y':
            return True
        if answer[0] == 'n':
            return False


async def get_account(sesh: RenewableTastyAPISession) -> TradingAccount:
    accounts = await TradingAccount.get_remote_accounts(sesh)
    accounts = [acc for acc in accounts if not acc.is_closed]
    account = os.getenv('TW_ACC')
    if account:
        for acc in accounts:
            if acc.account_number == account:
                return acc
        LOGGER.warning('Environment variable $TW_ACC is set, but doesn\'t appear to exist!')

    for i in range(len(accounts)):
        if i == 0:
            print(f'{i + 1}) {accounts[i].account_number} {accounts[i].nickname} (default)')
        else:
            print(f'{i + 1}) {accounts[i].account_number} {accounts[i].nickname}')
    choice = 0
    while choice not in range(1, len(accounts) + 1):
        try:
            raw = input('Please choose an account: ')
            choice = int(raw)
        except ValueError:
            if not raw:
                return accounts[0]

    return accounts[choice - 1]
