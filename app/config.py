from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "owncollection"
    cors_origins: str = "http://localhost:5180"
    # Host headers the API answers to (DNS-rebinding guard); the FE and healthcheck use localhost
    allowed_hosts: str = "localhost,127.0.0.1"
    base_currency: str = "EUR"
    pokemontcg_api_key: str = ""
    pokemontcg_base_url: str = "https://api.pokemontcg.io/v2"
    pricecharting_token: str = ""
    fetcher_url: str = "http://host.docker.internal:8110"
    scheduler_enabled: bool = False
    price_refresh_cron: str = "0 4 * * *"
    price_fetch_cron: str = "30 4 * * *"
    snapshot_cron: str = "0 6 * * *"
    catalog_import_cron: str = "0 3 * * 0"
    # max cards per scheduled scraped fetch; stalest first, the rest resumes next run
    scheduler_fetch_cap: int = 300
    # valuation (D-A): sold beats aggregate when >= sold_min_sales sales in the window
    sold_min_sales: int = 3
    sold_window_days: int = 90
    sold_sample: int = 10
    # order of trust for aggregate (market) prices; Cardmarket catalog figure can be months stale
    preferred_sources: str = "pricecharting,tcgplayer,cardmarket_web,cardmarket,altxyz"
    # market points older than this are only used when no fresher source has the grade
    market_max_age_days: int = 180
    # a source this many % away from the median of all sources is flagged (needs >= 3 sources)
    outlier_pct: int = 40


settings = Settings()
