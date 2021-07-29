import getpass
import os
from decimal import Decimal as D

from tastyworks.models.session import TastyAPISession

VERSION = '0.3.0'
ZERO = D(0)

_TOKEN_PATH = '.tastyworks/twcli/sesh'


class TastyworksCLIError(Exception):
    pass


class RenewableTastyAPISession(TastyAPISession):
    def __init__(self, API_url=None):
        path = os.path.join(os.path.expanduser('~'), _TOKEN_PATH)

        # try to load token
        if os.path.exists(path):
            print('Reusing cached session token to authenticate.')
            with open(path) as f:
                self.session_token = f.read().strip()

            self.API_url = API_url if API_url else 'https://api.tastyworks.com'
            self.username = 'foo'
            self.password = 'bar'

            # make sure token hasn't expired
            self.logged_in = self._validate_session()
        else:
            username, password = self._get_credentials()
            TastyAPISession.__init__(self, username, password)

            # write session token to cache
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(self.session_token)

    def _get_credentials(self):
        username = os.getenv('TW_USER')
        if not username:
            username = getpass.getpass('Username: ')
        password = os.getenv('TW_PASS')
        if not password:
            password = getpass.getpass('Password: ')

        return username, password
