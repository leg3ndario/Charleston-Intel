"""
Clerk of Court Daybook — daily new civil filings.
URL: https://cocdaybook.charlestoncounty.gov/

Highest-value filter: Lis Pendens (each = a pre-foreclosure lead).
"""
import logging
import re
from datetime import date, timedelta
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://cocdaybook.charlestoncounty.gov/"


class ClerkDaybookScraper(BaseScraper):
    source_id = "clerk_daybook"
    description = "Clerk of Court Daybook — daily filings (lis pendens, judgments)"

    def __init__(self, days_back: int = 1):
        self.days_back = days_back

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            page.goto(URL, wait_until="networkidle", timeout=45000)
            target_date = date.today() - timedelta(days=self.days_back)
            date_str = target_date.strftime("%m/%d/%Y")

            # Try to find a "Search by Type" or filter for Lis Pendens
            try:
                # Look for type dropdown
                for sel in ['select[name*="type" i]', 'select[id*="type" i]']:
                    try:
                        page.select_option(sel, label="Lis Pendens", timeout=2000)
                        break
                    except Exception:
                        continue

                # Date inputs
                for sel in ['input[name*="from" i]', 'input[id*="from" i]']:
                    try:
                        page.fill(sel, date_str, timeout=2000)
                        break
                    except Exception:
                        continue

                # Submit
                for sel in ['button:has-text("Search")', 'input[value*="Search" i]', 'button[type="submit"]']:
                    try:
                        page.click(sel, timeout=2000)
                        break
                    except Exception:
                        continue

                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                log.warning(f"Filter setup failed: {e}")

            rows = page.locator("table tr").all()
            log.info(f"Found {len(rows)} rows in clerk daybook")

            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]

                if not headers and any(k in " ".join(cell_texts).lower() for k in ["case", "plaintiff", "defendant", "type"]):
                    headers = [c.lower() for c in cell_texts]
                    continue

                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                case_num = ""
                plaintiff = ""
                defendant = ""
                case_type = ""
                for k, v in row_dict.items():
                    kl = k.lower()
                    if "case" in kl and re.search(r"\d", v) and not case_num:
                        case_num = v
                    elif "plaintiff" in kl and not plaintiff:
                        plaintiff = v
                    elif "defendant" in kl and not defendant:
                        defendant = v
                    elif "type" in kl and not case_type:
                        case_type = v

                # Filter to lis pendens / foreclosure / judgments
                ct = case_type.upper()
                if any(t in ct for t in ["LIS PENDENS", "FORECLOSURE"]):
                    lead_type = "LP"
                    flags = ["lis_pendens"]
                elif "JUDGMENT" in ct:
                    lead_type = "LIEN"
                    flags = []
                elif "MECHANIC" in ct:
                    lead_type = "LIEN"
                    flags = ["mechanic_lien"]
                elif "TAX LIEN" in ct:
                    lead_type = "LIEN"
                    flags = ["state_tax_lien"]
                else:
                    continue  # skip non-distress filings

                if not (defendant or case_num):
                    continue

                yield {
                    "source_record_id": f"coc:{case_num}",
                    "lead_type": lead_type,
                    "owner": defendant or None,
                    "case_number": case_num or None,
                    "plaintiff": plaintiff or None,
                    "extra_flags": flags,
                    "filing_date": target_date,
                    "notes": f"Clerk Daybook — {case_type}",
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(ClerkDaybookScraper().run())
