"""Filing registry: which reports we know about, and downloading them once."""

from dataclasses import dataclass
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "filings" / "registry.yaml"
PDF_DIR = ROOT / "filings" / "pdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (bursa-filing-agent; portfolio project)"}


@dataclass
class Filing:
    id: str
    company: str
    period_end: str
    url: str

    @property
    def path(self) -> Path:
        return PDF_DIR / f"{self.id}.pdf"


def load_registry(path: Path = REGISTRY) -> dict[str, Filing]:
    """All filings in the registry, keyed by id."""
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {r["id"]: Filing(r["id"], r["company"], str(r["period_end"]), r["url"]) for r in rows}


def download(filing: Filing, force: bool = False) -> Path:
    """Download the PDF unless we already have it. Refuses anything that is not a PDF."""
    if filing.path.exists() and not force:
        return filing.path
    resp = requests.get(filing.url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise ValueError(f"{filing.id}: {filing.url} did not return a PDF")
    filing.path.parent.mkdir(parents=True, exist_ok=True)
    filing.path.write_bytes(resp.content)
    return filing.path


if __name__ == "__main__":
    for f in load_registry().values():
        print(f"{f.id}: {download(f).stat().st_size:,} bytes")
