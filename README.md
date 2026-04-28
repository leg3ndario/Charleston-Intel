# Charleston County Lead Intelligence Backend

Production-grade scraper + enrichment + API stack for the Charleston County motivated-seller dashboard.

## What's in here

```
scrapers/         11 scrapers (5 fully-auto, 6 Playwright-based)
parsers/          PDF parser for Mobile Home Tax list
enrichment/       Auto-enrichment from the tax portal (absentee/OOS flags)
normalizers/      Address + owner normalizers (the dedup brain)
db/               Supabase schema, client, scoring engine, upsert pipeline
api/              FastAPI service the dashboard reads
scheduler/        Cron orchestrator (APScheduler)
tests/            31 unit tests (all passing)
```

---

## One-time setup (about 30 minutes)

### 1. Create a Supabase project
- Go to https://app.supabase.com → New Project
- Pick a region close to you (us-east-1)
- Save the password somewhere safe
- Once it's up, go to **Settings → API** and copy:
  - Project URL → `SUPABASE_URL`
  - `service_role` secret → `SUPABASE_SERVICE_KEY` (this is the backend key, NEVER ship to a browser)
  - `anon` public key → `SUPABASE_ANON_KEY` (safe for the dashboard)

### 2. Run the schema
- In Supabase, **SQL Editor → New Query**
- Paste the contents of `db/schema.sql` and run it
- You should see "Success. No rows returned." Tables are created.

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your real Supabase URL and keys
```

### 4. Install dependencies (local Python)
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 5. Verify everything works
```bash
PYTHONPATH=. python -m pytest tests/ -v
# Should see 31 passed
```

---

## Running it

### Option A — local development
Two processes:
```bash
# Terminal 1: API
PYTHONPATH=. uvicorn api.main:app --reload --port 8000

# Terminal 2: scheduler
PYTHONPATH=. python -m scheduler.runner
```

Then point your dashboard at `http://localhost:8000/api/leads`.

### Option B — Docker (one command)
```bash
docker-compose up --build
```

### Option C — production deploy
- Push the Docker image to a registry
- Deploy two services from the same image:
  - **API** — runs `uvicorn api.main:app --host 0.0.0.0 --port 8000`
  - **Worker** — runs `python -m scheduler.runner`
- Recommended hosts: Fly.io, Railway, Render. All have free tiers that fit this workload.

---

## Triggering scrapers manually

For first-run / testing, you don't want to wait for cron. Run any single scraper:

```bash
# By module
PYTHONPATH=. python -m scrapers.rp_tax_sale
PYTHONPATH=. python -m scrapers.master_auction

# Or by job group via scheduler
PYTHONPATH=. python -m scheduler.runner fast      # all daily fast scrapers
PYTHONPATH=. python -m scheduler.runner daybook   # ROD + Clerk daybook
PYTHONPATH=. python -m scheduler.runner heavy     # weekly heavy scrapers
PYTHONPATH=. python -m scheduler.runner enrich    # drain enrichment queue
PYTHONPATH=. python -m scheduler.runner all       # everything

# Or via API
curl -X POST http://localhost:8000/api/scrape/rp_tax_sale
curl -X POST http://localhost:8000/api/enrich
```

---

## Schedule (defaults)

| Cadence | Job | What runs |
|---|---|---|
| Daily 6:00 AM ET | `fast` | RP Tax Sale, Sealed Bid, Master Auction, Mobile Home PDF, Hutchens |
| Daily 7:00 AM ET | `daybook` | ROD Day Book, Clerk Daybook |
| Weekly Sun 6:30 AM | `heavy` | Pending Cases, Probate, Magistrate Evictions |
| Quarterly (Mar/Jun/Sep/Dec 1st) | `dor` | SC DOR Top Delinquent |
| Hourly :15 | `enrich` | Drain enrichment queue (30 properties/cycle) |

Edit `scheduler/runner.py` to change cadence.

---

## Connecting the dashboard

The HTML dashboard you have currently uses browser storage. To make it use this backend, swap the data source. In the dashboard's `<script>` at the top, replace the `loadLeads()` function with:

```javascript
async function loadLeads() {
  const resp = await fetch("http://localhost:8000/api/leads?limit=500");
  const data = await resp.json();
  leads = data.leads.map(l => ({
    id: l.id,
    owner: l.owner_raw,
    address: l.address,
    mailing: l.mailing_address,
    type: l.lead_type,
    case: l.case_number,
    amount: l.amount,
    source: l.source,
    flags: l.flags || [],
    notes: l.notes || '',
    phone: '',
    score: l.score,
  }));
}
```

For KPIs:
```javascript
async function renderKPIs() {
  const r = await fetch("http://localhost:8000/api/stats");
  const s = await r.json();
  // ... render using s.total_leads, s.high_score, etc.
}
```

---

## How it actually works (architecture)

```
┌─────────────────────────────────────────────────────────────┐
│  Charleston County data sources (28 portals)                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ XLSX    │  │ PDF     │  │ HTML    │  │ JCMS    │  ...    │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
└───────┼────────────┼────────────┼────────────┼──────────────┘
        ▼            ▼            ▼            ▼
   ┌─────────────────────────────────────────────────┐
   │ Scrapers (requests / pdfplumber / Playwright)   │
   └────────────────────┬────────────────────────────┘
                        ▼
   ┌─────────────────────────────────────────────────┐
   │ upsert_lead() — normalize, dedupe, score,       │
   │ queue for enrichment                            │
   └────────────────────┬────────────────────────────┘
                        ▼
   ┌─────────────────────────────────────────────────┐
   │ Supabase (Postgres)                             │
   │  - properties (canonical, dedupe key = TMS)     │
   │  - leads (one per signal, idempotent)           │
   │  - enrichment_queue                             │
   │  - scrape_runs (audit log)                      │
   └────┬─────────────────────────────────┬──────────┘
        ▼                                 ▼
   ┌──────────────────┐         ┌────────────────────┐
   │ Enrichment job   │         │ FastAPI /api/leads │
   │ (hourly)         │         │ /api/stats         │
   │ Pulls tax portal │         │ /api/scrape/{src}  │
   │ → flags absentee │         └─────────┬──────────┘
   │ → flags OOS      │                   ▼
   │ → re-score leads │         ┌────────────────────┐
   └──────────────────┘         │ Your HTML dashboard│
                                └────────────────────┘
```

---

## What gets flagged automatically

When a new lead comes in:

1. **From its source type** — TAX → `tax`, LP → `lis_pendens`, etc.
2. **From its mailing address (after enrichment)** —
   - Mailing state ≠ SC → `out_of_state` (+15 score)
   - Mailing address ≠ property address → `absentee` (+15 score)
3. **From explicit flags** the scraper attached (e.g. `state_tax_lien`, `mechanic_lien`)
4. **Multi-flag bonus** — +10 per flag beyond the first

Score caps at 100. ≥60 = worth working. ≥80 = priority.

---

## Adding new scrapers

1. Create `scrapers/your_source.py` inheriting `BaseScraper`
2. Implement `fetch()` yielding dicts with required keys
3. Add to `SCRAPER_REGISTRY` in `api/main.py`
4. Add to a job group in `scheduler/runner.py`

The base class handles audit logging, error capture, and ingestion automatically.

---

## Compliance

SC Code §30-2-50 prohibits using public records for **commercial solicitation directed to any person in SC**. Use this system for research, underwriting, target identification, and due diligence — not for direct cold outreach to leads. Run your outreach through compliant channels (PPL opt-in, paid media, etc.) and confirm with your attorney.

---

## Troubleshooting

**"SUPABASE_URL must be set"** — your `.env` isn't loaded. Make sure you're running from the project root and `.env` exists.

**Playwright scraper says "could not fill date form"** — the county portal HTML changed. Open the portal in your browser, inspect the date input's name/id attribute, and add it to the selector list in that scraper's `fetch()`.

**Tests pass but scraping returns 0 records** — most county portals are quiet on weekends. Try running on a weekday morning, or extend the `days_back` parameter.

**Enrichment queue grows but never drains** — check that the API/scheduler service can reach `https://sc-charleston.publicaccessnow.com`. Some hosts block outbound traffic to unknown domains by default.

**Charleston portal changed its layout** — the scrapers are written defensively (multiple selector fallbacks per field) but eventually need updates. Run a single scraper with `headless=False` in `playwright_base.py` to watch what it sees.
