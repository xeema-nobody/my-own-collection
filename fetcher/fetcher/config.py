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
    login_timeout_s: float = 300
    poll_interval_s: float = 1


settings = Settings()
