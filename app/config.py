from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "owncollection"
    cors_origins: str = "http://localhost:5180"
    # Host headers the API answers to (DNS-rebinding guard); the FE and healthcheck use localhost
    allowed_hosts: str = "localhost,127.0.0.1"
    base_currency: str = "EUR"
    # catalog + aggregate price source: pokemontcg | tcgdex (pokemontcg.io keys expire 2027-03-01)
    catalog_provider: str = "pokemontcg"
    tcgdex_base_url: str = "https://api.tcgdex.net/v2/en"
    pokemontcg_api_key: str = ""
    pokemontcg_base_url: str = "https://api.pokemontcg.io/v2"
    pricecharting_token: str = ""
    fetcher_url: str = "http://host.docker.internal:8110"
    scheduler_enabled: bool = False
    price_refresh_cron: str = "0 4 * * *"
    price_fetch_cron: str = "30 4 * * *"
    snapshot_cron: str = "0 6 * * *"
    catalog_import_cron: str = "0 3 * * 0"
    alert_prune_cron: str = "30 6 * * *"
    # max cards per scheduled scraped fetch; stalest first, the rest resumes next run
    scheduler_fetch_cap: int = 300
    # fetch one catalog price in the background when a card without prices joins the collection / wishlist
    price_on_add: bool = True
    # include wishlisted cards in the scheduled scraped fetch (false = collection only)
    scheduler_fetch_wishlist: bool = True
    # read alert events older than this many days are deleted by the scheduler; 0 keeps them all
    alert_events_keep_days: int = 90
    # alt.xyz sold-list pages read per card (page 1 + more while listings stay inside the sold window)
    altxyz_max_pages: int = 3
    # ...and no sale older than this many days is kept: stale sales skew toward lower values
    altxyz_max_age_days: int = 180
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
    # seconds the whole-collection valuation is cached in memory (writers also drop it); 0 = off
    valuation_cache_ttl: int = 60
    # Phone scanning over the tailnet (docs/architecture.md "Phone scanning"). Empty secret = phone mode off:
    # a request carrying X-Moc-Gate is then refused. Set by scripts/lan.sh in lan/lan.env, never in .env.
    lan_gate_secret: str = ""
    # exact https origin of the tailnet host the phone uses (Origin guard, phone mode only)
    lan_origin: str = ""
    # Tailscale login the Caddy gate accepts; shown on the laptop, enforced by Caddy
    lan_login: str = ""
    # card name reader: tesseract (local, no network)
    ocr_provider: str = "tesseract"
    tesseract_cmd: str = "tesseract"
    scan_max_image_mb: int = 8
    scan_event_keep_days: int = 7


settings = Settings()
