"""CrusoeBackend tests with a stand-in OpenAI-compatible client (no network, no SDK)."""

import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import CrusoeBackend, _loads_lenient, run_swarm  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

GOOD = {
    "optimizer": {"route_id": "SUEZ_FAST", "transit_days": 23, "est_cost_usd": 410000,
                  "meets_deadline": True, "rationale": "fast"},
    "critic": {"verdict": "REJECT", "risk_score": 90, "flags": [
        {"severity": "CRITICAL", "category": "Security", "title": "t", "detail": "d", "evidence": "RS-01"}]},
    "arbiter": {"decision": "PIVOT", "final_route_id": "CAPE_EXPRESS", "transit_days": 30,
                "est_cost_usd": 602000, "residual_risk_score": 16, "meets_deadline": True,
                "mitigations": ["m"], "summary": "s"},
}


def _who(messages):
    sysmsg = messages[0]["content"][:40]
    return next(k for k in GOOD if k.upper() in sysmsg)


def _chunk(text):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=text))])


class FakeCompletions:
    """Optimizer streams a clean verdict; Critic omits it; Arbiter writes broken JSON.
    Tool calling is 'unsupported' (raises), JSON-schema output works."""

    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        who = _who(kw["messages"])
        if kw.get("stream"):
            text = {"optimizer": "Suez is fastest.\n<json>" + json.dumps(GOOD["optimizer"]) + "</json>",
                    "critic": "Drones at Bab el-Mandeb (RS-01). REJECT.",
                    "arbiter": "Pivot.\n<json>{\"decision\": \"PIVOT\", oops}</json>"}[who]
            return iter(_chunk(t) for t in [text[:10], text[10:]])
        if "tools" in kw:
            raise RuntimeError("tool calling not supported by this model")
        msg = types.SimpleNamespace(content="```json\n" + json.dumps(GOOD[who]) + "\n```", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def backend():
    b = CrusoeBackend.__new__(CrusoeBackend)
    b.completions = FakeCompletions()
    b.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=b.completions))
    b.model = "test-model"
    return b


class Crusoe(unittest.TestCase):
    def test_full_swarm_with_recovery(self):
        b = backend()
        evs = list(run_swarm(SCENARIOS["red_sea"], b))
        kinds = [(e.type, e.agent) for e in evs if e.type != "token"]
        self.assertIn(("repair", "critic"), kinds)
        self.assertIn(("repair", "arbiter"), kinds)
        self.assertEqual(evs[-1].data["arbiter"]["final_route_id"], "CAPE_EXPRESS")
        # narration streamed and kept, verdict recovered
        critic_done = next(e for e in evs if e.type == "agent_done" and e.agent == "critic")
        self.assertIn("RS-01", critic_done.text)

    def test_repair_falls_through_unsupported_tools(self):
        b = backend()
        list(run_swarm(SCENARIOS["red_sea"], b))
        repairs = [c for c in b.completions.calls if not c.get("stream")]
        self.assertTrue(any("tools" in c for c in repairs))
        self.assertTrue(any(c.get("response_format", {}).get("type") == "json_schema" for c in repairs))
        for c in repairs:  # assistant turn carries the agent's own reasoning
            self.assertEqual(c["messages"][2]["role"], "assistant")

    def test_lenient_parse(self):
        self.assertEqual(_loads_lenient('<json>\n{"a": 1}\n</json>'), {"a": 1})
        self.assertEqual(_loads_lenient('```json\n{"a": 2}\n```'), {"a": 2})
        with self.assertRaises(ValueError):
            _loads_lenient("no json here")


if __name__ == "__main__":
    unittest.main()
