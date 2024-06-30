import getpass
import logging
import os
import pickle
import shutil
import sys
from configparser import ConfigParser
from datetime import date
from decimal import Decimal

from rich import print
from tastytrade import Account, ProductionSession

logger = logging.getLogger(__name__)
VERSION = '2.0'
ZERO = Decimal(0)

CUSTOM_CONFIG_PATH = '.config/ttcli/ttcli.cfg'
DEFAULT_CONFIG_PATH = 'etc/ttcli.cfg'
TOKEN_PATH = '.config/ttcli/.session'


def print_error(msg: str):
    print(f'[bold red]Error: {msg}[/bold red]')


def print_warning(msg: str):
    print(f'[light_coral]Warning: {msg}[/light_coral]')


class RenewableSession(ProductionSession):
    def __init__(self):
        custom_path = os.path.join(os.path.expanduser('~'), CUSTOM_CONFIG_PATH)
        default_path = os.path.join(sys.prefix, DEFAULT_CONFIG_PATH)
        token_path = os.path.join(os.path.expanduser('~'), TOKEN_PATH)

        # load config
        self.config = ConfigParser()
        if not os.path.exists(custom_path):
            # copy default config to user home dir
            os.makedirs(os.path.dirname(custom_path), exist_ok=True)
            shutil.copyfile(default_path, custom_path)
            self.config.read(default_path)
        self.config.read(custom_path)

        logged_in = False
        # try to load token
        if os.path.exists(token_path):
            with open(token_path, 'rb') as f:
                self.__dict__ = pickle.load(f)

            # make sure token hasn't expired
            logged_in = self.validate()

        if not logged_in:
            # either the token expired or doesn't exist
            username, password = self._get_credentials()
            ProductionSession.__init__(self, username, password)

            accounts = Account.get_accounts(self)
            self.accounts = [acc for acc in accounts if not acc.is_closed]
            # write session token to cache
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, 'wb') as f:
                pickle.dump(self.__dict__, f)
            logger.debug('Logged in with new session, cached for next login.')
        else:
            logger.debug('Logged in with cached session.')

    def _get_credentials(self):
        username = (self.config['general'].get('username') or
                    os.getenv('TTCLI_USERNAME'))
        if not username:
            username = getpass.getpass('Username: ')
        password = (self.config['general'].get('password') or
                    os.getenv('TTCLI_PASSWORD'))
        if not password:
            password = getpass.getpass('Password: ')

        return username, password

    def get_account(self) -> Account:
        account = self.config['general'].get('default-account', None)
        if account:
            try:
                return next(a for a in self.accounts if a.account_number == account)
            except StopIteration:
                print_warning('Default account is set, but the account doesn\'t appear to exist!')

        for i in range(len(self.accounts)):
            if i == 0:
                print(f'{i + 1}) {self.accounts[i].account_number} '
                      f'{self.accounts[i].nickname} (default)')
            else:
                print(f'{i + 1}) {self.accounts[i].account_number} {self.accounts[i].nickname}')
        choice = 0
        while choice not in range(1, len(self.accounts) + 1):
            try:
                raw = input('Please choose an account: ')
                choice = int(raw)
            except ValueError:
                if not raw:
                    return self.accounts[0]
        return self.accounts[choice - 1]


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