from app.providers.fetcher import FetchResponse
from app.providers.price.resolve import find_product

CARD = {"name": "Galarian Slowking V", "number": "179", "set": {"name": "Chilling Reign"}}
PRODUCT = "https://www.pricecharting.com/game/pokemon-chilling-reign/galarian-slowking-v-179"


class RedirectClient:
    def __init__(self, final_url):
        self.final_url = final_url

    async def fetch(self, site, url, **kw):
        return FetchResponse("ok", self.final_url, "t", "<html>no table</html>")


async def test_single_hit_redirect_is_the_product():
    url, fail = await find_product(CARD, RedirectClient(PRODUCT + "?q=x"), "pricecharting",
                                   "https://www.pricecharting.com/search-products?q=x",
                                   lambda html: [], None, product_marker="/game/")
    assert (url, fail) == (PRODUCT + "?q=x", None)


async def test_search_page_without_hits_is_not_found():
    url, fail = await find_product(CARD, RedirectClient("https://www.pricecharting.com/search-products?q=x"),
                                   "pricecharting", "https://www.pricecharting.com/search-products?q=x",
                                   lambda html: [], None, product_marker="/game/")
    assert url is None and fail.status == "not_found"
