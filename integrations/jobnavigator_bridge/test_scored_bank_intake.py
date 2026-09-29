"""Synthetic regressions for the installed JobNavigator bridge test suite.

Install beside the bridge's existing tests; no production jobs are fixtures.
"""
from dataclasses import replace
import threading
from urllib.parse import parse_qs, urlsplit

from jobnavigator_bridge.common import Budget
from jobnavigator_bridge.source import Source
from tests.support import Base, FakeTransport, job, response


class ScoredBankIntakeTests(Base):
    def bank(self, ident, *, company="Synthetic Bank", score=95):
        record = job(ident)
        record.update(
            source="direct", search_id="", company=company,
            url="https://bank.example.org/jobs/" + ident,
            source_url="", application_url="", application_type="",
            resolution_status="", cv_scores={} if score is None else {"cv": score},
            best_score=0 if score is None else score,
        )
        return record

    def test_scans_named_searches_and_scored_direct_banks(self):
        named = [job("chicago", search_id="approved"), job("india", search_id="india")]
        direct = [self.bank("bank")]
        config = replace(
            self.cfg, allowed_search_ids=["approved", "india"],
            direct_scored_companies=["Synthetic Bank"], page_size=3, page_overlap=1,
        )

        def serve(url, _):
            query = parse_qs(urlsplit(url).query)
            if "search_id" in query:
                rows = [row for row in named if row["search_id"] == query["search_id"][0]]
            else:
                self.assertEqual(["direct"], query["source"])
                self.assertEqual(["new"], query["status"])
                self.assertEqual(["1"], query["min_score"])
                rows = direct
            offset = int(query["offset"][0])
            return response({"total": len(rows), "jobs": rows[offset:offset + 3]})

        transport = FakeTransport(callback=serve)
        scan = Source(config, "synthetic-api-secret", transport).scan(Budget(20))
        self.assertTrue(scan.complete)
        self.assertEqual({"chicago", "india", "bank"}, {row["id"] for row in scan.jobs})
        self.assertEqual(3, scan.total)
        self.assertEqual(6, scan.requests)

    def test_direct_official_url_requires_completed_score_and_allowed_company(self):
        self.cfg = replace(self.cfg, direct_scored_companies=["Synthetic Bank"])
        report, state = self.run_jobs([
            self.bank("scored"),
            self.bank("unscored", score=None),
            self.bank("other", company="Other Bank"),
        ])
        self.assertTrue(report["complete"])
        self.assertEqual(1, len(self.bot.intakes))
        self.assertEqual("https://bank.example.org/jobs/scored", self.bot.intakes[0][0]["url"])
        self.assertEqual("delivered", state.record("synthetic:scored")["status"])
        self.assertEqual("pending_score", state.record("synthetic:unscored")["status"])
        self.assertEqual("excluded", state.record("synthetic:other")["status"])

    def test_independent_public_url_checks_can_finish_within_a_shared_budget(self):
        self.cfg = replace(self.cfg, direct_scored_companies=["Synthetic Bank"])
        barrier = threading.Barrier(2)

        class SlowAvailability:
            def __init__(self):
                self.calls = set()

            def check(self, url, budget):
                self.calls.add(url)
                barrier.wait(timeout=2)
                return "unknown", "availability_unverified"

        availability = SlowAvailability()
        report, state = self.run_jobs(
            [job("named"), self.bank("direct")], availability=availability,
        )
        self.assertTrue(report["complete"])
        self.assertEqual(2, len(availability.calls))
        self.assertEqual("delivered", state.record("synthetic:direct")["status"])
