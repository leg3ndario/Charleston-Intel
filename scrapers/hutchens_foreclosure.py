"""
Hutchens Law Firm — third-party SC foreclosure sale list.
URL: https://sales.hutchenslawfirm.com/SCfcSalesList.aspx

Filterable by county. Captures pending sales the Master list may miss.
"""
import logging
import re
from datetime import datetime
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://sales.hutchenslawfirm.com/SCfcSalesList.aspx"


class HutchensForeclosureScraper(BaseScraper):
    source_id = "hutchens_foreclosure"
    description = "Hutchens Law Firm SC foreclosure sales (Charleston)"

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            page.goto(URL, wait_until="networkidle", timeout=45000)

            try:
                # Filter to Charleston County
                for sel in ['select[name*="County" i]', 'select[id*="County" i]']:
                    try:
                        page.select_option(sel, label="Charleston", timeout=2000)
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
            except Exception as e:
                log.warning(f"Hutchens filter setup failed: {e}")

            rows = page.locator("table tr").all()
            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]
                if not headers and any(h in " ".join(cell_texts).lower() for h in ["case", "address", "sale"]):
                    headers = [c.lower() for c in cell_texts]
                    continue
                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                case_num = ""
                address = ""
                sale_date = ""
                county = ""
                for k, v in row_dict.items():
                    kl = k.lower()
                    if "case" in kl and not case_num:
                        case_num = v
                    elif "address" in kl and not address:
                        address = v
                    elif "sale" in kl and "date" in kl and not sale_date:
                        sale_date = v
                    elif "county" in kl and not county:
                        county = v

                if county and "charleston" not in county.lower():
                    continue

                filing_date = None
                if sale_date:
                    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                        try:
                            filing_date = datetime.strptime(sale_date.split()[0], fmt).date()
                            break
                        except (ValueError, IndexError):
                            continue

                if not (case_num and address):
                    continue

                yield {
                    "source_record_id": f"hutchens:{case_num}",
                    "lead_type": "FCL",
                    "address": address,
                    "case_number": case_num,
                    "filing_date": filing_date,
                    "extra_flags": ["foreclosure"],
                    "notes": "Hutchens Law Firm pending sale",
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(HutchensForeclosureScraper().run())
