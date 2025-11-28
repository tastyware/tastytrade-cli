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

from calendar import monthrange
import exchange_calendars as xcals
from zoneinfo import ZoneInfo
import pandas as pd


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

def is_third_friday(date, tz):
    def get_third_friday_or_thursday(year, month, tz):
        _, last = monthrange(year, month)
        first = datetime(year, month, 1)
        last = datetime(year, month, last)
        result = xcals.get_calendar("XNYS", start=first, end=last)
        result = result.sessions.to_pydatetime()

        found = [None, None]
        for i in result:
            if i.weekday() == 4 and 15 <= i.day <= 21 and i.month == month:
                # Third Friday
                found[0] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
            elif i.weekday() == 3 and 15 <= i.day <= 21 and i.month == month:
                # Thursday alternative
                found[1] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
        return found[0] or found[1], result

    # We try with current month
    candidate, result = get_third_friday_or_thursday(date.year, date.month, tz)
    if candidate and pd.Timestamp(date).date() > candidate.date():
        # If current date is over, try next month
        next_month = date.month + 1
        next_year = date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        candidate, result = get_third_friday_or_thursday(next_year, next_month, tz)    
    return candidate, result


def get_SOFR_ticker(): # To know th risk free yield
    month_codes = {3: "H", 6: "M", 9: "U", 12: "Z"}

    def third_wednesday(year, month):
        count = 0
        for day in range(1, 32):
            try:
                d = date(year, month, day)
            except ValueError:
                break
            if d.weekday() == 2:  # Wednesday
                count += 1
                if count == 3:
                    return d
        return None

    def sofr_expiration_date(year, month):
        wednesday = third_wednesday(year, month)
        return wednesday - timedelta(days=5)

    def next_sofr_contract(today=None):
        if today is None:
            today = datetime.now(ZoneInfo("America/New_York")).date()
        year = today.year
        quarterly_months = [3, 6, 9, 12]

        for i, m in enumerate(quarterly_months):
            expiration = sofr_expiration_date(year, m)
            if today < expiration:
                contract_month = m
                break
            elif today == expiration:
                contract_month = quarterly_months[i + 1] if i + 1 < len(quarterly_months) else 3
                if contract_month == 3:
                    year += 1
                break
        else:
            contract_month = 3
            year += 1

        month_code = month_codes[contract_month]
        year_code = str(year)[-1]
        ticker = f"/SR3{month_code}{year_code}"
        expiration_date = pd.Timestamp(sofr_expiration_date(year, contract_month)).tz_localize(ZoneInfo("America/New_York"))

        return ticker, expiration_date

    ticker, expiration = next_sofr_contract()
    return ticker

def next_open_day(date):
    tz_europe = ZoneInfo("Europe/Madrid") # It's easier to calculate the next day using europe time, only have to add 2 or 1 hour
    now_europe = datetime.now(tz_europe)
    hour = now_europe.hour
    days_to_add = 2 if 22 <= hour <= 23 else 1
    next_day = date + timedelta(days=days_to_add)

    _, last = monthrange(next_day.year, next_day.month)
    first = datetime(next_day.year, next_day.month, 1)
    last = datetime(next_day.year, next_day.month, last)
    calendar = xcals.get_calendar("XNYS", start=first, end=last)
    trading_days = calendar.sessions.to_pydatetime()
    trading_dates = [d.date() for d in trading_days]

    while next_day not in trading_dates:
        next_day += timedelta(days=1)
    return next_day

def expir_to_datetime(expir: str):
    tz = "America/New_York"
    today = datetime.now(ZoneInfo(tz))
    today_date = today.date()

    expir = expir.lower().strip()

    _, last = monthrange(today.year, today.month)
    first = datetime(today.year, today.month, 1)
    last = datetime(today.year, today.month, last)
    calendar = xcals.get_calendar("XNYS", start=first, end=last)
    trading_days = calendar.sessions.to_pydatetime()
    trading_dates = [d.date() for d in trading_days]

    if expir == "0dte":
        # If market is open today, then today is the returned date
        if today_date in trading_dates:
            return today_date
        else:
            return next_open_day(today_date)

    elif expir.endswith("dte"):
        try:
            dte = int(expir.replace("dte", ""))
            future_date = today_date
            for _ in range(dte):
                future_date = next_open_day(future_date)
            return future_date
        except ValueError:
            raise ValueError(f"Format for expiration not recognised: {expir}")

    elif expir == "weekly":
        # Buscar viernes de esta semana
        this_friday = today_date + timedelta((4 - today_date.weekday()) % 7)

        _, last = monthrange(this_friday.year, this_friday.month)
        first = datetime(this_friday.year, this_friday.month, 1)
        last = datetime(this_friday.year, this_friday.month, last)
        calendar = xcals.get_calendar("XNYS", start=first, end=last)
        trading_days = calendar.sessions.to_pydatetime()
        trading_dates = [d.date() for d in trading_days]

        if this_friday in trading_dates:
            return this_friday
        elif (this_friday - timedelta(days=1)) in trading_dates:
            return this_friday - timedelta(days=1)
        else:
            raise ValueError("Friday and thursday is closed.")


    elif expir == "opex":
        date_, result = is_third_friday(today_date, tz)
        return date_.date()

    elif expir == "monthly":
        return trading_dates[-1]

    else:
        raise ValueError(f"Expiration type unknown: {expir}")

       