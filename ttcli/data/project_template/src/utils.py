import logging
import math
import random
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from anyio import sleep
from coredis import ConnectionPool, PureToken, Redis
from tastytrade import Account, Session
from tastytrade.instruments import OCC
from tastytrade.market_data import MarketData
from tastytrade.order import (
    Leg,
    LimitOrder,
    MarketOrder,
    NotionalOrder,
    OrderAction,
    OrderStatus,
    StopLimitOrder,
)
from tastytrade.utils import (
    NYSE,
    TastytradeError,
    get_third_friday,
    is_market_open_on,
    now_in_new_york,
    today_in_new_york,
)

from .config import settings

# logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s")
# use new york time for logs
formatter.converter = lambda *args: now_in_new_york().timetuple()  # type: ignore
formatter.datefmt = "%H:%M:%S"
handler.setFormatter(formatter)
logger.addHandler(handler)


redis_url = settings.REDIS_URL
# for connections to heroku redis
if redis_url.startswith("rediss"):
    redis_url += "?ssl_cert_reqs=none"
pool = ConnectionPool.from_url(redis_url, decode_responses=True)
# redis client for use elsewhere
redis = Redis(connection_pool=pool, decode_responses=True)


async def idempotent(key: str, ttl: timedelta | int | None = 60) -> bool:
    """
    Shields code from being run multiple times.

    :param key: idempotency key to use
    :param ttl: how long to prevent duplicate runs, defaults to 1 minute
    """
    return await redis.set(f"pydempotent:{key}", 1, condition=PureToken.NX, ex=ttl)


def next_day(day: date | None = None) -> date:
    """
    Get the next market day from the current (or provided) date.

    :param day: date to calculate next market day from, defaults to today
    """
    day = day or today_in_new_york()
    date_range = NYSE.valid_days(day + timedelta(days=1), day + timedelta(days=5))
    return date_range.to_pydatetime()[0].date()


def get_tasty_exit(day: date | None = None) -> date:
    """
    Get the next exit day (~21 DTE for monthly) from the current (or provided) date.

    :param day: date to calculate next exit day from, defaults to today
    """
    today = day or today_in_new_york()
    # next month's monthly
    exp = get_third_friday(get_third_friday(today) + timedelta(weeks=4))
    target = exp - timedelta(days=21)
    while not is_market_open_on(target):
        target -= timedelta(days=1)
    if target < today:
        # already past, do the following month
        exp = get_third_friday(exp + timedelta(weeks=4))
        target = exp - timedelta(days=21)
        while not is_market_open_on(target):
            target -= timedelta(days=1)
    return target


def calculate_mid(legs: Iterable[Leg], prices: dict[OCC, MarketData]) -> Decimal:
    """
    Given a mapping of OCC symbol -> `MarketData`, calculate the mid price for a spread
    with an arbitrary number of legs. This should match the mid price shown on official
    Tastytrade platforms.

    :param legs: iterable of Tastytrade `Leg` objects
    :param prices: mapping of OCC symbol -> `MarketData` fetched for that symbol

    :return: mid price calculated for arbitrarily complex spread
    """
    size = math.gcd(*[int(leg.quantity or 0) for leg in legs])
    longs = [leg for leg in legs if leg.action.multiplier > 0]
    shorts = [leg for leg in legs if leg.action.multiplier < 0]
    long_asks = sum(prices[long.symbol].ask * long.quantity / size for long in longs)  # type: ignore
    long_bids = sum(prices[long.symbol].bid * long.quantity / size for long in longs)  # type: ignore
    short_bids = sum(
        prices[short.symbol].bid * short.quantity / size  # type: ignore
        for short in shorts
    )
    short_asks = sum(
        prices[short.symbol].ask * short.quantity / size  # type: ignore
        for short in shorts
    )
    opp = short_bids - long_asks
    nat = short_asks - long_bids
    return Decimal(nat + opp) / 2


def round_to_allowed(order: LimitOrder | StopLimitOrder) -> None:
    """
    Round the given order's limit price to the nearest valid price, given the tick
    width configured in `Settings.TICK_WIDTH`.

    :param order: order to round price of
    """
    base = settings.TICK_WIDTH
    order.price = base * round(order.price / base)


async def follow_order(order: LimitOrder, account: Account, session: Session) -> int:
    """
    Place an order in the given account, then adjust it according to the configuration
    until it fills or MAX_ADJUSTMENTS is hit.

    :param order: order to place and monitor
    :param account: account to place order in
    :param session: paper or live session object for API

    :return: the ID of the order that filled
    """
    # only allow one trade entry per day. protects against rare double orders
    if not await idempotent(account.account_number, ttl=timedelta(hours=7)):
        raise RuntimeError(f"Trade already placed in account {account.account_number}!")
    placed = (await account.place_order(session, order, dry_run=False)).order
    logger.info(
        f"Placed initial order {placed.id} in account {account.account_number}."
    )
    try:
        for _ in range(settings.MAX_ADJUSTMENTS):
            await sleep(
                random.uniform(
                    settings.MIN_ADJUSTMENT_INTERVAL, settings.MAX_ADJUSTMENT_INTERVAL
                )
            )
            order.price -= settings.TICK_WIDTH
            # this will raise if the order was filled
            placed = await account.replace_order(session, placed.id, order)
            logger.info(
                f"Replaced with order {placed.id} in account {account.account_number}."
            )
        # failed to place within constraints
        await account.delete_order(session, placed.id)
        logger.info(f"Maximum adjustments of {settings.MAX_ADJUSTMENTS} reached!")
        raise RuntimeError(f"Trade aborted in account {account.account_number}!")
    except TastytradeError:
        # if it got filled, we're fine; otherwise, raise
        await sleep(1)
        placed = await account.get_order(session, placed.id)
        if placed.status != OrderStatus.FILLED:
            raise
    logger.info(f"Order {placed.id} filled in account {account.account_number}!")
    return placed.id


_matching = {
    OrderAction.BUY_TO_OPEN: OrderAction.SELL_TO_CLOSE,
    OrderAction.SELL_TO_OPEN: OrderAction.BUY_TO_CLOSE,
}


def build_closing_legs(opening: LimitOrder | MarketOrder | NotionalOrder) -> list[Leg]:
    """
    Build opposite, closing legs for the given opening trade.

    :param opening: opening order to create matching closing legs for
    """
    return [
        leg.model_copy(deep=True, update={"action": _matching[leg.action]})
        for leg in opening.legs
        if leg.action in _matching
    ]
