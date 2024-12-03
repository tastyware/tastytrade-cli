import getpass
import logging
import os
import pickle
from configparser import ConfigParser
from datetime import date
from decimal import Decimal
from typing import Any, Type

from httpx import AsyncClient, Client
from rich import print as rich_print
from tastytrade import Account, DXLinkStreamer, Session
from tastytrade.dxfeed import Quote
from tastytrade.instruments import TickSize
from tastytrade.streamer import U

logger = logging.getLogger(__name__)
VERSION = "0.3"
ZERO = Decimal(0)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

CUSTOM_CONFIG_PATH = ".config/ttcli/ttcli.cfg"
TOKEN_PATH = ".config/ttcli/.session"

config_path = os.path.join(os.path.expanduser("~"), CUSTOM_CONFIG_PATH)


def print_error(msg: str):
    rich_print(f"[bold red]Error: {msg}[/bold red]")


def print_warning(msg: str):
    rich_print(f"[light_coral]Warning: {msg}[/light_coral]")


def round_to_width(x, base=Decimal(1)):
    return base * round(x / base)


def round_to_tick_size(price: Decimal, ticks: list[TickSize]) -> Decimal:
    for tick in ticks:
        if tick.threshold is None or price < tick.threshold:
            return round_to_width(price, tick.value)
    return price  # unreachable


async def listen_events(
    dxfeeds: list[str], event_class: Type[U], streamer: DXLinkStreamer
) -> dict[str, U]:
    event_dict = {}
    await streamer.subscribe(event_class, dxfeeds)
    async for event in streamer.listen(event_class):
        if event_class == Quote and event.bidPrice is None:  # type: ignore
            continue
        event_dict[event.eventSymbol] = event
        if len(event_dict) == len(dxfeeds):
            return event_dict
    return event_dict  # unreachable


class RenewableSession(Session):
    def __init__(self):
        token_path = os.path.join(os.path.expanduser("~"), TOKEN_PATH)
        logged_in = False
        # try to load token
        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                data = pickle.load(f)
                self.deserialize(data)

            # make sure token hasn't expired
            logged_in = self.validate()

        # load config; should always exist
        self.config = ConfigParser()
        self.config.read(config_path)

        if not logged_in:
            # either the token expired or doesn't exist
            username, password = self._get_credentials()
            Session.__init__(self, username, password)

            # write session token to cache
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                pickle.dump(self.serialize(), f)
            logger.debug("Logged in with new session, cached for next login.")
        else:
            logger.debug("Logged in with cached session.")
        accounts = Account.get_accounts(self)
        self.accounts = [acc for acc in accounts if not acc.is_closed]

    def deserialize(self, data: dict[str, Any]):
        self.session_token = data["session_token"]
        self.remember_token = data["remember_token"]
        self.streamer_token = data["streamer_token"]
        self.dxlink_url = data["dxlink_url"]
        self.is_test = data["is_test"]
        self.sync_client = Client(
            base_url=data["base_url"],
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": data["session_token"],
            },
        )
        self.async_client = AsyncClient(
            base_url=data["base_url"],
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": data["session_token"],
            },
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "session_token": self.session_token,
            "remember_token": self.remember_token,
            "base_url": str(self.sync_client.base_url),
            "streamer_token": self.streamer_token,
            "dxlink_url": self.dxlink_url,
            "is_test": self.is_test,
        }

    def _get_credentials(self):
        username = os.getenv("TT_USERNAME")
        password = os.getenv("TT_PASSWORD")
        if self.config.has_section("general"):
            username = username or self.config["general"].get("username")
            password = password or self.config["general"].get("password")

        if not username:
            username = getpass.getpass("Username: ")
        if not password:
            password = getpass.getpass("Password: ")

        return username, password

    def get_account(self) -> Account:
        account = self.config["general"].get("default-account", None)
        if account:
            try:
                return next(a for a in self.accounts if a.account_number == account)
            except StopIteration:
                print_warning(
                    "Default account is set, but the account doesn't appear to exist!"
                )

        for i in range(len(self.accounts)):
            if i == 0:
                print(
                    f"{i + 1}) {self.accounts[i].account_number} "
                    f"{self.accounts[i].nickname} (default)"
                )
            else:
                print(
                    f"{i + 1}) {self.accounts[i].account_number} {self.accounts[i].nickname}"
                )
        choice = 0
        while choice not in range(1, len(self.accounts) + 1):
            try:
                raw = input("Please choose an account: ")
                choice = int(raw)
            except ValueError:
                return self.accounts[0]
        return self.accounts[choice - 1]


def is_monthly(day: date) -> bool:
    return day.weekday() == 4 and 15 <= day.day <= 21


def get_confirmation(prompt: str, default: bool = True) -> bool:
    while True:
        answer = input(prompt).lower()
        if not answer:
            return default
        if answer[0] == "y":
            return True
        if answer[0] == "n":
            return False
