"""
Magistrate Summary Court Dockets — eviction filings.
URL: https://jcmsweb.charlestoncounty.gov/summarycourtdockets/

Each rule-to-vacate = landlord-distress lead. Owners with multiple eviction
filings indicate frustrated landlord = high-priority motivated seller.
"""
import logging
import re
from datetime import date, timedelta
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://jcmsweb.charlestoncounty.gov/summarycourtdockets/"


class MagistrateEvictionScraper(BaseScraper):
    source_id = "magistrate_evictions"
    description = "Magistrate court evictions / landlord-tenant filings"

    def __init__(self, days_back: int = 7):
        self.days_back = days_back

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            page.goto(URL, wait_until="networkidle", timeout=45000)

            from_date = (date.today() - timedelta(days=self.days_back)).strftime("%m/%d/%Y")

            try:
                for sel in ['select[name*="type" i]', 'select[id*="type" i]']:
                    try:
                        page.select_option(sel, label="Landlord/Tenant", timeout=2000)
                        break
                    except Exception:
                        continue

                for sel in ['input[name*="from" i]', 'input[id*="from" i]']:
                    try:
                        page.fill(sel, from_date, timeout=2000)
                        break
                    except Exception:
                        continue

                for sel in ['button:has-text("Search")', 'input[type="submit"]']:
                    try:
                        page.click(sel, timeout=2000)
                        break
                    except Exception:
                        continue

                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                log.warning(f"Eviction filter setup failed: {e}")

            rows = page.locator("table tr").all()
            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]
                if not headers and any(h in " ".join(cell_texts).lower() for h in ["case", "plaintiff", "defendant"]):
                    headers = [c.lower() for c in cell_texts]
                    continue
                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                case_num = ""
                plaintiff = ""  # the LANDLORD — our actual lead target
                defendant = ""  # the tenant
                address = ""
                for k, v in row_dict.items():
                    kl = k.lower()
                    if "case" in kl and re.search(r"\d", v) and not case_num:
                        case_num = v
                    elif "plaintiff" in kl and not plaintiff:
                        plaintiff = v
                    elif "defendant" in kl and not defendant:
                        defendant = v
                    elif "address" in kl and not address:
                        address = v

                if not (case_num and plaintiff):
                    continue

                # The LANDLORD is the lead, not the tenant
                yield {
                    "source_record_id": f"mag:{case_num}",
                    "lead_type": "EVCT",
                    "owner": plaintiff,
                    "address": address or None,
                    "case_number": case_num,
                    "extra_flags": ["eviction"],
                    "notes": f"Magistrate eviction — landlord {plaintiff} vs. tenant {defendant}",
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(MagistrateEvictionScraper().run())
