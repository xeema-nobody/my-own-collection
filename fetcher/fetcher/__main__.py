import uvicorn

from fetcher.config import settings

# Loopback only: the fetcher drives a logged-in browser profile, never expose it.
uvicorn.run("fetcher.main:app", host="127.0.0.1", port=settings.fetcher_port)
