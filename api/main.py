"""
FastAPI service. The HTML dashboard fetches leads from /api/leads.

Endpoints:
  GET  /api/leads           — list leads (filtered, sorted, paginated)
  GET  /api/leads/{id}      — single lead detail
  POST /api/leads           — manual lead insert
  PATCH /api/leads/{id}     — update status, notes
  GET  /api/stats           — KPI numbers
  GET  /api/sources         — scrape run history
  POST /api/scrape/{source} — trigger a scraper on demand
  POST /api/enrich          — kick off enrichment worker
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db.client import get_client
from db.upsert import upsert_lead
from enrichment.tax_portal import TaxPortalEnricher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Charleston County Lead Intelligence API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production to your dashboard's origin
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Schemas
# -----------------------------
class LeadCreate(BaseModel):
    owner: Optional[str] = None
    address: Optional[str] = None
    lead_type: str = "OTH"
    case_number: Optional[str] = None
    amount: Optional[float] = None
    notes: Optional[str] = None
    mailing_address: Optional[str] = None
    extra_flags: Optional[list[str]] = None


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/api/leads")
def list_leads(
    min_score: int = Query(0, ge=0, le=100),
    lead_type: Optional[str] = None,
    flag: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    client = get_client()
    q = client.table("v_leads_enriched").select("*").gte("score", min_score)
    if lead_type:
        q = q.eq("lead_type", lead_type)
    if status:
        q = q.eq("status", status)
    if flag:
        q = q.contains("flags", [flag])
    if search:
        # Postgres ilike on owner / address
        q = q.or_(f"owner_norm.ilike.%{search.lower()}%,address.ilike.%{search}%")

    q = q.order("score", desc=True).range(offset, offset + limit - 1)
    res = q.execute()
    return {"leads": res.data, "limit": limit, "offset": offset}


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: str):
    client = get_client()
    res = client.table("v_leads_enriched").select("*").eq("id", lead_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Lead not found")
    return res.data


@app.post("/api/leads")
def create_lead(payload: LeadCreate):
    result = upsert_lead(
        source="manual",
        source_record_id=f"manual:{datetime.utcnow().isoformat()}:{(payload.owner or '')[:40]}",
        lead_type=payload.lead_type,
        owner=payload.owner,
        address=payload.address,
        case_number=payload.case_number,
        amount=payload.amount,
        notes=payload.notes,
        mailing_address=payload.mailing_address,
        extra_flags=payload.extra_flags,
    )
    return result


@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: str, payload: LeadUpdate):
    client = get_client()
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    res = client.table("leads").update(update).eq("id", lead_id).execute()
    return {"updated": True, "data": res.data}


@app.get("/api/stats")
def stats():
    client = get_client()

    def count(filt=None):
        q = client.table("leads").select("id", count="exact")
        if filt:
            q = filt(q)
        return q.execute().count or 0

    return {
        "total_leads": count(),
        "high_score": count(lambda q: q.gte("score", 60)),
        "pre_foreclosure": count(lambda q: q.contains("flags", ["lis_pendens"])),
        "foreclosure": count(lambda q: q.contains("flags", ["foreclosure"])),
        "tax_delinquent": count(lambda q: q.contains("flags", ["tax"])),
        "probate": count(lambda q: q.contains("flags", ["probate"])),
        "code_violations": count(lambda q: q.contains("flags", ["code"])),
        "mechanic_liens": count(lambda q: q.contains("flags", ["mechanic_lien"])),
        "fed_tax_liens": count(lambda q: q.contains("flags", ["fed_tax_lien"])),
        "state_tax_liens": count(lambda q: q.contains("flags", ["state_tax_lien"])),
        "absentee": count(lambda q: q.contains("flags", ["absentee"])),
        "out_of_state": count(lambda q: q.contains("flags", ["out_of_state"])),
    }


@app.get("/api/sources")
def sources(limit: int = 50):
    client = get_client()
    res = (
        client.table("scrape_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"runs": res.data}


# -----------------------------
# On-demand scraper triggers
# -----------------------------
SCRAPER_REGISTRY = {}


def _load_scrapers():
    """Lazy-import scrapers only when triggered (avoids import cost on API boot)."""
    if SCRAPER_REGISTRY:
        return
    from scrapers.rp_tax_sale import RealPropertyTaxSaleScraper
    from scrapers.sealed_bid_sale import SealedBidSaleScraper
    from scrapers.master_auction import MasterAuctionScraper
    from scrapers.sc_dor_delinquent import SCDORDelinquentScraper
    from scrapers.rod_daybook import RODDaybookScraper
    from scrapers.clerk_daybook import ClerkDaybookScraper
    from scrapers.pending_cases import PendingCasesScraper
    from scrapers.probate import ProbateScraper
    from scrapers.magistrate_evictions import MagistrateEvictionScraper
    from scrapers.hutchens_foreclosure import HutchensForeclosureScraper
    from parsers.mobile_home_tax import MobileHomeTaxParser

    SCRAPER_REGISTRY.update({
        "rp_tax_sale": RealPropertyTaxSaleScraper,
        "sealed_bid_sale": SealedBidSaleScraper,
        "master_auction": MasterAuctionScraper,
        "sc_dor_delinquent": SCDORDelinquentScraper,
        "rod_daybook": RODDaybookScraper,
        "clerk_daybook": ClerkDaybookScraper,
        "pending_cases": PendingCasesScraper,
        "probate": ProbateScraper,
        "magistrate_evictions": MagistrateEvictionScraper,
        "hutchens_foreclosure": HutchensForeclosureScraper,
        "mobile_home_tax": MobileHomeTaxParser,
    })


@app.post("/api/scrape/{source}")
def trigger_scrape(source: str, background_tasks: BackgroundTasks):
    _load_scrapers()
    cls = SCRAPER_REGISTRY.get(source)
    if not cls:
        raise HTTPException(404, f"Unknown source. Available: {list(SCRAPER_REGISTRY.keys())}")

    def _run():
        try:
            cls().run()
        except Exception as e:
            log.error(f"Background scrape {source} failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "source": source}


@app.post("/api/enrich")
def trigger_enrichment(background_tasks: BackgroundTasks, batch_size: int = 50):
    def _run():
        try:
            TaxPortalEnricher(batch_size=batch_size).run()
        except Exception as e:
            log.error(f"Enrichment job failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "batch_size": batch_size}


@app.get("/api/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
