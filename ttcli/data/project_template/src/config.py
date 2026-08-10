from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )
    # configuration for our toy strategy
    LOTS: int = 1
    DELTA: int = 16
    SYMBOL: str = "SPY"
    TICK_WIDTH: Decimal = Decimal("0.01")

    # configuration for cache/database
    # DATABASE_URL: str
    REDIS_URL: str

    # required Tastytrade credentials
    # to obtain a secret and refresh token, follow the steps here:
    # https://tastyworks-api.rtfd.io/en/latest/sessions.html#creating-an-oauth-application
    TT_REFRESH: str
    TT_SECRET: str
    # you can buy a tastyware paper API key here: https://tastyware.dev/login
    TW_API_KEY: str
    TW_ACCOUNT: str
    # order adjustment configuration
    MIN_ADJUSTMENT_INTERVAL: float = 1
    MAX_ADJUSTMENT_INTERVAL: float = 10
    MAX_ADJUSTMENTS: int = 3


settings = Settings()  # type: ignore
