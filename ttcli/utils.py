import asyncio
import getpass
import inspect
import json
import os
import pickle
from collections import defaultdict
from configparser import ConfigParser
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial, wraps
from typing import Any, Callable, Type

import httpx
from anyio import move_on_after
from rich import print as rich_print
from tastytrade import API_URL, Account, DXLinkStreamer, Session
from tastytrade.instruments import TickSize
from tastytrade.order import OrderAction
from tastytrade.streamer import U
from tastytrade.utils import TastytradeError, now_in_new_york
from typer import Typer

from ttcli import CUSTOM_CONFIG_PATH, TOKEN_PATH, VERSION, logger

ZERO = Decimal(0)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

_fmt = "%Y-%m-%d %H:%M:%S%z"
config_path = os.path.join(os.path.expanduser("~"), CUSTOM_CONFIG_PATH)


def print_error(msg: str):
    rich_print(f"[bold red]Error: {msg}[/bold red]")


def print_warning(msg: str):
    rich_print(f"[light_coral]Warning: {msg}[/light_coral]")


def decimalify(val: str) -> Decimal:
    return Decimal(val)


async def listen_events(
    dxfeeds: list[str], event_class: Type[U], streamer: DXLinkStreamer
) -> dict[str, U | None]:
    event_dict: dict[str, U | None] = defaultdict(lambda: None)
    await streamer.subscribe(event_class, dxfeeds)
    with move_on_after(3):
        async for event in streamer.listen(event_class):
            event_dict[event.event_symbol] = event
            if len(event_dict) == len(dxfeeds):
                break
    return event_dict


def conditional_color(value: Decimal, dollars: bool = True, round: bool = True) -> str:
    d = "$" if dollars else ""
    if round:
        return (
            f"[red]-{d}{abs(value):.2f}[/red]"
            if value < 0
            else f"[green]{d}{value:.2f}[/green]"
        )
    return f"[red]-{d}{abs(value)}[/red]" if value < 0 else f"[green]{d}{value}[/green]"


def conditional_quantity(value: Decimal, action: OrderAction) -> str:
    modified = value * (-1 if "Sell" in action.value else 1)
    return str(modified) if modified < 0 else f"+{modified}"


def round_to_width(x, base=Decimal(1)):
    return base * round(x / base)


def round_to_tick_size(price: Decimal, ticks: list[TickSize]) -> Decimal:
    for tick in ticks:
        if tick.threshold is None or price < tick.threshold:
            return round_to_width(price, tick.value)
    return price


class AsyncTyper(Typer):
    @staticmethod
    def maybe_run_async(decorator: Callable, func: Callable) -> Any:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            def runner(*args: Any, **kwargs: Any) -> Any:
                return asyncio.run(func(*args, **kwargs))

            decorator(runner)
        else:
            decorator(func)
        return func

    def callback(self, *args: Any, **kwargs: Any) -> Any:
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args: Any, **kwargs: Any) -> Any:
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)


class RenewableSession(Session):
    def __init__(self):
        token_path = os.path.join(os.path.expanduser("~"), f"{TOKEN_PATH}.v{VERSION}")
        logged_in = False
        # try to load token
        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                data = pickle.load(f)
                self._deserialize(data)

            # make sure token hasn't expired
            if now_in_new_york() > self.session_expiration - timedelta(seconds=30):
                try:
                    self.refresh()
                    logged_in = True
                except TastytradeError:
                    logger.debug("Failed to load session from token, reinitializing...")
                    logged_in = False

        # load config; should always exist
        self.config = ConfigParser()
        self.config.read(config_path)

        if not logged_in:
            # either the token expired or doesn't exist
            refresh, secret = self._get_credentials()
            Session.__init__(self, secret, refresh)

            # write session token to cache
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                conf = self.__dict__.pop("config")
                pickle.dump(self.serialize(), f)
                self.__dict__["config"] = conf
            logger.debug("Logged in with new session, cached for next login.")
        else:
            logger.debug("Logged in with cached session.")
        accounts = Account.get(self)
        self.accounts = [acc for acc in accounts if not acc.is_closed]

    def _get_credentials(self):
        refresh = os.getenv("TT_REFRESH")
        secret = os.getenv("TT_SECRET")
        refresh = refresh or self.config.get("general", "refresh_token")
        secret = secret or self.config.get("general", "client_secret")

        if not refresh:
            refresh = getpass.getpass("Refresh Token: ")
        if not secret:
            secret = getpass.getpass("Client Secret: ")

        return refresh, secret

    def get_account(self) -> Account:
        if len(self.accounts) == 1:  # auto-select if there's only 1 option
            return self.accounts[0]
        account = self.config.get("general", "default-account", fallback=None)
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

    def _deserialize(self, serialized: str):
        deserialized = json.loads(serialized)
        self.__dict__ = deserialized
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.session_token,
        }
        self.session_expiration = datetime.strptime(
            deserialized["session_expiration"], _fmt
        )
        self.streamer_expiration = datetime.strptime(
            deserialized["streamer_expiration"], _fmt
        )
        self.sync_client = httpx.Client(base_url=API_URL, headers=headers)
        self.async_client = httpx.AsyncClient(base_url=API_URL, headers=headers)


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
