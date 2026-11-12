"""Save the statement pages' text for each filing into eval/fixtures/, so CI can run offline.

Several company sites refuse downloads from cloud IP ranges (GitHub Actions), so CI cannot fetch
the PDFs. Re-run this locally after adding a filing:  python eval/snapshot.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bursa_agent import extract  # noqa: E402
from bursa_agent.filings import download, load_registry  # noqa: E402

FIXTURES = ROOT / "eval" / "fixtures"


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    for filing in load_registry().values():
        download(filing)
        try:
            data = {"scanned": False, "pages": extract.statement_pages(filing.path)}
        except extract.ScannedPDF:
            data = {"scanned": True, "pages": []}
        (FIXTURES / f"{filing.id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
        print(filing.id, "scanned" if data["scanned"] else [n for n, _ in data["pages"]])


if __name__ == "__main__":
    main()
