import httpx


async def fetch_rate(base: str, quote: str) -> float:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://api.frankfurter.dev/v1/latest", params={"base": base, "symbols": quote})
        r.raise_for_status()
        return float(r.json()["rates"][quote])
