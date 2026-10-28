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
    cert_number: str | None = None


class Acquired(BaseModel):
    price: int | None = Field(default=None, ge=0, description="cents")
    currency: str = "EUR"
    date: dt.date | None = None
    source: str | None = None


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
    acquired: Acquired | None = None
    notes: str | None = None
    tags: list[str] | None = None


class RemoveIn(BaseModel):
    quantity: int = Field(default=1, ge=1)


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

    @model_validator(mode="after")
    def _target(self):
        if not (self.cards or self.sets or self.owned):
            raise ValueError("give cards, sets or owned")
        return self


AlertScope = Literal["stack", "card", "total"]
AlertOp = Literal["above", "below", "up_pct", "down_pct"]
AlertKind = Literal["any", "sold", "market"]


class AlertIn(BaseModel):
    scope: AlertScope
    item_id: str | None = None          # stack scope
    card_id: str | None = None          # card scope
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
