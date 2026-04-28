"""
Master-in-Equity foreclosure auction list. Static HTML page — easy parse.
URL: https://www.charlestoncounty.org/foreclosure/runninglist.html
"""
import logging
import re
from datetime import datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

log = logging.getLogger(__name__)

URL = "https://www.charlestoncounty.org/foreclosure/runninglist.html"


class MasterAuctionScraper(BaseScraper):
    source_id = "master_auction_list"
    description = "Charleston County Master-in-Equity foreclosure auctions"

    def fetch(self) -> Iterable[dict]:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 lead-research-bot"})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "html.parser")

        # The page layout uses a single big table — find the largest one
        tables = soup.find_all("table")
        if not tables:
            log.warning("No tables found on auction page")
            return

        # Pick the table with the most rows
        best = max(tables, key=lambda t: len(t.find_all("tr")))
        rows = best.find_all("tr")
        if len(rows) < 2:
            return

        # Extract header
        header_cells = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        log.info(f"Auction headers: {header_cells}")

        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) < 3:
                continue

            row_dict = dict(zip(header_cells, cells)) if header_cells else {f"col{i}": v for i, v in enumerate(cells)}

            def find_field(*needles):
                for k, v in row_dict.items():
                    if any(n in k for n in needles) and v:
                        return v
                return ""

            sale_date_str = find_field("date", "sale")
            plaintiff = find_field("plaintiff")
            defendant = find_field("defendant", "owner")
            tms = find_field("tms", "pin")
            address = find_field("address", "property")
            case_num = find_field("case", "number")

            # Some rows have status (cancelled/postponed) — capture that
            status_text = " ".join(cells).lower()
            extra_flags = []
            notes = "Master auction list"
            if "cancel" in status_text or "withdraw" in status_text:
                extra_flags.append("absentee")  # often signals settlement / motivated seller
                notes = "Foreclosure cancelled/withdrawn — likely motivated seller"

            filing_date = None
            if sale_date_str:
                # Try a few date formats
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                    try:
                        filing_date = datetime.strptime(sale_date_str.split()[0], fmt).date()
                        break
                    except ValueError:
                        continue

            if not (defendant or address):
                continue

            yield {
                "source_record_id": case_num or f"auction:{tms}|{defendant}|{sale_date_str}",
                "lead_type": "FCL",
                "owner": defendant or None,
                "address": address or None,
                "tms": tms or None,
                "case_number": case_num or None,
                "filing_date": filing_date,
                "plaintiff": plaintiff or None,
                "extra_flags": extra_flags,
                "notes": notes,
                "raw_data": row_dict,
            }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(MasterAuctionScraper().run())
