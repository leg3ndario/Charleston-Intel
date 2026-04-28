"""
Mobile Home Tax Sale Listing — PDF parser via pdfplumber.

Source: https://www.charlestoncounty.org/departments/delinquent-tax/files/MH-Tax-Sale-Listing.pdf

PDF format observed: tabular with columns roughly:
  TMS / Decal# | Owner | Park / Location | Year(s) Delinquent | Amount Due

We try table extraction first, then fall back to line-regex parsing if the table
is non-grid (some weeks the PDF is generated as a free-flow report).
"""
import io
import logging
import re
from datetime import date
from typing import Iterable

import pdfplumber
import requests

from scrapers.base import BaseScraper

log = logging.getLogger(__name__)

URL = "https://www.charlestoncounty.org/departments/delinquent-tax/files/MH-Tax-Sale-Listing.pdf"

# Fallback regex for free-flow rows: TMS-like start, then text, then dollar amount
ROW_RE = re.compile(
    r"^\s*([\d-]{6,})\s+(.+?)\s+\$?([\d,]+\.\d{2})\s*$"
)


class MobileHomeTaxParser(BaseScraper):
    source_id = "mobile_home_tax_pdf"
    description = "Mobile Home Tax Sale PDF parser"

    def fetch(self) -> Iterable[dict]:
        log.info(f"Downloading {URL}")
        resp = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 lead-research-bot"})
        resp.raise_for_status()

        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            log.info(f"PDF has {len(pdf.pages)} pages")

            for page_num, page in enumerate(pdf.pages, 1):
                # Try structured table extraction first
                tables = page.extract_tables() or []

                yielded_from_tables = 0
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # Detect header
                    header = [str(c or "").strip().lower() for c in table[0]]
                    has_header = any(k in " ".join(header) for k in ["tms", "owner", "amount", "name", "decal"])

                    rows = table[1:] if has_header else table

                    for row in rows:
                        if not row or all(c in (None, "") for c in row):
                            continue

                        cells = [str(c or "").strip() for c in row]
                        row_dict = dict(zip(header, cells)) if has_header else {f"col{i}": v for i, v in enumerate(cells)}

                        tms = ""
                        owner = ""
                        location = ""
                        amount_str = ""

                        if has_header:
                            for k, v in row_dict.items():
                                if any(x in k for x in ["tms", "decal", "pin"]) and v:
                                    tms = tms or v
                                elif any(x in k for x in ["owner", "name"]) and v:
                                    owner = owner or v
                                elif any(x in k for x in ["park", "location", "address", "situs"]) and v:
                                    location = location or v
                                elif any(x in k for x in ["amount", "due", "total"]) and v:
                                    amount_str = amount_str or v
                        else:
                            # Heuristic: first numeric-looking col = TMS, last $-shaped = amount, name in middle
                            tms = cells[0] if cells else ""
                            owner = cells[1] if len(cells) > 1 else ""
                            location = cells[2] if len(cells) > 2 else ""
                            amount_str = next((c for c in reversed(cells) if "$" in c or re.search(r"\d+\.\d{2}", c)), "")

                        if not (tms or owner):
                            continue

                        try:
                            amount = float(re.sub(r"[^\d.]", "", amount_str)) if amount_str else None
                        except ValueError:
                            amount = None

                        yielded_from_tables += 1
                        yield {
                            "source_record_id": f"mh:{tms or owner}",
                            "lead_type": "TAX",
                            "owner": owner or None,
                            "address": location or None,
                            "tms": tms or None,
                            "amount": amount,
                            "extra_flags": ["tax"],
                            "notes": f"Mobile home tax sale (page {page_num})",
                            "raw_data": row_dict,
                        }

                # If table extraction failed for this page, fall back to line regex
                if yielded_from_tables == 0:
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        m = ROW_RE.match(line)
                        if not m:
                            continue
                        tms, middle, amount_str = m.groups()
                        # Owner is the first chunk before any obvious park name marker
                        try:
                            amount = float(amount_str.replace(",", ""))
                        except ValueError:
                            amount = None
                        yield {
                            "source_record_id": f"mh:{tms}",
                            "lead_type": "TAX",
                            "owner": middle.strip(),
                            "tms": tms,
                            "amount": amount,
                            "extra_flags": ["tax"],
                            "notes": f"Mobile home tax sale (line regex fallback, page {page_num})",
                            "raw_data": {"line": line},
                        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(MobileHomeTaxParser().run())
