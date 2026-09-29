"""Breaking-news re-check tests: twists replay cleanly and prompts review the booked plan."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import ARBITER, CRITIC, VERDICT_SCHEMAS, build_user_message  # noqa: E402
from pipeline import (ReplayBackend, make_breaking_bulletin, recheck_scenario,  # noqa: E402
                      run_recheck, run_swarm)
from scenarios import SCENARIOS  # noqa: E402

_TYPES = {"integer": int, "string": str, "boolean": bool, "array": list, "object": dict}


def check_schema(tc: unittest.TestCase, value, schema: dict, path: str = "$"):
    """Just enough JSON Schema (type, enum, required, properties, items) for the verdicts."""
    tc.assertIsInstance(value, _TYPES[schema["type"]], path)
    if "enum" in schema:
        tc.assertIn(value, schema["enum"], path)
    for key in schema.get("required", []):
        tc.assertIn(key, value, f"{path}.{key}")
    for key, sub in schema.get("properties", {}).items():
        if key in value:
            check_schema(tc, value[key], sub, f"{path}.{key}")
    if schema["type"] == "array":
        for i, item in enumerate(value):
            check_schema(tc, item, schema["items"], f"{path}[{i}]")


def run(events) -> tuple[dict, list[str]]:
    started, ctx = [], {}
    for ev in events:
        if ev.type == "agent_start":
            started.append(ev.agent)
        elif ev.type == "swarm_done":
            ctx = ev.data
    return ctx, started


class Twists(unittest.TestCase):
    def test_every_scenario_has_a_valid_twist(self):
        for key, scen in SCENARIOS.items():
            with self.subTest(scenario=key):
                self.assertTrue(scen.get("twists"))
                for t in scen["twists"]:
                    self.assertEqual(t["bulletin"]["id"], "NEW-01")
                    for agent in ("critic", "arbiter"):
                        check_schema(self, t["script"][agent]["json"], VERDICT_SCHEMAS[agent])
                    self.assertIn(t["script"]["arbiter"]["json"]["final_route_id"], scen["routes"])

    def test_twist_replays_and_skips_optimizer(self):
        fast = ReplayBackend(speed=1e6)
        for key, scen in SCENARIOS.items():
            with self.subTest(scenario=key):
                first, _ = run(run_swarm(scen, fast, fast))
                t = scen["twists"][0]
                rescen = recheck_scenario(scen, t["bulletin"], t["hotspot"], t["script"])
                ctx, started = run(run_recheck(rescen, fast, first, fast))
                self.assertEqual(started, ["critic", "arbiter"])
                self.assertEqual(ctx["current_plan"], first["arbiter"])
                self.assertIn(ctx["arbiter"]["final_route_id"], scen["routes"])

    def test_cold_chain_hurricane_pivots_to_air(self):
        scen = SCENARIOS["cold_chain"]
        fast = ReplayBackend(speed=1e6)
        first, _ = run(run_swarm(scen, fast, fast))
        t = scen["twists"][0]
        ctx, _ = run(run_recheck(recheck_scenario(scen, t["bulletin"], t["hotspot"], t["script"]), fast, first, fast))
        self.assertEqual((ctx["arbiter"]["decision"], ctx["arbiter"]["final_route_id"]), ("PIVOT", "AIR_PHARMA"))


class RecheckPrompts(unittest.TestCase):
    def setUp(self):
        scen = SCENARIOS["red_sea"]
        t = scen["twists"][0]
        self.scen = recheck_scenario(scen, t["bulletin"], t["hotspot"], t["script"])
        self.plan = scen["script"]["arbiter"]["json"]

    def test_critic_reviews_booked_plan(self):
        msg = build_user_message(CRITIC, self.scen, {"current_plan": self.plan})
        self.assertIn("CURRENT BOOKED PLAN", msg)
        self.assertIn("[NEW-01]", msg)
        self.assertIn("BREAKING bulletin just arrived (NEW-01)", msg)
        self.assertNotIn("OPTIMIZER PROPOSAL", msg)

    def test_arbiter_is_told_to_weigh_rebooking(self):
        msg = build_user_message(ARBITER, self.scen, {"current_plan": self.plan, "critic": {"verdict": "CONDITIONAL"}})
        self.assertIn("Confirm or change the booked plan", msg)
        self.assertIn("CRITIC FINDINGS", msg)

    def test_chained_bulletins_keep_only_latest_new(self):
        b2, h2 = make_breaking_bulletin("Port strike at Rotterdam", self.scen, "NEW-02")
        chained = recheck_scenario(self.scen, b2, h2)
        self.assertEqual([b["id"] for b in chained["intel"] if b.get("new")], ["NEW-02"])
        self.assertEqual([h["name"] for h in chained["hotspots"] if h.get("new")], ["Rotterdam"])


class BreakingBulletin(unittest.TestCase):
    def test_pins_to_route_place_with_severity(self):
        b, h = make_breaking_bulletin("Port strike at Cape Town", SCENARIOS["red_sea"])
        self.assertEqual((b["id"], b["severity"], b["category"]), ("NEW-01", "HIGH", "Labor"))
        self.assertEqual(h["name"], "Cape Town")

    def test_unplaced_text_has_no_hotspot(self):
        b, h = make_breaking_bulletin("Carrier announces new booking portal", SCENARIOS["red_sea"])
        self.assertIsNone(h)
        self.assertEqual(b["category"], "Carrier")


if __name__ == "__main__":
    unittest.main()
