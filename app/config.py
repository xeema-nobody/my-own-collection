from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "owncollection"
    cors_origins: str = "http://localhost:5180"
    base_currency: str = "EUR"
    pokemontcg_api_key: str = ""
    pokemontcg_base_url: str = "https://api.pokemontcg.io/v2"
    pricecharting_token: str = ""
    fetcher_url: str = "http://host.docker.internal:8110"
    scheduler_enabled: bool = False
    price_refresh_cron: str = "0 4 * * *"
    # valuation (D-A): sold beats aggregate when >= sold_min_sales sales in the window
    sold_min_sales: int = 3
    sold_window_days: int = 90
    sold_sample: int = 10
    # order of trust for aggregate (market) prices; Cardmarket catalog figure can be months stale
    preferred_sources: str = "pricecharting,tcgplayer,cardmarket_web,cardmarket,altxyz"
    # market points older than this are only used when no fresher source has the grade
    market_max_age_days: int = 180


settings = Settings()
