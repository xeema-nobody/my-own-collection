from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

HOME = Path.home() / ".moc-fetcher"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FETCHER_", extra="ignore")

    fetcher_port: int = 8110
    chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    profile_dir: Path = HOME / "profile"      # dedicated profile, never the user's main one
    failures_dir: Path = HOME / "failures"
    cdp_port: int = 9333
    idle_timeout_s: float = 120
    nav_timeout_s: float = 45
    challenge_grace_s: float = 10             # let Cloudflare self-resolve before asking the user
    click_settle_s: float = 3                 # let SPAs hydrate before clicking
    page_change_s: float = 8                  # max wait for the list to change after a next-page click
    page_poll_s: float = 0.25
    login_timeout_s: float = 300
    poll_interval_s: float = 1
    notify_enabled: bool = True               # macOS notification for new alert events
    app_url: str = "http://127.0.0.1:8100"
    notify_poll_s: float = 60
    notify_state: Path = HOME / "notified.json"
    publish_max_per_day: int = 10             # Vinted uploads per calendar day (real runs only)
    publish_min_gap_s: float = 90             # pause between items in one run (+ up to 50 % random)
    publish_action_delay_s: tuple[float, float] = (0.6, 1.8)
    publish_state: Path = HOME / "publish_day.json"
    sites_file: Path = HOME / "sites.json"    # extra sites, re-read on every request


settings = Settings()
