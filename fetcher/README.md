# moc-fetcher

Host-Mac service that fetches pages from PriceCharting, Cardmarket and alt.xyz (and, from roadmap 5f, the PSA and Beckett cert pages) for the app. It drives real Google Chrome (own profile in `~/.moc-fetcher/profile`) over CDP, because Cloudflare blocks Playwright's Chromium on Cardmarket. Nothing runs until the app asks; Chrome closes after 120 s idle.

If a site shows a login or Cloudflare challenge, the Chrome tab is brought to the front and the fetch waits (`GET /status` -> `waiting_login:<site>`). Log in yourself; credentials are never read or stored.

## Setup

```bash
cd fetcher
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'     # no `playwright install`: system Chrome is used
python -m fetcher           # 127.0.0.1:8110
```

Or from the repo root: `scripts/fetcher.sh start|stop|restart|status|logs` (log in `~/.moc-fetcher/fetcher.log`).

Env (prefix `FETCHER_`): `FETCHER_PORT`, `CHROME_PATH`, `PROFILE_DIR`, `CDP_PORT`, `IDLE_TIMEOUT_S`, `LOGIN_TIMEOUT_S`, `NOTIFY_ENABLED`, `APP_URL`, `NOTIFY_POLL_S`, `NOTIFY_STATE`.

## Alert notifications
The fetcher also polls the app (`FETCHER_APP_URL`, default `http://127.0.0.1:8100`) every `FETCHER_NOTIFY_POLL_S` (60) seconds for unread alert events and shows one macOS notification (via `osascript`) for events it has not announced yet: the event text for one, "N new price alerts" for several. Off switch: `FETCHER_NOTIFY_ENABLED=false`.

- Dedupe state: `~/.moc-fetcher/notified.json` (`FETCHER_NOTIFY_STATE`): high-water mark + notified ids. Reading an alert in the UI does not matter. Delete the file to reseed.
- First run (no state file) seeds silently: the existing unread backlog is not announced.
- App down or osascript failing: logged at debug, retried next tick. While the Mac sleeps or the fetcher is stopped nothing is shown; events queued meanwhile arrive as one summary on return.
- macOS must allow notifications for the app that runs `osascript` (System Settings -> Notifications -> Script Editor, or the terminal app that started the fetcher). No click-through.

## API

`POST /fetch/{pricecharting|cardmarket|altxyz}` `{"url": "...", "wait_selector": null, "click_text": null, "click_labels": [], "pages": 1, "next_label": null, "wait_ms": 0}` -> `{status, final_url, title, html, htmls, detail}`; `GET /status`; `POST /close`; `GET /health`.

`pages` > 1 with `next_label` (and `wait_selector`, used as the list signature) clicks the control in the same tab after loading once and returns one snapshot per page in `htmls` (`html` = first). It waits for the list to change after each click and stops early, without error, when the control is missing or the list stops changing.

Tests: `pytest` (fake browser, no network).

## Sites

Built-in: pricecharting, cardmarket, altxyz, psa, beckett (the last two read slab cert pages). Add more without a restart in `~/.moc-fetcher/sites.json`, re-read on every request:

```json
[{"id": "cgc", "hosts": ["cgccards.com"], "min_interval_s": 4, "cookie_button": null}]
```

`GET /health` returns `{"ok": true, "sites": [...]}`. Unattended fetches (scans, scheduler) wait the 10 s Cloudflare challenge grace, then fail as `blocked`; they never wait for a login.
