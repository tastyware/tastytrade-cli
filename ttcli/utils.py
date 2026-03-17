import asyncio
import inspect
import json
import os
import pickle
from collections import defaultdict
from configparser import ConfigParser
from datetime import date
from decimal import Decimal
from functools import partial, wraps
from typing import Any, Awaitable, Callable, Self, Type, TypeVar

from anyio import create_task_group, move_on_after
from rich import print as rich_print
from tastytrade import Account, DXLinkStreamer, Session
from tastytrade.instruments import TickSize
from tastytrade.order import OrderAction
from tastytrade.streamer import U
from typer import Typer

from ttcli import CUSTOM_CONFIG_PATH, TOKEN_PATH, VERSION, logger

ZERO = Decimal(0)
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

config_path = os.path.join(os.path.expanduser("~"), CUSTOM_CONFIG_PATH)


def print_error(msg: str):
    rich_print(f"[bold red]Error: {msg}[/bold red]")


def print_warning(msg: str):
    rich_print(f"[light_coral]Warning: {msg}[/light_coral]")


def decimalify(val: str) -> Decimal:
    return Decimal(val)


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


def conditional_quantity(value: Decimal | int, action: OrderAction) -> str:
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
    def __init__(self, **_: Any):
        # load config; should always exist
        self.config = ConfigParser()
        self.config.read(config_path)
        refresh = self.config.get("general", "refresh_token", fallback=None)
        secret = self.config.get("general", "client_secret", fallback=None)
        super().__init__(secret, refresh)

    async def __ainit__(self) -> Self:
        # try to load token
        token_path = os.path.join(os.path.expanduser("~"), f"{TOKEN_PATH}.v{VERSION}")
        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                data = pickle.load(f)
                logger.debug("Logged in with cached session.")
                return self.deserialize(data)
        # either the token expired or doesn't exist
        accounts = await Account.get(self)
        self.accounts = [acc for acc in accounts if not acc.is_closed]
        # write session token to cache
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "wb") as f:
            data = self.serialize()
            pickle.dump(data, f)
        logger.debug("Logged in with new session, cached for next login.")
        return self

    def __await__(self):
        return self.__ainit__().__await__()

    def serialize(self) -> str:
        attrs = self.__dict__.copy()
        del attrs["_client"]
        del attrs["_lock"]
        del attrs["config"]
        attrs["accounts"] = [a.model_dump(mode="json") for a in self.accounts]
        return json.dumps(attrs)

    @classmethod
    def deserialize(cls, serialized: str) -> Self:
        deserialized: dict[str, Any] = json.loads(serialized)
        accounts = deserialized.pop("accounts")
        self = cls(
            provider_secret=deserialized["provider_secret"],
            refresh_token=deserialized["refresh_token"],
        )
        self.session_expiration = deserialized["session_expiration"]
        self.session_token = deserialized["session_token"]
        auth_headers = {"Authorization": f"Bearer {self.session_token}"}
        self._client.headers.update(auth_headers)
        self.accounts = [Account.model_validate(a) for a in accounts]
        return self

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


T = TypeVar("T")


async def gather(*awaitables: Awaitable[T]) -> tuple[T, ...]:
    """
    anyio-compatible implementation of asyncio.gather that runs tasks in a task group
    and collects the results.
    """
    if not awaitables:
        return ()
    results: list[Any] = [None] * len(awaitables)

    async def runner(awaitable: Awaitable[Any], i: int) -> None:
        results[i] = await awaitable

    async with create_task_group() as tg:
        for i, awaitable in enumerate(awaitables):
            tg.start_soon(runner, awaitable, i)
    return tuple(results)


def volfmt(n: int | float) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(n)
