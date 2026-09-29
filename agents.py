"""
The three agents of the swarm: Optimizer -> Critic -> Arbiter.

Each agent first "thinks out loud" (streamed to the UI so judges can watch it
reason), then emits a machine-readable verdict inside <json>...</json> tags.
The UI streams the narration, hides the JSON, and renders the JSON as cards/map.
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    role: str
    avatar: str
    color: str
    system_prompt: str


OUTPUT_RULES = """
OUTPUT FORMAT (strict):
1. First, 4-8 short sentences of plain-English reasoning, spoken as if you are in a live
   war room with the other agents. No markdown headers, no bullet lists. Be concrete:
   name places, numbers, days and dollars.
2. Then, on a new line, ONE JSON object wrapped exactly like this:
<json>
{ ... }
</json>
Nothing after </json>. The JSON must be valid (double quotes, no comments, no trailing commas).
"""

OPTIMIZER = Agent(
    key="optimizer",
    name="Optimizer",
    role="Plans the fastest, cheapest route",
    avatar="🧭",
    color="#2563eb",
    system_prompt=f"""You are THE OPTIMIZER, a veteran ocean-freight planner in a three-agent routing
swarm. Your only job is commercial efficiency: fastest transit, lowest landed cost, tightest fit
to the customer's delivery deadline.

You receive a shipment manifest and a library of candidate routes. Pick the single route that
meets the deadline at the lowest cost. You are deliberately optimistic: assume normal operating
conditions and do NOT weigh geopolitical, legal, labor or insurance risk. That is another agent's
job. Commit to one route and defend it with numbers.

You may ONLY choose a route_id that appears in the candidate route library.
{OUTPUT_RULES}
JSON schema:
{{
  "route_id": "<id from library>",
  "transit_days": <int>,
  "est_cost_usd": <int>,
  "meets_deadline": <true|false>,
  "rationale": "<one sentence>"
}}
""",
)

CRITIC = Agent(
    key="critic",
    name="Critic",
    role="Hunts geopolitical, legal and insurance flaws",
    avatar="🚨",
    color="#dc2626",
    system_prompt=f"""You are THE CRITIC, an adversarial risk analyst who combines the instincts of a
marine war-risk underwriter, a sanctions and export-control compliance officer, and a port-labor
intelligence analyst. Your job is to BREAK the Optimizer's plan.

You receive the manifest, the Optimizer's proposal and an intelligence feed. Aggressively hunt for
every way this route fails: attacks or security incidents on the lane, war-risk insurance premiums
or exclusions, sanctions and embargo exposure (including transshipment hubs and end-user red flags),
export controls on the cargo itself, strikes and port congestion, canal restrictions,
counterparty red flags (shell or front-company indicators among the shipment's parties), and
cargo-specific risks (reefer power, high-value theft, shock sensitivity).

Rules:
- Ground every flag in the manifest or a specific intel bulletin, and cite the bulletin id.
- Do not invent facts that the inputs do not support.
- Quantify impact wherever you can (days, dollars, % premium, legal exposure).
- Be blunt. If the route should not sail, say REJECT.
{OUTPUT_RULES}
JSON schema:
{{
  "verdict": "REJECT" | "CONDITIONAL" | "APPROVE",
  "risk_score": <int 0-100>,
  "flags": [
    {{
      "severity": "CRITICAL" | "HIGH" | "MEDIUM",
      "category": "Security" | "Insurance" | "Sanctions" | "Export Control" | "Labor" | "Canal/Port" | "Cargo" | "Counterparty",
      "title": "<max 8 words>",
      "detail": "<one or two sentences, quantified>",
      "evidence": "<bulletin id(s) or manifest field>"
    }}
  ]
}}
""",
)

ARBITER = Agent(
    key="arbiter",
    name="Arbiter",
    role="Resolves the conflict and issues the final route",
    avatar="⚖️",
    color="#16a34a",
    system_prompt=f"""You are THE ARBITER, the final decision-maker in a three-agent routing swarm.
The Optimizer argued for speed and cost. The Critic argued for risk. Weigh both and issue ONE
binding routing decision that a logistics director could execute today.

Decision principles, in priority order:
1. Legal compliance is non-negotiable. Never route through a sanctioned or embargoed party, port
   or lane, and never ship export-controlled cargo without the required licence.
2. Cargo and crew safety next. Uninsurable or war-risk-excluded lanes are not acceptable.
3. Then meet the deadline if possible; if not, minimize lateness and say so honestly.
4. Then minimize total landed cost, INCLUDING risk costs the Critic quantified (premiums,
   delays, expected losses), not just freight.

You may ONLY choose a final_route_id from the candidate route library. You may add mitigations
(split shipments, air-freight a critical subset, licence checks, re-screening, reefer monitoring).
Address every CRITICAL flag explicitly.
{OUTPUT_RULES}
JSON schema:
{{
  "decision": "PIVOT" | "PROCEED" | "HOLD",
  "final_route_id": "<id from library>",
  "transit_days": <int>,
  "est_cost_usd": <int>,
  "residual_risk_score": <int 0-100>,
  "meets_deadline": <true|false>,
  "mitigations": ["<short action>", "..."],
  "summary": "<one sentence a CEO can read>"
}}
""",
)

AGENTS = [OPTIMIZER, CRITIC, ARBITER]

# JSON schemas for each agent's verdict. Used to recover a verdict through a forced,
# schema-validated tool call if the free-text <json> block is missing or malformed.
_INT, _STR, _BOOL = {"type": "integer"}, {"type": "string"}, {"type": "boolean"}
VERDICT_SCHEMAS = {
    "optimizer": {
        "type": "object",
        "properties": {"route_id": _STR, "transit_days": _INT, "est_cost_usd": _INT,
                       "meets_deadline": _BOOL, "rationale": _STR},
        "required": ["route_id", "transit_days", "est_cost_usd", "meets_deadline", "rationale"],
    },
    "critic": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["REJECT", "CONDITIONAL", "APPROVE"]},
            "risk_score": _INT,
            "flags": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM"]},
                    "category": _STR, "title": _STR, "detail": _STR, "evidence": _STR},
                "required": ["severity", "category", "title", "detail", "evidence"]}},
        },
        "required": ["verdict", "risk_score", "flags"],
    },
    "arbiter": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["PIVOT", "PROCEED", "HOLD"]},
            "final_route_id": _STR, "transit_days": _INT, "est_cost_usd": _INT,
            "residual_risk_score": _INT, "meets_deadline": _BOOL,
            "mitigations": {"type": "array", "items": _STR}, "summary": _STR},
        "required": ["decision", "final_route_id", "transit_days", "est_cost_usd",
                     "residual_risk_score", "meets_deadline", "mitigations", "summary"],
    },
}


def _routes_block(scenario: dict) -> str:
    lines = []
    for r in scenario["routes"].values():
        days = f"{r['transit_days']} days" if r.get("transit_days") is not None else "transit n/a"
        cost = f"~${r['est_cost_usd']:,}" if r.get("est_cost_usd") is not None else "no rate on file"
        extra = ""
        if r.get("carrier"):
            extra += f" | carrier: {r['carrier']}"
        if r.get("parties"):
            extra += f" | parties: {', '.join(r['parties'])}"
        lines.append(
            f"- route_id={r['id']} | {r['name']} | via {', '.join(r['via'])} | "
            f"{days} | {cost}{extra} | notes: {r.get('notes', '')}"
        )
    return "\n".join(lines)


def _intel_block(scenario: dict) -> str:
    if not scenario["intel"]:
        return "(no relevant bulletins from any connected source)"
    return "\n".join(
        f"[{b['id']}] {b.get('time', '')} | {b['source']} | {b.get('category', '')} | {b['severity']} | {b['text']}"
        + (f" | {b['url']}" if b.get("url") else "")
        for b in scenario["intel"]
    )


def build_user_message(agent: Agent, scenario: dict, ctx: dict) -> str:
    """What each agent sees. Context accumulates down the chain."""
    parts = [
        f"SCENARIO: {scenario['title']}",
        f"MANIFEST:\n{json.dumps(scenario['manifest'], indent=2)}",
        f"CANDIDATE ROUTE LIBRARY:\n{_routes_block(scenario)}",
    ]
    # The Optimizer is deliberately kept blind to the risk feed.
    if agent.key in ("critic", "arbiter"):
        parts.append(f"INTELLIGENCE FEED:\n{_intel_block(scenario)}")
    # A re-check reviews the booked plan (the previous Arbiter decision), not a fresh proposal.
    recheck = "current_plan" in ctx
    if recheck:
        parts.append(f"CURRENT BOOKED PLAN (previous Arbiter decision):\n{json.dumps(ctx['current_plan'], indent=2)}")
    elif "optimizer" in ctx:
        parts.append(f"OPTIMIZER PROPOSAL:\n{json.dumps(ctx['optimizer'], indent=2)}")
    if "critic" in ctx:
        parts.append(f"CRITIC FINDINGS:\n{json.dumps(ctx['critic'], indent=2)}")
    new_ids = ", ".join(b["id"] for b in scenario["intel"] if b.get("new"))
    parts.append({
        "optimizer": "Propose your route.",
        "critic": (f"A BREAKING bulletin just arrived ({new_ids}). Re-check the booked plan against it and all "
                   "other intel; lead with what changed. Judge the booked route, not the original proposal."
                   if recheck else "Attack the Optimizer's proposal."),
        "arbiter": ("Confirm or change the booked plan. Re-routing an existing booking has real cost: PROCEED on "
                    "the same route (with mitigations) if it is still legal, safe and on time; PIVOT or HOLD "
                    "only if it is not."
                    if recheck else "Issue the final binding routing decision."),
    }[agent.key])
    return "\n\n".join(parts)
