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

from agents import AGENTS, ARBITER, CRITIC, VERDICT_SCHEMAS, Agent, build_user_message

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


class CrusoeBackend:
    """Open-weight models on Crusoe Managed Inference (OpenAI-compatible API).

    Same interface as ClaudeBackend: stream() for the agent's reasoning, repair() to
    recover a missing or malformed verdict. Open models differ in what they support,
    so repair() tries forced tool calling, then JSON-schema output, then JSON mode,
    then a plain "JSON only" retry."""

    name = "Live (Crusoe)"
    BASE_URL = "https://api.crusoe.ai/v1"
    DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None):
        from openai import OpenAI  # imported lazily so replay mode needs no SDK

        self.client = OpenAI(api_key=api_key or os.environ.get("CRUSOE_API_KEY"),
                             base_url=base_url or os.environ.get("CRUSOE_BASE_URL", self.BASE_URL))
        self.model = model or os.environ.get("CRUSOE_MODEL", self.DEFAULT_MODEL)

    def _messages(self, agent: Agent, user_msg: str) -> list[dict]:
        return [{"role": "system", "content": agent.system_prompt},
                {"role": "user", "content": user_msg}]

    def stream(self, agent: Agent, scenario: dict, user_msg: str) -> Iterator[str]:
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=4000, temperature=0.3, stream=True,
            messages=self._messages(agent, user_msg))
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def repair(self, agent: Agent, user_msg: str, narration: str) -> dict:
        schema = VERDICT_SCHEMAS[agent.key]
        msgs = self._messages(agent, user_msg) + [
            {"role": "assistant", "content": narration.strip() or "(reasoning omitted)"},
            {"role": "user", "content": "Submit your final verdict now, consistent with the reasoning above. "
                                        "Return only the JSON object, matching this schema: " + json.dumps(schema)}]
        attempts = [
            dict(tools=[{"type": "function", "function": {
                "name": "submit_verdict", "description": f"Submit the {agent.name}'s final verdict.",
                "parameters": schema}}],
                 tool_choice={"type": "function", "function": {"name": "submit_verdict"}}),
            dict(response_format={"type": "json_schema",
                                  "json_schema": {"name": "verdict", "schema": schema}}),
            dict(response_format={"type": "json_object"}),
            dict(),
        ]
        errors = []
        for extra in attempts:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, max_tokens=3000, temperature=0, messages=msgs, **extra)
                msg = resp.choices[0].message
                calls = getattr(msg, "tool_calls", None) or []
                raw = calls[0].function.arguments if calls else (msg.content or "")
                data = _loads_lenient(raw)
                missing = [k for k in schema.get("required", []) if k not in data]
                if missing:
                    raise ValueError(f"verdict missing {missing}")
                return data
            except Exception as exc:  # unsupported feature or bad output: try the next way
                errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
        raise ValueError("verdict repair failed: " + " | ".join(errors))


def _loads_lenient(raw: str) -> dict:
    """Parse a JSON object from model output that may carry fences or <json> tags."""
    raw = raw.strip()
    if "<json>" in raw or "```" in raw:
        raw = re.sub(r"^```(?:json)?|```$", "", raw.split("<json>")[-1].replace("</json>", "").strip()).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in output")
    return json.loads(raw[start:end + 1])


def make_live_backend(provider: str, model: str | None = None, api_key: str | None = None):
    """'claude' or 'crusoe' -> a live backend."""
    return (CrusoeBackend if provider == "crusoe" else ClaudeBackend)(model=model, api_key=api_key)


# --------------------------------------------------------------------------- the loop

def run_swarm(scenario: dict, backend, fallback: ReplayBackend | None = None,
              agents: list[Agent] | None = None, ctx: dict | None = None) -> Iterator[Event]:
    """Sequential agent loop. Each agent sees the manifest plus all earlier verdicts.
    `agents` and a seeded `ctx` let a re-check resume part-way down the chain."""
    fallback = fallback or ReplayBackend(speed=2.0)
    ctx = dict(ctx or {})

    for agent in agents or AGENTS:
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


# --------------------------------------------------------------------------- re-check

def recheck_scenario(scenario: dict, bulletin: dict, hotspot: dict | None = None,
                     script: dict | None = None) -> dict:
    """The scenario as it stands after a breaking bulletin: the bulletin (marked new) leads the
    intel feed, its hotspot joins the map, and `script` replaces the replay script."""
    def old(items):  # earlier breaking items stay in the feed but are no longer "new"
        return [{k: v for k, v in i.items() if k != "new"} for i in items]

    b = {"time": "BREAKING", **bulletin, "new": True}
    return {**scenario, "intel": [b, *old(scenario["intel"])],
            "hotspots": [*old(scenario["hotspots"]), *([{**hotspot, "new": True}] if hotspot else [])],
            "script": script}


def run_recheck(scenario: dict, backend, prior_ctx: dict, fallback: ReplayBackend | None = None) -> Iterator[Event]:
    """Re-check a booked plan after `recheck_scenario`: the Critic attacks the previous Arbiter
    decision and the Arbiter confirms or changes it. The Optimizer is blind to intel, so it
    would only propose the same route again and does not run."""
    return run_swarm(scenario, backend, fallback, agents=[CRITIC, ARBITER],
                     ctx={"current_plan": prior_ctx["arbiter"]})


# keyword -> category; each regex matches at a word start so "port" doesn't fire on "report"
_CATEGORY_RULES = [
    ("Sanctions", r"\b(sanction|designat|embargo|asset freeze)"),
    ("Export Control", r"\b(export|licen[cs]e|dual-use)"),
    ("Security", r"\b(attack|missile|drone|pira|hijack|seiz|boarding|war\b)"),
    ("Labor", r"\b(strike|stoppage|union|walkout)"),
    ("Weather", r"\b(storm|hurricane|typhoon|cyclone|flood|fog|gale|wind)"),
    ("Insurance", r"\b(insur|premium|underwrit|cover\b)"),
    ("Canal/Port", r"\b(canal|ports?\b|terminal|berth|queue|congestion|ferry|draft)"),
]


def make_breaking_bulletin(text: str, scenario: dict, bid: str = "NEW-01") -> tuple[dict, dict | None]:
    """Turn free text into a citable bulletin, pinned to the first port or chokepoint it names
    on any candidate route (deterministic, the same matching the connected sources use)."""
    from sources.base import guess_severity
    from sources.geo import match_location, places_for_routes

    t = text.strip().lower()
    category = next((c for c, rx in _CATEGORY_RULES if re.search(rx, t)), "Carrier")
    bulletin = {"id": bid, "source": "Breaking news (injected)", "category": category,
                "severity": guess_severity(text, default="HIGH"), "text": text.strip()}
    hit = match_location(text, places_for_routes(scenario["routes"]))
    hotspot = {"name": hit[0], "lat": hit[1], "lon": hit[2], "label": f"{hit[0]}: breaking ({bid})"} if hit else None
    return bulletin, hotspot


# --------------------------------------------------------------------------- CLI

def _cli() -> None:
    import argparse
    from scenarios import SCENARIOS

    p = argparse.ArgumentParser(description="Run the RouteGuard swarm in the terminal")
    p.add_argument("--scenario", default="red_sea", choices=list(SCENARIOS))
    p.add_argument("--manifest", help="run on your own manifest (JSON/CSV) using connected sources; implies --live")
    p.add_argument("--sources", default="config/sources.toml", help="source config for --manifest")
    p.add_argument("--ingest-only", action="store_true", help="with --manifest: print ingested data and exit")
    p.add_argument("--live", action="store_true", help="call a live model instead of replay")
    p.add_argument("--provider", default="claude", choices=["claude", "crusoe"],
                   help="live model provider (crusoe = open models on Crusoe Managed Inference)")
    p.add_argument("--model", help="override the provider's default model")
    p.add_argument("--speed", type=float, default=20.0)
    p.add_argument("--twist", action="store_true",
                   help="after the decision, inject the scenario's breaking-news twist and re-check")
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
    backend = make_live_backend(args.provider, args.model) if args.live else ReplayBackend(speed=args.speed)
    fallback = ReplayBackend(speed=args.speed)
    print(f"\n=== {scenario['title']} ===  [{backend.name}]\n")
    ctx = _print_run(run_swarm(scenario, backend, fallback), "FINAL")
    twists = scenario.get("twists") or []
    if args.twist and twists:
        t = twists[0]
        print(f"\n\n⚡ BREAKING [{t['bulletin']['id']}]: {t['bulletin']['text']}")
        rescen = recheck_scenario(scenario, t["bulletin"], t.get("hotspot"), t.get("script"))
        _print_run(run_recheck(rescen, backend, ctx, fallback), "UPDATED")
    elif args.twist:
        print("\n[!] this scenario has no breaking-news twist")


def _print_run(events: Iterator[Event], label: str) -> dict:
    ctx: dict = {}
    for ev in events:
        if ev.type == "agent_start":
            print(f"\n--- {ev.agent.upper()} ---")
        elif ev.type == "token":
            print(ev.text, end="", flush=True)
        elif ev.type == "fallback":
            print(f"\n[!] live call failed ({ev.text}); falling back to replay")
        elif ev.type == "swarm_done":
            ctx = ev.data
            a = ctx["arbiter"]
            print(f"\n\n>>> {label}: {a['decision']} -> {a['final_route_id']} "
                  f"({a['transit_days']} d, ${a['est_cost_usd']:,}, residual risk {a['residual_risk_score']})")
    return ctx


if __name__ == "__main__":
    _cli()
