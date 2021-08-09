import getpass
import os
from decimal import Decimal as D

import requests
from tastyworks.models.session import TastyAPISession
from tastyworks.models.trading_account import TradingAccount

VERSION = '0.3.0'
ZERO = D(0)

_TOKEN_PATH = '.tastyworks/twcli/sesh'


class TastyworksCLIError(Exception):
    pass


class RenewableTastyAPISession(TastyAPISession):
    def __init__(self, API_url=None):
        path = os.path.join(os.path.expanduser('~'), _TOKEN_PATH)
        self.logged_in = False

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
            print('Logged in with cached session token.')

    def _get_credentials(self):
        username = os.getenv('TW_USER')
        if not username:
            username = getpass.getpass('Username: ')
        password = os.getenv('TW_PASS')
        if not password:
            password = getpass.getpass('Password: ')

        return username, password


async def choose_account(session):
    accounts = await TradingAccount.get_remote_accounts(session)
    accounts = [acc for acc in accounts if not acc.is_closed]

    account = os.getenv('TW_ACC')
    if account:
        for acc in accounts:
            if acc.account_number == account:
                return acc

        print('Warning: Environment variable TW_ACC is set, but a matching account does not exist.')

    for i in range(len(accounts)):
        print(f'{i + 1}) {accounts[i].nickname} ~ {accounts[i].account_number}')
    choice = input('Choose an account (default 1): ')
    if not choice:
        choice = 1

    if int(choice) > len(accounts):
        raise TastyworksCLIError('Invalid account choice!')

    return accounts[int(choice) - 1]
