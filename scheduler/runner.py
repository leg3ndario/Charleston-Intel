"""
Cron orchestrator. Runs scrapers + enrichment on a schedule.

Run with:  python -m scheduler.runner
Or deploy as a service (systemd, Docker, fly.io machine, Railway worker, etc).

Schedule:
  Daily 6am — fast scrapers (XLSX downloads, static HTML)
  Daily 7am — Playwright daybook scrapers
  Hourly   — enrichment worker drains queue
  Weekly Sun 6am — heavy scrapers (pending cases, probate, evictions)
  Quarterly — SC DOR delinquent list (manual trigger or 1st of Mar/Jun/Sep/Dec)
"""
import logging
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

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
from enrichment.tax_portal import TaxPortalEnricher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def safe_run(scraper_cls, *args, **kwargs):
    """Run a scraper, never let an exception kill the scheduler."""
    name = scraper_cls.__name__
    log.info(f"=== Starting {name} ===")
    try:
        result = scraper_cls(*args, **kwargs).run()
        log.info(f"=== {name} done: {result} ===")
    except Exception as e:
        log.exception(f"!!! {name} crashed: {e}")


def daily_fast_scrapers():
    """Lightweight: XLSX downloads + static HTML pages. ~5 min total."""
    safe_run(RealPropertyTaxSaleScraper)
    safe_run(SealedBidSaleScraper)
    safe_run(MasterAuctionScraper)
    safe_run(MobileHomeTaxParser)
    safe_run(HutchensForeclosureScraper)


def daily_daybook_scrapers():
    """Playwright-based, pulls yesterday's filings. ~5-10 min."""
    safe_run(RODDaybookScraper, days_back=1)
    safe_run(ClerkDaybookScraper, days_back=1)


def weekly_heavy_scrapers():
    """Heavier queries that don't need daily cadence. ~15-30 min."""
    safe_run(PendingCasesScraper, days_back=7)
    safe_run(ProbateScraper, days_back=14)
    safe_run(MagistrateEvictionScraper, days_back=7)


def quarterly_dor():
    safe_run(SCDORDelinquentScraper)


def hourly_enrichment():
    log.info("=== Enrichment cycle ===")
    try:
        result = TaxPortalEnricher(batch_size=30).run()
        log.info(f"Enrichment: {result}")
    except Exception as e:
        log.exception(f"Enrichment failed: {e}")


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone="America/New_York")

    # Daily fast scrapers — 6:00 AM ET
    sched.add_job(daily_fast_scrapers, CronTrigger(hour=6, minute=0), id="daily_fast", name="Daily fast scrapers")
    # Daily daybook scrapers — 7:00 AM ET
    sched.add_job(daily_daybook_scrapers, CronTrigger(hour=7, minute=0), id="daily_daybook", name="Daily daybook scrapers")
    # Weekly heavy scrapers — Sunday 6:00 AM ET
    sched.add_job(weekly_heavy_scrapers, CronTrigger(day_of_week="sun", hour=6, minute=30), id="weekly_heavy", name="Weekly heavy scrapers")
    # Quarterly SC DOR — 1st of Mar/Jun/Sep/Dec at 8:00 AM ET
    sched.add_job(quarterly_dor, CronTrigger(month="3,6,9,12", day=1, hour=8, minute=0), id="quarterly_dor", name="Quarterly SC DOR")
    # Hourly enrichment drain
    sched.add_job(hourly_enrichment, CronTrigger(minute=15), id="hourly_enrich", name="Hourly enrichment")

    return sched


def run_now(job_name: str):
    """Run a single job immediately, for manual ops."""
    jobs = {
        "fast": daily_fast_scrapers,
        "daybook": daily_daybook_scrapers,
        "heavy": weekly_heavy_scrapers,
        "dor": quarterly_dor,
        "enrich": hourly_enrichment,
        "all": lambda: (daily_fast_scrapers(), daily_daybook_scrapers(),
                        weekly_heavy_scrapers(), quarterly_dor(), hourly_enrichment()),
    }
    if job_name not in jobs:
        print(f"Unknown job '{job_name}'. Available: {list(jobs.keys())}")
        sys.exit(1)
    jobs[job_name]()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Manual one-shot mode: python -m scheduler.runner fast
        run_now(sys.argv[1])
    else:
        log.info(f"Scheduler starting at {datetime.now()}")
        build_scheduler().start()
