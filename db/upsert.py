"""
Lead ingestion pipeline. Every scraper pushes raw records here.
Handles:
  - Address & owner normalization
  - Property dedup (find or create)
  - Lead dedup (idempotent via source + source_record_id)
  - Auto-flagging from type and mailing address
  - Score calculation
  - Enrichment queueing
"""
import json
import logging
from datetime import datetime, date
from typing import Any, Optional

from db.client import get_client
from db.scoring import compute_score, merge_flags
from normalizers.address import (
    normalize_address,
    extract_zip,
    is_out_of_state,
    is_absentee,
)
from normalizers.owner import normalize_owner, owner_key

log = logging.getLogger(__name__)


def _serialize(obj):
    """JSON-safe serialization for raw_data field."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def find_or_create_property(
    address_raw: str,
    tms: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> Optional[str]:
    """Returns property_id (uuid). If TMS is known it's the strongest match key."""
    client = get_client()
    address_norm = normalize_address(address_raw)
    if not address_norm and not tms:
        return None

    # Try TMS first — strongest match
    if tms:
        try:
            res = client.table("properties").select("id").eq("tms", tms).limit(1).execute()
            if res.data:
                return res.data[0]["id"]
        except Exception as e:
            log.warning(f"TMS lookup failed: {e}")

    # Fall back to normalized address
    if address_norm:
        try:
            res = (
                client.table("properties")
                .select("id")
                .eq("address_norm", address_norm)
                .limit(1)
                .execute()
            )
            if res.data:
                # Backfill TMS if we now know it
                if tms:
                    client.table("properties").update({"tms": tms}).eq(
                        "id", res.data[0]["id"]
                    ).execute()
                return res.data[0]["id"]
        except Exception as e:
            log.warning(f"Address lookup failed: {e}")

    # Create
    payload = {
        "tms": tms,
        "address_raw": address_raw,
        "address_norm": address_norm,
        "city": city,
        "zip": zip_code or extract_zip(address_raw),
    }
    try:
        res = client.table("properties").insert(payload).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        log.error(f"Property insert failed for {address_raw}: {e}")
        return None


def upsert_lead(
    *,
    source: str,
    source_record_id: str,
    lead_type: str,
    owner: Optional[str] = None,
    address: Optional[str] = None,
    tms: Optional[str] = None,
    case_number: Optional[str] = None,
    amount: Optional[float] = None,
    filing_date: Optional[date] = None,
    plaintiff: Optional[str] = None,
    notes: Optional[str] = None,
    extra_flags: Optional[list[str]] = None,
    mailing_address: Optional[str] = None,
    raw_data: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Insert or update a lead. Returns {"action": "inserted"|"updated"|"skipped", "lead_id": ...}.

    Idempotent on (source, source_record_id) — re-running a scraper will not create duplicates.
    """
    client = get_client()

    # Normalize identifying fields
    address_norm = normalize_address(address) if address else ""
    owner_norm = owner_key(owner) if owner else ""

    # Find/create the property
    property_id = None
    if address or tms:
        property_id = find_or_create_property(
            address_raw=address or "",
            tms=tms,
            zip_code=extract_zip(address) if address else None,
        )

    # Build flag set
    flags = list(extra_flags or [])
    if mailing_address:
        if is_absentee(address, mailing_address):
            flags.append("absentee")
        if is_out_of_state(mailing_address):
            flags.append("out_of_state")
    flags = merge_flags(lead_type, flags)
    score = compute_score(flags)

    # Normalize raw_data for jsonb insertion
    safe_raw = json.loads(json.dumps(raw_data or {}, default=_serialize))

    payload = {
        "property_id": property_id,
        "source": source,
        "source_record_id": source_record_id,
        "lead_type": lead_type,
        "owner_raw": owner,
        "owner_norm": owner_norm,
        "address_raw": address,
        "address_norm": address_norm,
        "case_number": case_number,
        "amount": amount,
        "filing_date": filing_date.isoformat() if isinstance(filing_date, date) else filing_date,
        "plaintiff": plaintiff,
        "notes": notes,
        "flags": flags,
        "score": score,
        "raw_data": safe_raw,
    }

    # Check existing
    existing = (
        client.table("leads")
        .select("id, score, flags")
        .eq("source", source)
        .eq("source_record_id", source_record_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        lead_id = existing.data[0]["id"]
        # Merge flags (preserve any flags added later by enrichment)
        merged = sorted(set(existing.data[0].get("flags", []) + flags))
        payload["flags"] = merged
        payload["score"] = compute_score(merged)
        client.table("leads").update(payload).eq("id", lead_id).execute()
        action = "updated"
    else:
        ins = client.table("leads").insert(payload).execute()
        lead_id = ins.data[0]["id"] if ins.data else None
        action = "inserted"

    # Queue for enrichment if we have a property and no enrichment yet
    if property_id and lead_id and action == "inserted":
        try:
            prop = (
                client.table("properties")
                .select("enriched_at")
                .eq("id", property_id)
                .single()
                .execute()
            )
            if prop.data and not prop.data.get("enriched_at"):
                # Higher priority for higher-score leads
                priority = 1 if score >= 60 else 5
                client.table("enrichment_queue").insert({
                    "property_id": property_id,
                    "lead_id": lead_id,
                    "priority": priority,
                }).execute()
        except Exception as e:
            log.warning(f"Enrichment queue insert failed: {e}")

    return {"action": action, "lead_id": lead_id, "property_id": property_id, "score": score}


def start_scrape_run(source: str) -> str:
    """Returns run_id for use in finish_scrape_run."""
    client = get_client()
    res = client.table("scrape_runs").insert({
        "source": source,
        "status": "running",
    }).execute()
    return res.data[0]["id"]


def finish_scrape_run(
    run_id: str,
    *,
    status: str,
    found: int = 0,
    new: int = 0,
    updated: int = 0,
    error: Optional[str] = None,
):
    client = get_client()
    client.table("scrape_runs").update({
        "finished_at": datetime.utcnow().isoformat(),
        "status": status,
        "records_found": found,
        "records_new": new,
        "records_updated": updated,
        "error_message": error,
    }).eq("id", run_id).execute()
