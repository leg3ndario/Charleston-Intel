"""
SC Department of Revenue — Top Delinquent Taxpayers list.
Quarterly statewide. We filter for Charleston County addresses.
"""
import logging
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from normalizers.address import normalize_address

log = logging.getLogger(__name__)

URL = "https://dor.sc.gov/transparency/compliance-searches-license-validation/south-carolinas-top-delinquent-taxpayers"

CHARLESTON_CITIES = {
    "charleston", "north charleston", "mount pleasant", "mt pleasant",
    "isle of palms", "folly beach", "james island", "johns island",
    "sullivans island", "kiawah island", "seabrook island", "edisto island",
    "hollywood", "ravenel", "meggett", "rockville", "lincolnville",
    "mcclellanville", "awendaw",
}


class SCDORDelinquentScraper(BaseScraper):
    source_id = "sc_dor_delinquent"
    description = "SC DOR Top Delinquent Taxpayers (Charleston County only)"

    def fetch(self) -> Iterable[dict]:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 lead-research-bot"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        tables = soup.find_all("table")
        if not tables:
            log.warning("No tables found on SC DOR delinquent page")
            return

        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]

            for tr in rows[1:]:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
                if len(cells) < 2:
                    continue
                row_dict = dict(zip(headers, cells)) if headers else {f"col{i}": v for i, v in enumerate(cells)}

                # Filter for Charleston County
                blob = " ".join(cells).lower()
                if not any(city in blob for city in CHARLESTON_CITIES):
                    continue

                def find(*names):
                    for k, v in row_dict.items():
                        if any(n in k for n in names) and v:
                            return v
                    return ""

                name = find("name", "taxpayer")
                address = find("address", "city")
                amount_raw = find("amount", "balance", "owed", "liability")

                try:
                    amount = float(str(amount_raw).replace("$", "").replace(",", "")) if amount_raw else None
                except (ValueError, TypeError):
                    amount = None

                if not name:
                    continue

                yield {
                    "source_record_id": f"scdor:{normalize_address(address) or name.lower()}",
                    "lead_type": "LIEN",
                    "owner": name,
                    "address": address or None,
                    "amount": amount,
                    "extra_flags": ["state_tax_lien"],
                    "notes": "SC DOR top delinquent taxpayer list",
                    "raw_data": row_dict,
                }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(SCDORDelinquentScraper().run())
