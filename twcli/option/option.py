from datetime import date
from typing import Optional

from tastyworks.models.option_chain import get_option_chain
from tastyworks.models.underlying import Underlying

from ..utils import RenewableTastyAPISession, get_tasty_monthly, is_monthly


async def choose_expiration(sesh: RenewableTastyAPISession, undl: Underlying,
                            all_expirations: Optional[bool] = False) -> date:
    chain = await get_option_chain(sesh, undl)
    exps = chain.get_all_expirations()
    if not all_expirations:
        exps = [exp for exp in exps if is_monthly(exp)]
    default = get_tasty_monthly()
    for i in range(len(exps)):
        if exps[i] == default:
            print(f'{i + 1}) {exps[i]} (default)')
        else:
            print(f'{i + 1}) {exps[i]}')
    choice = 0
    while choice not in range(1, len(exps) + 1):
        try:
            raw = input('Please choose an expiration: ')
            choice = int(raw)
        except ValueError:
            if not raw:
                return default

    return exps[choice - 1]
