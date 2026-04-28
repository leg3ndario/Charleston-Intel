"""
ROD Day Book scraper. Pulls yesterday's recordings.
URL: https://roddaybook.charlestoncounty.org/

We look for high-signal document types:
  Quitclaim Deed (QC) — often signals motivated transfer
  Estate Deed / Personal Rep Deed — probate signal
  Deed Into Trust
  Tax Deed
  Lis Pendens
"""
import logging
import re
from datetime import date, timedelta
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://roddaybook.charlestoncounty.org/"

HIGH_SIGNAL_DOC_TYPES = {
    "QUITCLAIM": ("OTH", ["absentee"]),  # weak signal but worth tracking
    "QUIT CLAIM DEED": ("OTH", []),
    "PERSONAL REPRESENTATIVE DEED": ("PROB", ["probate"]),
    "PR DEED": ("PROB", ["probate"]),
    "ESTATE DEED": ("PROB", ["probate"]),
    "DEED IN TRUST": ("OTH", []),
    "TAX DEED": ("TAX", ["tax"]),
    "LIS PENDENS": ("LP", ["lis_pendens"]),
    "MECHANICS LIEN": ("LIEN", ["mechanic_lien"]),
    "MECHANIC LIEN": ("LIEN", ["mechanic_lien"]),
    "FEDERAL TAX LIEN": ("LIEN", ["fed_tax_lien"]),
    "STATE TAX LIEN": ("LIEN", ["state_tax_lien"]),
}


class RODDaybookScraper(BaseScraper):
    source_id = "rod_daybook"
    description = "Charleston County ROD Day Book — daily recordings"

    def __init__(self, days_back: int = 1):
        self.days_back = days_back

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            page.goto(URL, wait_until="networkidle", timeout=45000)
            log.info("ROD Day Book loaded")

            target_date = (date.today() - timedelta(days=self.days_back))

            # The site has form fields for from-date/to-date. Selector exact names
            # vary; we attempt several common ones and bail gracefully if missing.
            try:
                # Try common date input selectors
                date_str = target_date.strftime("%m/%d/%Y")
                for sel in ['input[name*="From" i]', 'input[id*="from" i]', 'input[name="dateFrom"]']:
                    try:
                        page.fill(sel, date_str, timeout=2000)
                        break
                    except Exception:
                        continue
                for sel in ['input[name*="To" i]', 'input[id*="to" i]', 'input[name="dateTo"]']:
                    try:
                        page.fill(sel, date_str, timeout=2000)
                        break
                    except Exception:
                        continue

                # Submit
                for sel in ['button:has-text("Search")', 'input[type="submit"]', 'button[type="submit"]']:
                    try:
                        page.click(sel, timeout=2000)
                        break
                    except Exception:
                        continue

                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                log.warning(f"Could not fill date form: {e} — falling back to default page contents")

            # Pull all table rows
            rows = page.locator("table tr").all()
            log.info(f"Found {len(rows)} table rows")

            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]

                # Detect header row
                if not headers and any(h.lower() in " ".join(cell_texts).lower() for h in ["doc type", "document", "grantor", "name"]):
                    headers = [c.lower() for c in cell_texts]
                    continue

                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                doc_type = ""
                grantor = ""
                grantee = ""
                book = ""
                rec_num = ""

                for k, v in row_dict.items():
                    kl = k.lower()
                    if "doc" in kl and "type" in kl and not doc_type:
                        doc_type = v
                    elif "grantor" in kl and not grantor:
                        grantor = v
                    elif "grantee" in kl and not grantee:
                        grantee = v
                    elif ("book" in kl or "vol" in kl) and not book:
                        book = v
                    elif ("rec" in kl or "doc" in kl) and re.search(r"\d", v) and not rec_num:
                        rec_num = v

                doc_type_upper = doc_type.upper().strip()
                match = None
                for sig, payload in HIGH_SIGNAL_DOC_TYPES.items():
                    if sig in doc_type_upper:
                        match = payload
                        break
                if not match:
                    continue  # skip noise (mortgages, releases, easements, etc.)

                lead_type, flags = match
                yield {
                    "source_record_id": f"rod:{rec_num or book}:{grantor[:30]}",
                    "lead_type": lead_type,
                    "owner": grantor or grantee or None,
                    "case_number": rec_num or book or None,
                    "extra_flags": flags,
                    "notes": f"ROD Day Book — {doc_type}",
                    "filing_date": target_date,
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(RODDaybookScraper().run())
