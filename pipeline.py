"""
Core logic: a simple sequential loop  Optimizer -> Critic -> Arbiter.

run_swarm() is a generator of Events, so any front end (Streamlit, CLI) can
render the agents "talking" token by token.

Two interchangeable backends:
  * ReplayBackend  - streams pre-recorded agent output from scenarios.py.
                     No network, identical every time: use this on stage.
  * ClaudeBackend  - calls the Claude API live with the prompts in agents.py.
If the live backend fails mid-run, the swarm falls back to replay for the
remaining agents automatically, so the demo never dies on stage.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Iterator

from agents import AGENTS, VERDICT_SCHEMAS, Agent, build_user_message

JSON_RE = re.compile(r"<json>\s*(\{.*\})\s*</json>", re.DOTALL)


@dataclass
class Event:
    type: str            # agent_start | token | agent_done | fallback | swarm_done
    agent: str = ""
    text: str = ""
    data: dict = field(default_factory=dict)


def split_output(full_text: str) -> tuple[str, dict]:
    """Return (narration, parsed JSON). Tolerates a missing closing tag."""
    narration = full_text.split("<json>")[0].strip()
    m = JSON_RE.search(full_text)
    raw = m.group(1) if m else None
    if raw is None and "<json>" in full_text:
        raw = full_text.split("<json>", 1)[1].replace("</json>", "")
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
    if not raw:
        raise ValueError("Agent returned no <json> block")
    return narration, json.loads(raw)


# --------------------------------------------------------------------------- backends

class ReplayBackend:
    name = "Replay (offline)"

    def __init__(self, speed: float = 1.0):
        # speed = multiplier; 1.0 ~ fast human reading pace
        self.delay = 0.035 / max(speed, 0.05)

    def stream(self, agent: Agent, scenario: dict, user_msg: str) -> Iterator[str]:
        if not scenario.get("script"):
            raise RuntimeError("this scenario has no replay script (connected-data runs need the Live engine)")
        script = scenario["script"][agent.key]
        text = script["narration"].strip()
        # stream word by word, with a beat after each sentence
        for token in re.findall(r"\S+\s*", text):
            yield token
            pause = self.delay * (6 if token.rstrip().endswith((".", "!", "?")) else 1)
            time.sleep(pause)
        yield "\n<json>\n" + json.dumps(script["json"], indent=2) + "\n</json>"


class ClaudeBackend:
    name = "Live (Claude API)"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import anthropic  # imported lazily so replay mode needs no SDK

        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model or os.environ.get("ROUTEGUARD_MODEL", "claude-sonnet-5-5")

    def stream(self, agent: Agent, scenario: dict, user_msg: str) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=4000,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        ) as s:
            for text in s.text_stream:
                yield text

    def repair(self, agent: Agent, user_msg: str, narration: str) -> dict:
        """Recover the verdict with a forced, schema-validated tool call when the model's
        free-text <json> block is missing or malformed. Keeps the agent's own reasoning."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            system=agent.system_prompt,
            tools=[{"name": "submit_verdict",
                    "description": f"Submit the {agent.name}'s final structured verdict.",
                    "input_schema": VERDICT_SCHEMAS[agent.key]}],
            tool_choice={"type": "tool", "name": "submit_verdict"},
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": narration.strip() or "(reasoning omitted)"},
                {"role": "user", "content": "Submit your final verdict now with the submit_verdict tool, "
                                            "consistent with the reasoning above."},
            ],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise ValueError("verdict repair returned no tool call")


# --------------------------------------------------------------------------- the loop

def run_swarm(scenario: dict, backend, fallback: ReplayBackend | None = None) -> Iterator[Event]:
    """Sequential agent loop. Each agent sees the manifest plus all earlier verdicts."""
    fallback = fallback or ReplayBackend(speed=2.0)
    ctx: dict[str, dict] = {}

    for agent in AGENTS:
        yield Event("agent_start", agent.key)
        user_msg = build_user_message(agent, scenario, ctx)
        active = backend
        for attempt in range(2):
            buf = ""
            try:
                for chunk in active.stream(agent, scenario, user_msg):
                    buf += chunk
                    yield Event("token", agent.key, chunk)
                try:
                    narration, data = split_output(buf)
                except ValueError as parse_exc:  # includes json.JSONDecodeError
                    if not hasattr(active, "repair"):
                        raise
                    narration = buf.split("<json>")[0].strip()
                    yield Event("repair", agent.key, f"{parse_exc}")
                    data = active.repair(agent, user_msg, narration)
                break
            except Exception as exc:  # network error, bad JSON, missing key...
                if attempt == 1 or active is fallback or not scenario.get("script"):
                    raise
                yield Event("fallback", agent.key, f"{type(exc).__name__}: {exc}")
                active = fallback
                backend = fallback  # stay on replay for the rest of the run
        ctx[agent.key] = data
        yield Event("agent_done", agent.key, narration, data)

    yield Event("swarm_done", data=ctx)


# --------------------------------------------------------------------------- CLI

def _cli() -> None:
    import argparse
    from scenarios import SCENARIOS

    p = argparse.ArgumentParser(description="Run the RouteGuard swarm in the terminal")
    p.add_argument("--scenario", default="red_sea", choices=list(SCENARIOS))
    p.add_argument("--manifest", help="run on your own manifest (JSON/CSV) using connected sources; implies --live")
    p.add_argument("--sources", default="config/sources.toml", help="source config for --manifest")
    p.add_argument("--ingest-only", action="store_true", help="with --manifest: print ingested data and exit")
    p.add_argument("--live", action="store_true", help="call the Claude API instead of replay")
    p.add_argument("--speed", type=float, default=20.0)
    args = p.parse_args()

    if args.manifest:
        from sources import build_scenario, load_manifest

        with open(args.manifest, encoding="utf-8") as f:
            scenario, report = build_scenario(load_manifest(f.read(), args.manifest), args.sources)
        for r in report:
            print(f"  [{r['status']}] {r['source']}: {r['items']} item(s)")
        for b in scenario["intel"]:
            print(f"  [{b['id']}] {b['severity']}: {b['text'][:140]}")
        if args.ingest_only:
            print(json.dumps({"routes": list(scenario["routes"]), "hotspots": scenario["hotspots"]}, indent=2))
            return
        args.live = True
    else:
        scenario = SCENARIOS[args.scenario]
    backend = ClaudeBackend() if args.live else ReplayBackend(speed=args.speed)
    print(f"\n=== {scenario['title']} ===  [{backend.name}]\n")
    for ev in run_swarm(scenario, backend):
        if ev.type == "agent_start":
            print(f"\n--- {ev.agent.upper()} ---")
        elif ev.type == "token":
            print(ev.text, end="", flush=True)
        elif ev.type == "fallback":
            print(f"\n[!] live call failed ({ev.text}); falling back to replay")
        elif ev.type == "swarm_done":
            a = ev.data["arbiter"]
            print(f"\n\n>>> FINAL: {a['decision']} -> {a['final_route_id']} "
                  f"({a['transit_days']} d, ${a['est_cost_usd']:,}, residual risk {a['residual_risk_score']})")


if __name__ == "__main__":
    _cli()
