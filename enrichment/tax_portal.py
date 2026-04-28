"""
Tax-portal enrichment worker.

When a new lead is created, its property gets queued in `enrichment_queue`.
This worker drains the queue: for each property, look it up on the Real Property
Record Search portal, scrape owner + mailing address + assessed value, then
update the property record and recompute scores for any leads on it.

Portal: https://sc-charleston.publicaccessnow.com/RealPropertyRecordSearch.aspx

Strategy:
  1. Search by TMS if we have it (most reliable).
  2. Otherwise search by street address.
  3. Read the result page, extract owner / mailing / value.
  4. Update properties.is_absentee, is_out_of_state, mailing fields.
  5. Recompute lead scores for every lead on this property.
"""
import logging
import re
import time
from datetime import datetime
from typing import Optional

from db.client import get_client
from db.scoring import compute_score
from normalizers.address import is_absentee, is_out_of_state, extract_state
from normalizers.owner import normalize_owner
from scrapers.playwright_base import browser_context

log = logging.getLogger(__name__)

PORTAL_URL = "https://sc-charleston.publicaccessnow.com/RealPropertyRecordSearch.aspx"

# Field labels we look for on the result page
FIELD_PATTERNS = {
    "owner": [r"owner", r"taxpayer"],
    "mailing": [r"mailing\s*address", r"mail to", r"owner\s*address"],
    "assessed": [r"assessed\s*value", r"appraised\s*value", r"market\s*value"],
    "last_sale_date": [r"last\s*sale\s*date", r"sale\s*date"],
    "last_sale_price": [r"last\s*sale\s*price", r"sale\s*price"],
}


class TaxPortalEnricher:
    """Drains the enrichment_queue. Run on cron or on-demand."""

    def __init__(self, batch_size: int = 50, max_attempts: int = 3):
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.client = get_client()

    def run(self) -> dict:
        """Process up to batch_size pending items. Returns stats."""
        pending = self._get_pending_batch()
        if not pending:
            log.info("No pending enrichments")
            return {"processed": 0, "updated": 0, "failed": 0}

        log.info(f"Enriching {len(pending)} properties")
        processed = updated = failed = 0

        with browser_context() as page:
            page.goto(PORTAL_URL, wait_until="networkidle", timeout=45000)

            for item in pending:
                processed += 1
                try:
                    success = self._enrich_one(page, item)
                    if success:
                        updated += 1
                        self._mark_complete(item["id"])
                    else:
                        failed += 1
                        self._mark_attempt(item["id"], "No matching record found")
                except Exception as e:
                    failed += 1
                    log.error(f"Enrichment failed for property {item['property_id']}: {e}")
                    self._mark_attempt(item["id"], str(e))

                # Polite throttle — county portals throttle aggressive scrapers
                time.sleep(2)

        return {"processed": processed, "updated": updated, "failed": failed}

    def _get_pending_batch(self) -> list[dict]:
        res = (
            self.client.table("enrichment_queue")
            .select("id, property_id, lead_id, attempts")
            .is_("completed_at", "null")
            .lt("attempts", self.max_attempts)
            .order("priority")
            .order("created_at")
            .limit(self.batch_size)
            .execute()
        )
        return res.data or []

    def _enrich_one(self, page, item: dict) -> bool:
        prop_id = item["property_id"]
        if not prop_id:
            return False

        # Get the property's TMS / address
        prop_res = (
            self.client.table("properties")
            .select("id, tms, address_raw, address_norm")
            .eq("id", prop_id)
            .single()
            .execute()
        )
        if not prop_res.data:
            return False

        prop = prop_res.data
        tms = prop.get("tms")
        address = prop.get("address_raw") or prop.get("address_norm")

        # Run the search
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=30000)

        # Try TMS search first — try several common selector patterns
        searched = False
        if tms:
            for sel in ['input[name*="PIN" i]', 'input[name*="TMS" i]', 'input[id*="pin" i]', 'input[id*="tms" i]']:
                try:
                    page.fill(sel, tms, timeout=2000)
                    searched = True
                    break
                except Exception:
                    continue

        if not searched and address:
            # Strip city/zip — site usually wants street only
            street_only = re.sub(r",.*$", "", address).strip()
            for sel in ['input[name*="Address" i]', 'input[name*="Street" i]', 'input[id*="address" i]']:
                try:
                    page.fill(sel, street_only, timeout=2000)
                    searched = True
                    break
                except Exception:
                    continue

        if not searched:
            log.warning(f"No searchable identifier for property {prop_id}")
            return False

        for sel in ['input[type="submit"][value*="Search"]', 'button:has-text("Search")']:
            try:
                page.click(sel, timeout=2000)
                break
            except Exception:
                continue

        page.wait_for_load_state("networkidle", timeout=30000)

        # Click first result if a list was returned
        try:
            first_link = page.locator("table a").first
            if first_link.count() > 0:
                first_link.click(timeout=3000)
                page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass

        # Extract fields by scanning the HTML for label / value pairs
        html = page.content()
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)

        extracted = self._extract_fields(text)

        if not extracted.get("owner") and not extracted.get("mailing"):
            log.info(f"No fields extracted for property {prop_id}")
            return False

        # Update property record
        mailing = extracted.get("mailing")
        update_payload = {
            "owner_name_raw": extracted.get("owner"),
            "owner_name_norm": normalize_owner(extracted.get("owner")) if extracted.get("owner") else None,
            "mailing_address": mailing,
            "mailing_state": extract_state(mailing),
            "is_absentee": is_absentee(prop.get("address_raw"), mailing),
            "is_out_of_state": is_out_of_state(mailing),
            "assessed_value": self._parse_money(extracted.get("assessed")),
            "last_sale_price": self._parse_money(extracted.get("last_sale_price")),
            "enriched_at": datetime.utcnow().isoformat(),
        }
        # Drop None values to avoid clobbering existing data
        update_payload = {k: v for k, v in update_payload.items() if v is not None or k.startswith("is_") or k == "enriched_at"}

        self.client.table("properties").update(update_payload).eq("id", prop_id).execute()
        log.info(f"Enriched property {prop_id}: absentee={update_payload.get('is_absentee')} oos={update_payload.get('is_out_of_state')}")

        # Re-flag and re-score every lead on this property
        self._rescore_leads(prop_id, update_payload.get("is_absentee", False), update_payload.get("is_out_of_state", False))
        return True

    def _extract_fields(self, text: str) -> dict:
        out = {}
        for field, patterns in FIELD_PATTERNS.items():
            for pat in patterns:
                # Look for "Label: VALUE" or "Label VALUE" up to next clear delimiter
                m = re.search(rf"{pat}\s*[:]?\s*([^|]{{2,80}}?)(?=\s{{2,}}|\b(owner|mailing|assessed|tax|sale|tms|pin|legal|property)\b|$)", text, re.I)
                if m:
                    out[field] = m.group(1).strip()
                    break
        return out

    @staticmethod
    def _parse_money(s: Optional[str]) -> Optional[float]:
        if not s:
            return None
        try:
            return float(re.sub(r"[^\d.]", "", s))
        except ValueError:
            return None

    def _rescore_leads(self, property_id: str, absentee: bool, out_of_state: bool):
        leads = (
            self.client.table("leads")
            .select("id, flags, lead_type")
            .eq("property_id", property_id)
            .execute()
        )
        for lead in leads.data or []:
            flags = set(lead.get("flags", []))
            if absentee:
                flags.add("absentee")
            if out_of_state:
                flags.add("out_of_state")
            new_flags = sorted(flags)
            new_score = compute_score(new_flags)
            self.client.table("leads").update({
                "flags": new_flags,
                "score": new_score,
            }).eq("id", lead["id"]).execute()

    def _mark_complete(self, queue_id: str):
        self.client.table("enrichment_queue").update({
            "completed_at": datetime.utcnow().isoformat(),
        }).eq("id", queue_id).execute()

    def _mark_attempt(self, queue_id: str, error: str):
        # Increment attempts; this is read on the next cycle's filter
        existing = (
            self.client.table("enrichment_queue")
            .select("attempts")
            .eq("id", queue_id)
            .single()
            .execute()
        )
        attempts = (existing.data.get("attempts", 0) if existing.data else 0) + 1
        self.client.table("enrichment_queue").update({
            "attempts": attempts,
            "last_attempt": datetime.utcnow().isoformat(),
            "last_error": error[:1000],
        }).eq("id", queue_id).execute()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(TaxPortalEnricher().run())
