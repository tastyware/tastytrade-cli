from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from itertools import batched
from typing import NamedTuple

from anyio import move_on_after
from pydantic import TypeAdapter
from streaq import Worker
from tastytrade import Account, DXLinkStreamer, Session
from tastytrade.dxfeed import Greeks
from tastytrade.instruments import Option, OptionType, get_option_chain
from tastytrade.market_data import get_market_data_by_type
from tastytrade.order import Leg, LimitOrder, OrderAction
from tastytrade.paper import PaperSession
from tastytrade.utils import TZ, get_tasty_monthly, today_in_new_york

from .config import settings
from .utils import (
    build_closing_legs,
    calculate_mid,
    follow_order,
    get_tasty_exit,
    logger,
    pool,
    redis,
    round_to_allowed,
)

LegListAdapter = TypeAdapter(list[Leg])


class WorkerContext(NamedTuple):
    chain: dict[date, list[Option]]
    session: Session
    paper: PaperSession


@asynccontextmanager
async def lifespan() -> AsyncGenerator[WorkerContext]:
    """
    Initialize worker dependencies on startup.
    """
    session = Session(settings.TT_SECRET, settings.TT_REFRESH)
    chain = await get_option_chain(session, settings.SYMBOL)
    paper = PaperSession(settings.TW_API_KEY)
    yield WorkerContext(chain, session, paper)


# our worker object
worker = Worker(prefetch=0, redis_pool=pool, tz=TZ, lifespan=lifespan, grace_period=15)


@worker.cron("30 9 * * mon-fri", timeout=timedelta(minutes=5))
async def execute_tasty_strategy() -> None:
    # check if today is the monthly expiration
    if today_in_new_york() == get_tasty_exit():
        # implication: if we have an open position, it's now 21 DTE and can be closed
        # we can also open a new position which will be 45 DTE
        logger.info("Market opened, executing strategy...")
        tasty_monthly = get_tasty_monthly()
        subchain = worker.context.chain[tasty_monthly]
        dxfeeds = [o.streamer_symbol for o in subchain]
        # idea: we want to close our previous position we placed at 45 DTE that's now 21 DTE.
        # we want to roll it to the next 45 DTE position (next month's monthly).
        # this can be a single trade with opening/closing legs (or just opening if we have no position).
        async with DXLinkStreamer(worker.context.session) as streamer:
            # subscribe to options chain
            for chunk in batched(dxfeeds, 1000):
                await streamer.subscribe(Greeks, chunk, refresh_interval=10)
            greeks: dict[str, Greeks] = {}
            with move_on_after(3):  # wait max 3 seconds for greeks to come in
                async for greek in streamer.listen(Greeks):
                    greeks[greek.event_symbol] = greek
                    if len(greeks) == len(dxfeeds):
                        break
            logger.info(f"Fetched greeks for {len(greeks)} symbols.")
            puts = {
                p.streamer_symbol: p
                for p in subchain
                if p.option_type == OptionType.PUT and p.streamer_symbol in greeks
            }
            calls = {
                c.streamer_symbol: c
                for c in subchain
                if c.option_type == OptionType.CALL and c.streamer_symbol in greeks
            }
            # calculate closest put to target delta
            short_put = min(
                puts.values(),
                key=lambda p: abs(
                    greeks[p.streamer_symbol].delta * 100 + settings.DELTA
                ),
            )
            # calculate closest call to target delta
            short_call = min(
                calls.values(),
                key=lambda c: abs(
                    greeks[c.streamer_symbol].delta * 100 - settings.DELTA
                ),
            )
        # build order with opening & closing legs
        legs = [
            short_put.build_leg(settings.LOTS, OrderAction.SELL_TO_OPEN),
            short_call.build_leg(settings.LOTS, OrderAction.SELL_TO_OPEN),
        ]
        symbols = [short_put.symbol, short_call.symbol]
        raw = await redis.get("closing")
        if raw:
            existing = LegListAdapter.validate_json(raw)
            legs.extend(existing)
            symbols.extend([leg.symbol for leg in existing])
        # fetch market prices for all legs
        data = await get_market_data_by_type(worker.context.session, options=symbols)
        mid_price = calculate_mid(legs, {d.symbol: d for d in data})
        order = LimitOrder(legs=legs, price=mid_price)
        round_to_allowed(order)
        logger.info(
            f"Calculated mid price of ${order.price:.2f} for {settings.SYMBOL} "
            f"{short_put.strike_price}/{short_call.strike_price} strangle."
        )
        account = await Account.get(worker.context.paper, settings.TW_ACCOUNT)
        # place order in account and adjust to try to get a fill
        await follow_order(order, account, worker.context.paper)
        # next run will have access to closing legs
        closing = build_closing_legs(order)
        await redis.set("closing", LegListAdapter.dump_json(closing))
