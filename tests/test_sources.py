"""Connector tests against the bundled sample fixtures. Run: python -m unittest -v"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import AGENTS, build_user_message  # noqa: E402
from sources import build_scenario, load_manifest  # noqa: E402
from sources.base import Context  # noqa: E402
from sources.carriers import DCSAScheduleSource, RouteCSVSource  # noqa: E402
from sources.export_controls import ExportControlRulesSource  # noqa: E402
from sources.feeds import JSONFeedSource, RSSFeedSource  # noqa: E402
from sources.geo import chokepoints_on_route  # noqa: E402
from sources.sanctions import CountryEmbargoSource, SanctionsListSource, similarity  # noqa: E402

CNC = load_manifest((ROOT / "examples/manifests/cnc_tashkent.json").read_text(), "cnc.json")
BAT = load_manifest((ROOT / "examples/manifests/batteries_rotterdam.csv").read_text(), "bat.csv")


class Manifest(unittest.TestCase):
    def test_json_aliases(self):
        self.assertEqual(CNC["origin"], "Hamburg")
        self.assertEqual(CNC["destination"], "Tashkent")
        self.assertEqual(CNC["declared_value_usd"], 6_400_000)
        self.assertEqual(CNC["shipment_id"], "BK-77310")

    def test_csv_key_value(self):
        self.assertEqual(BAT["origin"], "Shanghai")
        self.assertEqual(BAT["deadline_days"], 40)

    def test_missing_required(self):
        with self.assertRaises(ValueError):
            load_manifest('{"origin": "Hamburg"}')


class Carriers(unittest.TestCase):
    def test_route_csv_filters_lane(self):
        r = RouteCSVSource("csv", "examples/carriers/routes.csv").routes(CNC)
        self.assertEqual(set(r), {"GULF_IRAN", "MIDDLE_CORRIDOR"})
        self.assertIn("Hormozgan Feeder Lines Co", r["GULF_IRAN"]["parties"])
        self.assertIn("Suez Canal", chokepoints_on_route(r["GULF_IRAN"]))
        self.assertEqual(r["MIDDLE_CORRIDOR"]["legs"][1]["mode"], "land")

    def test_dcsa_with_rates(self):
        r = DCSAScheduleSource("dcsa", "examples/carriers/dcsa_point_to_point_sample.json",
                               rate_sheet="examples/carriers/rate_sheet.csv").routes(BAT)
        self.assertEqual(len(r), 2)
        cape, suez = r["DCSA_1"], r["DCSA_2"]
        self.assertEqual((cape["transit_days"], cape["est_cost_usd"]), (38, 588000))
        self.assertEqual((suez["transit_days"], suez["est_cost_usd"]), (29, 495000))
        self.assertIn("Cape of Good Hope", chokepoints_on_route(cape))
        self.assertIn("Bab el-Mandeb", chokepoints_on_route(suez))


class Feeds(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(CNC, RouteCSVSource("csv", "examples/carriers/routes.csv").routes(CNC))

    def test_rss_filters_to_route(self):
        b = RSSFeedSource(name="sec", category="Security", url="examples/feeds/maritime_security.xml",
                          max_age_days=3650).fetch(self.ctx)
        locs = {x.location for x in b}
        self.assertIn("Bab el-Mandeb", locs)
        self.assertIn("Strait of Hormuz", locs)
        self.assertNotIn("Gulf of Guinea", locs)            # not on these routes
        self.assertTrue(all(x.lat is not None for x in b))
        hormuz = next(x for x in b if x.location == "Strait of Hormuz")
        self.assertEqual(hormuz.severity, "CRITICAL")

    def test_max_age(self):
        b = RSSFeedSource(name="sec", category="Security", url="examples/feeds/maritime_security.xml",
                          max_age_days=0, require_route_match=False).fetch(self.ctx)
        self.assertEqual(b, [])

    def test_atom_and_json(self):
        a = RSSFeedSource(name="ports", category="Canal/Port", url="examples/feeds/port_notices.xml",
                          max_age_days=3650).fetch(self.ctx)
        self.assertTrue(any("Caspian" in x.location or "Aktau" in x.text for x in a))
        self.assertFalse(any("Santos" in x.text for x in a))
        j = JSONFeedSource(name="canal", category="Canal/Port", url="examples/feeds/canal_notices.json",
                           items_path="notices", max_age_days=3650,
                           fields={"title": "headline", "summary": "body", "time": "published", "link": "url"}
                           ).fetch(self.ctx)
        self.assertTrue(any("Suez" in x.text for x in j))
        self.assertFalse(any("Panama" in x.text for x in j))


class Sanctions(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(CNC, RouteCSVSource("csv", "examples/carriers/routes.csv").routes(CNC))

    def test_similarity(self):
        self.assertEqual(similarity("Gulf Link Freight FZE", "GULF LINK FREIGHT FZE"), 1.0)
        self.assertLess(similarity("Rhine E-Mobility BV", "Northern Star Shipping LLC"), 0.5)

    def test_ofac_hit_on_notify_party(self):
        b = SanctionsListSource("ofac", "examples/sanctions/ofac_sdn_sample.csv", "ofac_sdn_csv").fetch(self.ctx)
        self.assertTrue(any(x.severity == "CRITICAL" and "manifest.notify_party" in x.text for x in b))

    def test_uk_and_eu_hit_on_route_party(self):
        uk = SanctionsListSource("uk", "examples/sanctions/uk_sample.csv", "uk_csv").fetch(self.ctx)
        eu = SanctionsListSource("eu", "examples/sanctions/eu_sample.csv", "eu_fsf_csv").fetch(self.ctx)
        self.assertTrue(any("route GULF_IRAN" in x.text for x in uk))
        self.assertTrue(any("route GULF_IRAN" in x.text for x in eu))

    def test_country_embargo(self):
        b = CountryEmbargoSource("emb", {"IR": "test"}).fetch(self.ctx)
        self.assertTrue(any("passes through Bandar Abbas" in x.text for x in b))
        self.assertFalse(any("MIDDLE_CORRIDOR" in x.text for x in b))


class ExportControls(unittest.TestCase):
    def test_dual_use_without_licence(self):
        ctx = Context(CNC, {})
        b = ExportControlRulesSource("ec", "examples/export_control_rules.csv").fetch(ctx)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].severity, "CRITICAL")
        self.assertIn("2B001", b[0].text)

    def test_licence_on_file_downgrades(self):
        m = dict(CNC, export_licence="DE-2B001-4471")
        b = ExportControlRulesSource("ec", "examples/export_control_rules.csv").fetch(Context(m, {}))
        self.assertEqual(b[0].severity, "HIGH")

    def test_batteries_not_licence(self):
        b = ExportControlRulesSource("ec", "examples/export_control_rules.csv").fetch(Context(BAT, {}))
        self.assertEqual(b[0].severity, "MEDIUM")


class EndToEnd(unittest.TestCase):
    def test_build_cnc(self):
        sc, report = build_scenario(CNC, "config/sources.toml")
        ok = [r for r in report if r["status"] == "ok"]
        self.assertGreaterEqual(len(ok), 8)
        self.assertEqual(set(sc["routes"]), {"GULF_IRAN", "MIDDLE_CORRIDOR"})
        ids = [b["id"] for b in sc["intel"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sc["intel"][0]["severity"], "CRITICAL")
        self.assertTrue(sc["hotspots"])
        msg = build_user_message(AGENTS[1], sc, {"optimizer": {"route_id": "GULF_IRAN"}})
        self.assertIn("INTELLIGENCE FEED", msg)
        self.assertIn("SAN-01", msg)

    def test_build_batteries_merges_route_sources(self):
        sc, _ = build_scenario(BAT, "config/sources.toml")
        self.assertEqual(set(sc["routes"]), {"AE_SUEZ_CSV", "AE_CAPE_CSV", "DCSA_1", "DCSA_2"})
        self.assertTrue(any("Bab el-Mandeb" == b["location"] for b in sc["intel"]))
        json.dumps(sc)  # must be serializable for the UI / logs

    def test_disabled_and_failing_sources_are_reported(self):
        sc, report = build_scenario(CNC, "config/sources.toml")
        self.assertTrue(any(r["status"] == "disabled" for r in report))


if __name__ == "__main__":
    unittest.main()
