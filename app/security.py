"""Phone mode: requests that come through the Caddy gate (tailnet) get a tiny allowlist, nothing else.

Caddy (127.0.0.1 only, behind `tailscale serve`) checks the Tailscale login and adds `X-Moc-Gate: <secret>`.
No header = laptop / curl / tests: behaviour unchanged. A wrong header is refused outright."""
import hmac

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

GATE_HEADER = "x-moc-gate"
# (method, path) the phone may call. Everything else is 403 in phone mode.
PHONE_ALLOWED = {("GET", "/api/scan/me"), ("POST", "/api/scan/identify"),
                 ("GET", "/api/scan/search"), ("POST", "/api/scan/add"), ("GET", "/health")}


def gate_state(request: Request) -> str:
    """'none' (no gate header), 'phone' (valid), 'bad' (present but wrong or phone mode off)."""
    given = request.headers.get(GATE_HEADER)
    if given is None:
        return "none"
    if settings.lan_gate_secret and hmac.compare_digest(given.encode(), settings.lan_gate_secret.encode()):
        return "phone"
    return "bad"


async def gate(request: Request, call_next):
    state = gate_state(request)
    request.state.phone = state == "phone"
    if state == "bad":
        return JSONResponse({"detail": "gate refused"}, status_code=403)
    if state == "phone":
        if (request.method, request.url.path) not in PHONE_ALLOWED:
            return JSONResponse({"detail": "not available from the phone"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != settings.lan_origin:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        host = request.headers.get("host", "")
        if not settings.lan_origin.endswith("://" + host):
            return JSONResponse({"detail": "host not allowed"}, status_code=403)
    return await call_next(request)


def require_laptop(request: Request) -> None:
    """Dependency for endpoints the phone must never reach (belt and braces next to the allowlist)."""
    if getattr(request.state, "phone", False):
        raise HTTPException(403, "not available from the phone")
