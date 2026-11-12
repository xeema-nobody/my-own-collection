# Vinted publisher extension

Chrome MV3 extension that works the app's publish queue in your own logged-in Vinted tab. It stores no credentials and never solves a CAPTCHA, login or dialog: on anything unexpected it releases the item and stops.

## Install (once)
1. Open `chrome://extensions`, switch on **Developer mode** (top right).
2. **Load unpacked**, pick the `extension/` folder of this repo.
3. The extension ID must be `bimomfclaapdbjclnekkhegdlpjcnnkb` (pinned by the manifest key; the backend allows only this origin). Pin the extension icon to the toolbar.
4. Be logged in to https://www.vinted.nl in this Chrome.

After editing extension files: click the reload icon on its card in `chrome://extensions`.

## Dry run on one queued card
1. App: confirm one card with "Publish on Vinted" (collection drawer). Leave `docker compose up` running (API on :8100).
2. Extension popup: **Dry run** ticked (default).
3. App: Settings > Data > "Vinted publish queue" > **Publish waiting**. A new Vinted tab opens on `/items/new#moc-publish`.
4. A banner at the top shows the steps. It fills photos, title, description, condition, parcel, price, reads everything back, then shows "DRY RUN OK", releases the item (back to Waiting) and stops. Nothing is uploaded.
5. Report what the banner said (or the error) and what the form looks like.

A real run (Dry run unticked) clicks Upload, reads the item URL from your profile, reports it, waits 90-135 s and takes the next waiting item (max 10 uploads per day). Do the first real Upload only after saying OK in chat.

## Stop
Banner **Stop** button or popup **Stop run**: releases the claimed item and ends the run.

## Tests
`cd extension && npm install && npm test` (vitest + jsdom, recipe only).
