"""
Pending Cases Search — JCMS portal.
URL: https://jcmsweb.charlestoncounty.org/courtrosters/PendingCases.aspx

We pull recent filings in distress-relevant subtypes:
  Foreclosure 420
  Mechanic's Lien 430
  State Tax Lien 432
  Federal Tax Lien 431
  Lis Pendens
  Partition
"""
import logging
import re
from datetime import date, timedelta
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://jcmsweb.charlestoncounty.org/courtrosters/PendingCases.aspx"

DISTRESS_SUBTYPES = {
    "Foreclosure": ("FCL", ["foreclosure"]),
    "Mechanic's Lien": ("LIEN", ["mechanic_lien"]),
    "State Tax Lien": ("LIEN", ["state_tax_lien"]),
    "Federal Tax Lien": ("LIEN", ["fed_tax_lien"]),
    "Lis Pendens": ("LP", ["lis_pendens"]),
    "Partition": ("OTH", []),
    "Judgment": ("LIEN", []),
}


class PendingCasesScraper(BaseScraper):
    source_id = "pending_cases"
    description = "JCMS Pending Cases — distress filings"

    def __init__(self, days_back: int = 7):
        self.days_back = days_back

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            for subtype, (lead_type, flags) in DISTRESS_SUBTYPES.items():
                log.info(f"Querying pending cases: {subtype}")
                yield from self._query_subtype(page, subtype, lead_type, flags)

    def _query_subtype(self, page, subtype, lead_type, flags) -> Iterable[dict]:
        try:
            page.goto(URL, wait_until="networkidle", timeout=45000)

            # Set filing-date range
            from_date = (date.today() - timedelta(days=self.days_back)).strftime("%m/%d/%Y")
            to_date = date.today().strftime("%m/%d/%Y")

            for sel in ['input[name*="From" i]', 'input[id*="From" i]']:
                try:
                    page.fill(sel, from_date, timeout=1500)
                    break
                except Exception:
                    continue
            for sel in ['input[name*="To" i]', 'input[id*="To" i]']:
                try:
                    page.fill(sel, to_date, timeout=1500)
                    break
                except Exception:
                    continue

            # Set case type / subtype dropdowns
            for sel in ['select[name*="SubType" i]', 'select[id*="SubType" i]', 'select[name*="Type" i]']:
                try:
                    page.select_option(sel, label=subtype, timeout=2000)
                    break
                except Exception:
                    continue

            for sel in ['input[type="submit"][value*="Search"]', 'button:has-text("Search")']:
                try:
                    page.click(sel, timeout=2000)
                    break
                except Exception:
                    continue

            page.wait_for_load_state("networkidle", timeout=30000)

            rows = page.locator("table tr").all()
            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]
                if not headers and any(h in " ".join(cell_texts).lower() for h in ["case", "filed", "party"]):
                    headers = [c.lower() for c in cell_texts]
                    continue
                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                case_num = ""
                party = ""
                filing = ""
                for k, v in row_dict.items():
                    kl = k.lower()
                    if "case" in kl and re.search(r"\d", v) and not case_num:
                        case_num = v
                    elif ("party" in kl or "defendant" in kl or "name" in kl) and not party:
                        party = v
                    elif "fil" in kl and not filing:
                        filing = v

                if not case_num:
                    continue

                yield {
                    "source_record_id": f"jcms:{case_num}",
                    "lead_type": lead_type,
                    "owner": party or None,
                    "case_number": case_num,
                    "extra_flags": flags,
                    "notes": f"Pending Cases — {subtype}",
                    "raw_data": row_dict,
                }
        except Exception as e:
            log.error(f"Subtype {subtype} failed: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(PendingCasesScraper().run())
