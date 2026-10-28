# moc-fetcher

Host-Mac service that fetches pages from PriceCharting, Cardmarket and alt.xyz for the app. It drives real Google Chrome (own profile in `~/.moc-fetcher/profile`) over CDP, because Cloudflare blocks Playwright's Chromium on Cardmarket. Nothing runs until the app asks; Chrome closes after 120 s idle.

If a site shows a login or Cloudflare challenge, the Chrome tab is brought to the front and the fetch waits (`GET /status` -> `waiting_login:<site>`). Log in yourself; credentials are never read or stored.

## Setup

```bash
cd fetcher
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'     # no `playwright install`: system Chrome is used
python -m fetcher           # 127.0.0.1:8110
```

Or from the repo root: `scripts/fetcher.sh start|stop|status|logs` (log in `~/.moc-fetcher/fetcher.log`).

Env (prefix `FETCHER_`): `FETCHER_PORT`, `CHROME_PATH`, `PROFILE_DIR`, `CDP_PORT`, `IDLE_TIMEOUT_S`, `LOGIN_TIMEOUT_S`.

## API

`POST /fetch/{pricecharting|cardmarket|altxyz}` `{"url": "...", "wait_selector": null, "wait_ms": 0}` -> `{status, final_url, title, html, detail}`; `GET /status`; `POST /close`; `GET /health`.

Tests: `pytest` (fake browser, no network).
