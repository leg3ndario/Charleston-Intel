"""Sealed Bid Sale XLSX — same shape as RP Tax Sale."""
import io
import logging
from typing import Iterable

import requests
import openpyxl

from scrapers.base import BaseScraper

log = logging.getLogger(__name__)

URL = "https://www.charlestoncounty.org/departments/delinquent-tax/files/2024-SEALED-BID-SALE-LIST-Tax-Sale.xlsx"


class SealedBidSaleScraper(BaseScraper):
    source_id = "sealed_bid_sale_xlsx"
    description = "Charleston County Sealed Bid Tax Sale Listing"

    def fetch(self) -> Iterable[dict]:
        resp = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 lead-research-bot"})
        resp.raise_for_status()

        wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        header_idx = 0
        for i, row in enumerate(rows[:10]):
            if sum(1 for c in row if c not in (None, "")) >= 3:
                header_idx = i
                break

        headers = [str(h).strip().lower() if h else f"col{i}" for i, h in enumerate(rows[header_idx])]

        def col(row_dict, *names):
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
            owner = col(row_dict, "owner", "name")
            address = col(row_dict, "address", "property", "situs")
            amount_raw = col(row_dict, "bid", "amount", "due")

            if not (tms or owner or address):
                continue

            try:
                amount = float(str(amount_raw).replace("$", "").replace(",", "")) if amount_raw else None
            except (ValueError, TypeError):
                amount = None

            yield {
                "source_record_id": f"sealed:{tms}" if tms else f"sealed:{owner}|{address}",
                "lead_type": "TAX",
                "owner": owner or None,
                "address": address or None,
                "tms": tms or None,
                "amount": amount,
                "notes": "Sealed bid tax sale listing",
                "raw_data": row_dict,
            }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(SealedBidSaleScraper().run())
