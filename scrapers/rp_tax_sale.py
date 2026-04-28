"""
RP Tax Sale Listing scraper — direct XLSX download, no Playwright needed.

Source URL keeps trailing version-busting param — we strip it and re-fetch.
The XLSX columns in observed historical files include: TMS, Owner Name, Property
Address, Tax Amount, etc. Schema may shift; we read header row dynamically.
"""
import io
import logging
from datetime import date
from typing import Iterable

import requests
import openpyxl

from scrapers.base import BaseScraper

log = logging.getLogger(__name__)

URL = "https://www.charlestoncounty.org/departments/delinquent-tax/files/RP-Tax-Sale-Listing.xlsx"


class RealPropertyTaxSaleScraper(BaseScraper):
    source_id = "rp_tax_sale_xlsx"
    description = "Charleston County Real Property Tax Sale Listing XLSX"

    def fetch(self) -> Iterable[dict]:
        log.info(f"Downloading {URL}")
        resp = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 lead-research-bot"})
        resp.raise_for_status()

        wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
        ws = wb.active

        # Locate header row — first row with multiple non-empty cells
        rows = list(ws.iter_rows(values_only=True))
        header_idx = 0
        for i, row in enumerate(rows[:10]):
            if sum(1 for c in row if c not in (None, "")) >= 3:
                header_idx = i
                break

        headers = [str(h).strip().lower() if h else f"col{i}" for i, h in enumerate(rows[header_idx])]
        log.info(f"Detected headers: {headers}")

        def col(row_dict: dict, *names) -> str:
            for n in names:
                for k, v in row_dict.items():
                    if n in k and v not in (None, ""):
                        return str(v).strip()
            return ""

        for row in rows[header_idx + 1 :]:
            if not row or all(c in (None, "") for c in row):
                continue

            row_dict = dict(zip(headers, row))
            tms = col(row_dict, "tms", "pin", "parcel")
            owner = col(row_dict, "owner", "name", "taxpayer")
            address = col(row_dict, "address", "property", "situs", "location")
            amount_raw = col(row_dict, "amount", "due", "tax", "bid")

            if not (tms or owner or address):
                continue

            try:
                amount = float(str(amount_raw).replace("$", "").replace(",", "")) if amount_raw else None
            except (ValueError, TypeError):
                amount = None

            yield {
                "source_record_id": tms or f"{owner}|{address}",
                "lead_type": "TAX",
                "owner": owner or None,
                "address": address or None,
                "tms": tms or None,
                "amount": amount,
                "notes": "Real property tax sale listing",
                "raw_data": row_dict,
            }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(RealPropertyTaxSaleScraper().run())
