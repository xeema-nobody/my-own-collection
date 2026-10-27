import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    variant: str = "normal"
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
    variant: str = "normal"
    grade_key: str = "raw"
    source: str = "manual"
    price: int = Field(ge=0, description="cents")
    currency: str = "EUR"
    sold_at: dt.date
    url: str | None = None
    title: str | None = None
