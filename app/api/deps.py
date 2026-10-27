from app.db.mongo import get_db  # noqa: F401  (re-export: routers import db accessor from here)


def clean(d: dict | None) -> dict | None:
    if d is None:
        return None
    d = {k: v for k, v in d.items() if k not in ("search_text", "name_norm", "number_sort")}
    d["id"] = d.pop("_id")
    return d
