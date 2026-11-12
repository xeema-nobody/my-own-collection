import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.providers.price import SCRAPED

Condition = Literal["NM", "LP", "MP", "HP", "DMG"]
Language = Literal["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"]
Grader = Literal["PSA", "BGS", "CGC", "SGC", "ACE", "OTHER"]


class Grading(BaseModel):
    company: Grader
    grade: float = Field(ge=1, le=10)
    cert_number: str | None = Field(default=None, max_length=20)
    grader_name: str | None = Field(default=None, max_length=40, description="the grader's name when company is OTHER")
    report_url: str | None = Field(default=None, max_length=200, description="set by the server from the cert template")
    cert_info: dict | None = Field(default=None, description="grader's cert page snapshot, set by the server")

    @model_validator(mode="after")
    def _clean(self):
        name = (self.grader_name or "").strip()
        self.grader_name = name or None if self.company == "OTHER" else None
        if self.cert_number is not None:
            self.cert_number = self.cert_number.strip() or None
        return self


AcqType = Literal["purchased", "pulled", "traded", "gift", "other"]


class Acquired(BaseModel):
    type: AcqType | None = None  # None = not set (treated as non-pulled)
    price: int | None = Field(default=None, ge=0, description="cents per copy; 0 or None = no cost recorded (excluded from P/L)")
    currency: str = "EUR"
    date: dt.date | None = None
    source: str | None = None  # where it was bought


class AcquiredPatch(BaseModel):
    """Partial edit: only fields sent are applied (explicit null clears one)."""
    type: AcqType | None = None
    price: int | None = Field(default=None, ge=0, description="cents per copy")
    currency: str | None = None
    date: dt.date | None = None
    source: str | None = None

    @model_validator(mode="after")
    def _currency(self):
        if "currency" in self.model_fields_set and not self.currency:
            raise ValueError("currency cannot be cleared")
        return self


class BulkRemoveIn(BaseModel):
    """Take whole stacks out of the collection, one reason for all (history is kept in `collection_exits`).
    Sold carries no price here: a per-copy sale price belongs to the single-stack form."""
    ids: list[str] = Field(min_length=1, max_length=500)
    reason: Literal["sold", "gifted", "removed"] = "removed"
    note: str | None = Field(default=None, max_length=300)


class BulkIdsIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class BulkAcquiredIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    acquired: AcquiredPatch

    @model_validator(mode="after")
    def _some(self):
        if not self.acquired.model_fields_set:
            raise ValueError("nothing to change")
        return self


class CollectionIn(BaseModel):
    card_id: str
    variant: str | None = None  # None when the card has no distinct variants
    language: Language = "en"
    condition: Condition | None = None
    grading: Grading | None = None
    quantity: int = Field(default=1, ge=1)
    acquired: Acquired | None = None
    notes: str | None = None
    tags: list[str] = []

    @model_validator(mode="after")
    def _check(self):
        if self.grading and self.condition:
            raise ValueError("graded items must not have a raw condition")
        if not self.grading and not self.condition:
            raise ValueError("raw items require a condition")
        if self.grading and self.grading.cert_number and self.quantity != 1:
            raise ValueError("a slab with a cert number has quantity 1")
        return self


class CollectionPatch(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    acquired: AcquiredPatch | None = None
    notes: str | None = None
    tags: list[str] | None = None


Platform = Literal["vinted", "cardmarket", "ebay", "marktplaats", "other"]
SaleStatus = Literal["none", "ready", "listed", "reserved", "withdrawn"]


class RemoveIn(BaseModel):
    """Take copies out of a stack. Sold may carry the sale price per copy (cents), the platform and the
    fees / shipping paid for the whole sale (cents); gifted / removed need none."""
    quantity: int = Field(default=1, ge=1)
    reason: Literal["sold", "gifted", "removed"] = "removed"
    price: int | None = Field(default=None, ge=0, description="cents per copy, sold only")
    currency: str = "EUR"
    date: dt.date | None = None
    note: str | None = Field(default=None, max_length=300)
    platform: Platform | None = None
    fees: int | None = Field(default=None, ge=0, description="cents, whole sale, sold only")
    shipping_paid: int | None = Field(default=None, ge=0, description="cents, whole sale, sold only")


class Listing(BaseModel):
    platform: Platform
    asking_price: int = Field(ge=0, description="cents per copy")
    currency: str = "EUR"
    listed_at: dt.date | None = None
    url: str | None = Field(default=None, max_length=300, pattern=r"^https?://")  # rendered as a link: no javascript:
    notes: str | None = Field(default=None, max_length=300)
    shipping: int | None = Field(default=None, ge=0, description="cents assumed")
    needs_platform_update: bool = Field(default=False, description="price changed in the app (reprice), not yet on the platform")


class RepriceConfirmIn(BaseModel):
    """The user's confirmation of a new asking price for one listing (app only, nothing is pushed to the platform)."""
    item_id: str = Field(max_length=40)
    platform: Platform
    asking_price: int = Field(ge=1, description="cents per copy")


class StackSaleIn(BaseModel):
    """Sale state of a whole stack. `listed` needs at least one listing; `none` clears the listings."""
    status: SaleStatus
    listings: list[Listing] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _check(self):
        if self.status == "listed" and not self.listings:
            raise ValueError("listed needs at least one listing")
        if self.status == "none":
            self.listings = []
        return self


class BulkSaleIn(BaseModel):
    """Same non-listed status for many stacks (listings need a price per stack: use the stack form)."""
    ids: list[str] = Field(min_length=1, max_length=500)
    status: Literal["none", "ready", "reserved", "withdrawn"]


class ListingPackIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
    platform: Literal["vinted", "cardmarket"] = "vinted"
    strategy: Literal["market", "under", "floor"] = "market"
    pct: int = Field(default=5, ge=0, le=90, description="percent under market, strategy 'under' only")


VINTED_CONDITIONS = ("New with tags", "New without tags", "Very good", "Good", "Satisfactory")


class PublishItemIn(BaseModel):
    """One user-confirmed Vinted item (roadmap 6e). The confirmation in the app is the approval to publish it."""
    item_id: str = Field(max_length=40)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    price: int = Field(gt=0, description="cents per copy")
    currency: str = "EUR"
    condition: Literal["New with tags", "New without tags", "Very good", "Good", "Satisfactory"]
    parcel: Literal["small", "medium", "large"]


class PublishConfirmIn(BaseModel):
    items: list[PublishItemIn] = Field(min_length=1, max_length=50)


class PublishResultIn(BaseModel):
    """Reported by the Claude session after working one queue item."""
    state: Literal["published", "failed"]
    url: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    error: str | None = Field(default=None, max_length=500)


class PresetIn(BaseModel):
    """Saved filter set for a list page. `query` = the page's URL params (strings), checked against a whitelist."""
    name: str = Field(min_length=1, max_length=60)
    scope: Literal["collection", "wishlist"] = "collection"
    query: dict[str, str] = Field(default_factory=dict, max_length=30)


class SaleIn(BaseModel):
    variant: str | None = None
    grade_key: str = "raw"
    source: str = "manual"
    price: int = Field(ge=0, description="cents")
    currency: str = "EUR"
    sold_at: dt.date
    url: str | None = Field(default=None, pattern=r"^https?://")  # rendered as a link: no javascript:
    title: str | None = None


class MatchIn(BaseModel):
    url: str


class CardFetchIn(BaseModel):
    sources: list[str] | None = None
    force: bool = False

    @model_validator(mode="after")
    def _sources(self):
        bad = set(self.sources or []) - set(SCRAPED)
        if bad:
            raise ValueError(f"not scraped sources: {sorted(bad)}")
        return self


class FetchIn(CardFetchIn):
    cards: list[str] | None = None
    sets: list[str] | None = None
    owned: bool = False
    missing: bool = False  # owned cards with a graded stack that has no graded price
    wishlist: bool = False
    # Bulk collection refresh: selects + orders owned cards (see price_fetch.resolve_bulk).
    mode: Literal["all", "never", "stale", "valuable", "stack"] | None = None
    stale_days: int = Field(7, ge=1, le=365)
    scope: Literal["collection", "wishlist", "both"] = "collection"  # which cards a bulk `mode` covers
    stack_id: str | None = None

    @model_validator(mode="after")
    def _target(self):
        if not (self.cards or self.sets or self.owned or self.missing or self.wishlist or self.mode):
            raise ValueError("give cards, sets, owned, missing, wishlist or mode")
        if self.mode == "stack" and not self.stack_id:
            raise ValueError("mode 'stack' needs stack_id")
        return self


class FetchControlIn(BaseModel):
    action: Literal["pause", "resume", "cancel"]


class WishIn(BaseModel):
    card_id: str
    variant: str | None = None
    grading: Grading | None = None      # None = raw; no cert (it is a want, not a slab)
    target_price: int | None = Field(default=None, gt=0, description="cents, base currency")
    note: str | None = None
    alert: bool = True                  # keep a "below target" alert rule while target_price is set

    @model_validator(mode="after")
    def _check(self):
        if self.grading:
            self.grading = self.grading.model_copy(update={"cert_number": None})
        return self


class WishPatch(BaseModel):
    target_price: int | None = Field(default=None, gt=0)
    note: str | None = None
    alert: bool | None = None


AlertScope = Literal["stack", "card", "total", "wish"]
AlertOp = Literal["above", "below", "up_pct", "down_pct"]
AlertKind = Literal["any", "sold", "market"]


class AlertIn(BaseModel):
    scope: AlertScope
    item_id: str | None = None          # stack scope
    card_id: str | None = None          # card scope
    wish_id: str | None = None          # wish scope (a wishlist entry)
    op: AlertOp
    threshold: float = Field(gt=0, description="cents for above/below, percent for up_pct/down_pct")
    days: int | None = Field(default=None, ge=1, le=365)    # pct ops only
    kind: AlertKind = "any"
    include_estimated: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.scope == "stack" and not self.item_id:
            raise ValueError("stack alerts need item_id")
        if self.scope == "card" and not self.card_id:
            raise ValueError("card alerts need card_id")
        if self.scope == "wish" and not self.wish_id:
            raise ValueError("wish alerts need wish_id")
        if self.scope != "wish":
            self.wish_id = None
        if self.scope != "stack":
            self.item_id = None
        if self.scope != "card":
            self.card_id = None
        if self.op in ("above", "below"):
            if self.threshold != int(self.threshold):
                raise ValueError("price thresholds are whole cents")
            self.threshold, self.days = int(self.threshold), None
        else:
            if self.days is None:
                raise ValueError("percent alerts need days")
            if self.threshold > 1000:
                raise ValueError("percent threshold too large")
        return self


class AlertPatch(BaseModel):
    enabled: bool | None = None
    include_estimated: bool | None = None
    threshold: float | None = Field(default=None, gt=0)
    kind: AlertKind | None = None


class ScanSessionIn(BaseModel):
    mode: Literal["raw", "slab"] = "raw"


SealedType = Literal["booster_box", "booster_bundle", "etb", "booster_pack", "tin", "collection_box", "blister", "other"]


class SealedIn(BaseModel):
    """Own a sealed product: the catalog entry (set + type + language + edition) is created once, then a normal stack."""
    set_id: str = Field(min_length=1, max_length=40, description="external id of a set in our sets list")
    type: SealedType
    language: Language = "en"
    edition: str | None = Field(default=None, max_length=60, description="'Pokémon Center', 'Costco'...")
    quantity: int = Field(default=1, ge=1, le=10000)
    acquired: Acquired | None = None
    notes: str | None = None
