"""
Charleston Probate Search via 3rd-party portal.
URL: https://www.southcarolinaprobate.net/charlestonprobatesearch/

Recent estates with real property = warm leads (heirs often want liquidity).
"""
import logging
import re
from datetime import date, timedelta
from typing import Iterable

from scrapers.base import BaseScraper
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

URL = "https://www.southcarolinaprobate.net/charlestonprobatesearch/"


class ProbateScraper(BaseScraper):
    source_id = "probate_search"
    description = "Charleston probate filings (recent estates)"

    def __init__(self, days_back: int = 14):
        self.days_back = days_back

    def fetch(self) -> Iterable[dict]:
        with browser_context() as page:
            page.goto(URL, wait_until="networkidle", timeout=45000)

            from_date = (date.today() - timedelta(days=self.days_back)).strftime("%m/%d/%Y")
            to_date = date.today().strftime("%m/%d/%Y")

            try:
                for sel in ['input[name*="filed" i][name*="from" i]', 'input[name*="from" i]', 'input[id*="from" i]']:
                    try:
                        page.fill(sel, from_date, timeout=2000)
                        break
                    except Exception:
                        continue
                for sel in ['input[name*="filed" i][name*="to" i]', 'input[name*="to" i]', 'input[id*="to" i]']:
                    try:
                        page.fill(sel, to_date, timeout=2000)
                        break
                    except Exception:
                        continue
                for sel in ['button:has-text("Search")', 'input[type="submit"]', 'input[value*="Search"]']:
                    try:
                        page.click(sel, timeout=2000)
                        break
                    except Exception:
                        continue
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                log.warning(f"Probate filter setup failed: {e}")

            rows = page.locator("table tr").all()
            headers = []
            for row in rows:
                cells = row.locator("th, td").all()
                cell_texts = [(c.text_content() or "").strip() for c in cells]
                if not headers and any(h in " ".join(cell_texts).lower() for h in ["case", "decedent", "filed"]):
                    headers = [c.lower() for c in cell_texts]
                    continue
                if len(cell_texts) < 3:
                    continue

                row_dict = dict(zip(headers, cell_texts)) if headers else {f"col{i}": v for i, v in enumerate(cell_texts)}

                case_num = ""
                decedent = ""
                pr_name = ""
                filing = ""
                status = ""
                for k, v in row_dict.items():
                    kl = k.lower()
                    if "case" in kl and re.search(r"\d", v) and not case_num:
                        case_num = v
                    elif ("decedent" in kl or "name" in kl or "party" in kl) and not decedent:
                        decedent = v
                    elif ("personal" in kl or "rep" in kl or "pr" in kl) and not pr_name:
                        pr_name = v
                    elif "fil" in kl and not filing:
                        filing = v
                    elif "status" in kl and not status:
                        status = v

                if not (case_num and decedent):
                    continue

                yield {
                    "source_record_id": f"probate:{case_num}",
                    "lead_type": "PROB",
                    "owner": decedent,
                    "case_number": case_num,
                    "extra_flags": ["probate"],
                    "notes": f"Probate estate — PR: {pr_name}; Status: {status}",
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(ProbateScraper().run())
