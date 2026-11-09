"""Graders with no machine-readable page (CGC, SGC): only a link (or none). Counted via status link_only."""
from app.providers.grading.base import LINK_ONLY, CertInfo, clean_cert, now


class LinkOnlyProvider:
    def __init__(self, grader: str, template: str | None, note: str):
        self.grader, self.template, self.note = grader, template, note

    async def lookup(self, cert: str) -> CertInfo:
        cert = clean_cert(cert) or ""
        url = self.template.format(cert=cert) if self.template and cert else None
        return CertInfo(self.grader, cert, LINK_ONLY, url, detail=self.note, fetched_at=now())
