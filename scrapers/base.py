"""Base scraper class. All scrapers inherit run() lifecycle from here."""
import logging
import traceback
from abc import ABC, abstractmethod
from typing import Iterable

from db.upsert import upsert_lead, start_scrape_run, finish_scrape_run

log = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Subclass must define source_id and implement fetch()."""

    source_id: str = ""  # e.g. 'rp_tax_sale_xlsx'
    description: str = ""

    @abstractmethod
    def fetch(self) -> Iterable[dict]:
        """
        Yield dicts with keys:
          source_record_id (required)
          lead_type (required)
          owner, address, tms, case_number, amount, filing_date, plaintiff,
          notes, extra_flags (list), mailing_address, raw_data (dict)
        """
        ...

    def run(self) -> dict:
        """Lifecycle wrapper — handles audit log and ingest."""
        run_id = start_scrape_run(self.source_id)
        log.info(f"[{self.source_id}] starting scrape (run_id={run_id})")

        found = new = updated = 0
        error = None

        try:
            for record in self.fetch():
                if not record.get("source_record_id"):
                    log.warning(f"[{self.source_id}] record missing source_record_id, skipping")
                    continue
                found += 1
                try:
                    result = upsert_lead(source=self.source_id, **record)
                    if result["action"] == "inserted":
                        new += 1
                    elif result["action"] == "updated":
                        updated += 1
                except Exception as e:
                    log.error(f"[{self.source_id}] upsert failed: {e}\n{traceback.format_exc()}")

            finish_scrape_run(run_id, status="success", found=found, new=new, updated=updated)
            log.info(f"[{self.source_id}] done — found={found} new={new} updated={updated}")
            return {"status": "success", "found": found, "new": new, "updated": updated}

        except Exception as e:
            error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            finish_scrape_run(run_id, status="failed", found=found, new=new, updated=updated, error=error)
            log.error(f"[{self.source_id}] FAILED: {error}")
            return {"status": "failed", "error": error}
