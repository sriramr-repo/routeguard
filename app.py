"""
RouteGuard - live Streamlit view of the three-agent routing swarm.

    streamlit run app.py
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import time

import plotly.graph_objects as go
import streamlit as st

from agents import AGENTS
from pipeline import (ClaudeBackend, make_live_backend, ReplayBackend, make_breaking_bulletin, recheck_scenario,
                      run_recheck, run_swarm)
from scenarios import SCENARIOS
from sources import build_scenario, load_manifest

SOURCES_CONFIG = os.environ.get("ROUTEGUARD_SOURCES", "config/sources.toml")
SAMPLE_MANIFESTS = {
    "Sample: CNC machines, Hamburg → Tashkent": "examples/manifests/cnc_tashkent.json",
    "Sample: EV batteries, Shanghai → Rotterdam": "examples/manifests/batteries_rotterdam.csv",
    "Sample: EV batteries with real forwarders (Similarweb)": "examples/manifests/batteries_real_parties.json",
}

st.set_page_config(page_title="RouteGuard", page_icon="🛰️", layout="wide")

AGENT_BY_KEY = {a.key: a for a in AGENTS}
SEV_COLOR = {"CRITICAL": "#ef4444", "HIGH": "#f97316", "MEDIUM": "#eab308"}

# ------------------------------------------------------------------ styles
st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1500px;}
h1.rg-title {font-size: 2.1rem; margin: 0; letter-spacing: -0.02em;}
.rg-sub {color: #94a3b8; margin: 0.15rem 0 1rem 0;}
.rg-pill {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.72rem;
          font-weight:600; letter-spacing:0.04em; border:1px solid #334155; color:#cbd5e1; margin-right:6px;}
.rg-manifest {display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin-bottom: 0.8rem;}
.rg-m {background:#111a2e; border:1px solid #1e293b; border-radius:12px; padding:10px 14px;}
.rg-m .k {color:#94a3b8; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em;}
.rg-m .v {font-size:1.05rem; font-weight:600; margin-top:2px;}
.rg-agent {background:#0f172a; border:1px solid #1e293b; border-left:5px solid var(--c);
           border-radius:12px; padding:12px 16px; margin-bottom:12px; transition: all .3s;}
.rg-agent.idle {opacity:0.45;}
.rg-agent.alert {border-color:#ef4444; box-shadow:0 0 0 1px #ef4444, 0 0 28px rgba(239,68,68,.45);
                 animation: rgpulse 1.1s ease-in-out infinite; background:#1a0b0e;}
.rg-agent.resolved {box-shadow:0 0 0 1px #22c55e, 0 0 22px rgba(34,197,94,.3);}
@keyframes rgpulse {0%,100% {box-shadow:0 0 0 1px #ef4444, 0 0 12px rgba(239,68,68,.35);}
                    50% {box-shadow:0 0 0 2px #ef4444, 0 0 36px rgba(239,68,68,.7);}}
.rg-head {display:flex; align-items:center; gap:10px;}
.rg-head .av {font-size:1.4rem;}
.rg-head .nm {font-weight:700; font-size:1.02rem;}
.rg-head .rl {color:#94a3b8; font-size:0.8rem;}
.rg-head .st {margin-left:auto; font-size:0.72rem; font-weight:700; letter-spacing:0.06em;}
.rg-text {margin-top:8px; line-height:1.55; color:#e2e8f0; font-size:0.95rem;}
.rg-cursor {display:inline-block; width:8px; background:var(--c); animation: blink 1s steps(1) infinite; margin-left:2px;}
@keyframes blink {50% {opacity:0;}}
.rg-card {margin-top:10px; background:#111a2e; border-radius:10px; padding:10px 12px; font-size:0.88rem;}
.rg-flag {border-left:4px solid var(--s); background:#1c0f14; border-radius:8px; padding:8px 12px; margin-top:8px;
          animation: slidein .35s ease-out both;}
.rg-flag .t {font-weight:700;} .rg-flag .d {color:#cbd5e1; font-size:0.86rem; margin-top:2px;}
.rg-flag .e {color:#94a3b8; font-size:0.74rem; margin-top:3px;}
@keyframes slidein {from {opacity:0; transform:translateX(-12px);} to {opacity:1; transform:none;}}
.rg-banner {border-radius:12px; padding:14px 18px; font-weight:700; font-size:1.05rem; margin-bottom:12px;}
.rg-banner.red {background:linear-gradient(90deg,#7f1d1d,#450a0a); border:1px solid #ef4444;
                animation: rgpulse 1.1s ease-in-out infinite;}
.rg-banner.green {background:linear-gradient(90deg,#14532d,#052e16); border:1px solid #22c55e;}
.rg-banner.blue {background:linear-gradient(90deg,#1e3a8a,#0b1a3d); border:1px solid #3b82f6;}
.rg-kpis {display:grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap:10px; margin-top:6px;}
.rg-kpi {background:#111a2e; border:1px solid #1e293b; border-radius:12px; padding:10px 12px;}
.rg-kpi .k {color:#94a3b8; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em;}
.rg-kpi .v {font-size:1.35rem; font-weight:700;}
.rg-kpi .d {font-size:0.78rem; color:#94a3b8;}
.rg-intel {font-size:0.84rem; padding:6px 0; border-bottom:1px solid #1e293b;}
.rg-banner.amber {background:linear-gradient(90deg,#78350f,#3b1a06); border:1px solid #f59e0b;}
.rg-new {display:inline-block; padding:0 7px; border-radius:999px; font-size:0.66rem; font-weight:800;
         letter-spacing:0.06em; background:#f59e0b; color:#1c1206; margin-right:6px; vertical-align:1px;}
.rg-diff {background:#111a2e; border:1px solid #1e293b; border-radius:12px; padding:10px 14px; margin-top:6px;}
.rg-diff .h {font-weight:700; margin-bottom:6px;}
.rg-diff table {width:100%; border-collapse:collapse; font-size:0.9rem;}
.rg-diff td {padding:4px 6px; border-top:1px solid #1e293b;}
.rg-diff td.k {color:#94a3b8; font-size:0.74rem; text-transform:uppercase; letter-spacing:0.06em;}
.rg-diff td.ch {font-weight:700;}
@media (max-width: 900px) {.rg-manifest, .rg-kpis {grid-template-columns: repeat(2, minmax(0,1fr));}}
</style>
""", unsafe_allow_html=True)


try:
    for _k, _v in st.secrets.items():
        # connector keys (e.g. TRADE_GOV_API_KEY) go to env; the Anthropic key never does
        if isinstance(_v, str) and not any(s in _k.lower() for s in ("anthropic", "crusoe")) and not _v.strip().startswith("sk-ant-"):
            os.environ.setdefault(_k, _v)
except Exception:
    pass


@st.cache_data(ttl=900, show_spinner="Ingesting connected sources…")
def ingest(manifest_text: str, filename: str, config_path: str, config_mtime: float,
           key_fingerprint: str, _secrets: dict):
    # _secrets is not hashed (leading underscore); key_fingerprint keys the cache per key instead
    manifest = load_manifest(manifest_text, filename)
    return build_scenario(manifest, config_path, secrets=_secrets)


# ------------------------------------------------------------------ helpers
def safe(s: str) -> str:
    """Streamlit markdown renders $...$ as LaTeX; entity-encode dollars so prices stay text."""
    return s.replace("$", "&#36;")


def money(v) -> str:
    if not isinstance(v, (int, float)):
        return "n/a"
    return f"${v / 1_000_000:.1f}M" if v >= 1_000_000 else f"${v / 1000:,.0f}k"


def _secrets_present() -> bool:
    try:
        return len(st.secrets) > 0
    except Exception:
        return False


def owner_passcode() -> str | None:
    try:
        if "ROUTEGUARD_PASSCODE" in st.secrets:
            return str(st.secrets["ROUTEGUARD_PASSCODE"])
    except Exception:
        pass
    return os.environ.get("ROUTEGUARD_PASSCODE")


PROVIDERS = {
    "claude": {"label": "Anthropic API key", "env": "ANTHROPIC_API_KEY", "word": "anthropic", "prefix": "sk-ant-",
               "model_env": "ROUTEGUARD_MODEL", "default_model": "claude-sonnet-5-5"},
    "crusoe": {"label": "Crusoe API key", "env": "CRUSOE_API_KEY", "word": "crusoe", "prefix": None,
               "model_env": "CRUSOE_MODEL", "default_model": "meta-llama/Llama-3.3-70B-Instruct"},
}


def get_api_key(provider: str = "claude") -> str | None:
    """Server-side Anthropic key from Streamlit secrets (any casing, top level or inside a section)
    or the environment. Never displayed or logged. Callers must gate it (see sidebar)."""
    spec = PROVIDERS[provider]
    prefix, word, env = spec["prefix"], spec["word"], spec["env"]

    def clean(v: str) -> str:
        return v.strip().strip('"').strip("'").strip()

    def scan(d, path="") -> tuple[str, str] | None:
        try:
            items = list(d.items())
        except Exception:
            return None
        for k, v in items:
            if prefix and isinstance(v, str) and clean(v).startswith(prefix):
                return clean(v), f"{path}{k}"
        for k, v in items:
            if isinstance(v, str) and word in k.lower() and "key" in k.lower():
                return clean(v), f"{path}{k}"
        for k, v in items:
            if not isinstance(v, str):
                found = scan(v, f"{path}{k}.")
                if found:
                    return found
        return None

    found = None
    try:
        found = scan(st.secrets)
    except Exception:
        pass
    if not found and os.environ.get(env):
        found = (clean(os.environ[env]), f"env {env}")
    if not found:
        st.session_state["key_diag"] = "no key in secrets or environment"
        return None
    key, where = found
    # safe diagnostic: field name, length, prefix check. Never the key itself.
    shape = "" if not prefix else (f", starts with {prefix}" if key.startswith(prefix) else f", does NOT start with {prefix}")
    st.session_state["key_diag"] = f"key from '{where}', {len(key)} chars{shape}"
    return key


def agent_panel(key: str, narration: str, data: dict | None, status: str, scenario: dict) -> str:
    """status: idle | thinking | done | alert | resolved"""
    a = AGENT_BY_KEY[key]
    label = {"idle": ("WAITING", "#64748b"), "thinking": ("THINKING…", a.color),
             "done": ("DONE", a.color), "alert": ("⚠ THREAT DETECTED", "#ef4444"),
             "resolved": ("✓ DECISION ISSUED", "#22c55e")}[status]
    cls = {"idle": "idle", "alert": "alert", "resolved": "resolved"}.get(status, "")
    body = html.escape(narration).replace("\n", "<br>")
    if status == "thinking":
        body += '<span class="rg-cursor">&nbsp;</span>'
    card = ""
    if data:
        card = result_card(key, data, scenario)
    return f"""
<div class="rg-agent {cls}" style="--c:{a.color}">
  <div class="rg-head"><span class="av">{a.avatar}</span>
    <div><div class="nm" style="color:{a.color}">{a.name}</div><div class="rl">{a.role}</div></div>
    <span class="st" style="color:{label[1]}">{label[0]}</span></div>
  <div class="rg-text">{body}</div>{card}
</div>"""


def result_card(key: str, d: dict, scenario: dict) -> str:
    routes = scenario["routes"]
    if key == "optimizer":
        r = routes.get(d.get("route_id"), {})
        return (f'<div class="rg-card">📍 <b>Proposed:</b> {html.escape(r.get("name", d.get("route_id", "?")))}'
                f' &nbsp;·&nbsp; {d.get("transit_days")} days &nbsp;·&nbsp; {money(d.get("est_cost_usd", 0))}'
                f' &nbsp;·&nbsp; deadline {"✅" if d.get("meets_deadline") else "❌"}</div>')
    if key == "critic":
        new_ids = [b["id"] for b in scenario["intel"] if b.get("new")]
        flags = "".join(
            f'<div class="rg-flag" style="--s:{SEV_COLOR.get(f.get("severity"), "#ef4444")};animation-delay:{i * 0.12:.2f}s">'
            f'<div class="t">{"<span class=rg-new>NEW</span>" if any(i in f.get("evidence", "") for i in new_ids) else ""}'
            f'<span style="color:{SEV_COLOR.get(f.get("severity"), "#ef4444")}">{html.escape(f.get("severity", ""))}</span>'
            f' · {html.escape(f.get("category", ""))} · {html.escape(f.get("title", ""))}</div>'
            f'<div class="d">{html.escape(f.get("detail", ""))}</div>'
            f'<div class="e">Evidence: {html.escape(f.get("evidence", ""))}</div></div>'
            for i, f in enumerate(d.get("flags", []))
        )
        return (f'<div class="rg-card" style="background:#1a0b0e">🛑 <b>Verdict: {html.escape(d.get("verdict", ""))}</b>'
                f' &nbsp;·&nbsp; risk score <b style="color:#ef4444">{d.get("risk_score")}/100</b></div>{flags}')
    if key == "arbiter":
        r = routes.get(d.get("final_route_id"), {})
        mit = "".join(f"<li>{html.escape(m)}</li>" for m in d.get("mitigations", []))
        return (f'<div class="rg-card" style="background:#0b1f14">✅ <b>{html.escape(d.get("decision", ""))} →'
                f' {html.escape(r.get("name", d.get("final_route_id", "?")))}</b><ul style="margin:6px 0 0 0">{mit}</ul></div>')
    return ""


def booked_panel(plan: dict, scenario: dict) -> str:
    """Stands in for the Optimizer during a re-check: the plan currently booked."""
    r = scenario["routes"].get(plan.get("final_route_id"), {})
    return f"""
<div class="rg-agent" style="--c:#f59e0b">
  <div class="rg-head"><span class="av">📌</span>
    <div><div class="nm" style="color:#f59e0b">Booked plan</div><div class="rl">The previous Arbiter decision, now under review</div></div>
    <span class="st" style="color:#f59e0b">RE-CHECKING</span></div>
  <div class="rg-card">📍 <b>{html.escape(r.get("name", plan.get("final_route_id", "?")))}</b>
    &nbsp;·&nbsp; {plan.get("transit_days")} days &nbsp;·&nbsp; {money(plan.get("est_cost_usd"))}
    &nbsp;·&nbsp; risk {plan.get("residual_risk_score")}</div>
</div>"""


def diff_card(before: dict, after: dict, bulletin: dict, n: int, scenario: dict) -> str:
    """Side-by-side of the booked plan and the re-checked decision."""
    routes = scenario["routes"]

    def name(d):
        return routes.get(d.get("final_route_id"), {}).get("name", d.get("final_route_id", "?"))

    def delta(b, a, fmt, lower_is_better=True):
        if not isinstance(b, (int, float)) or not isinstance(a, (int, float)) or a == b:
            return ""
        good = (a < b) == lower_is_better
        return (f' <span style="color:{"#22c55e" if good else "#ef4444"}">'
                f'({"+" if a > b else "-"}{fmt(abs(a - b))})</span>')

    rows = [
        ("Route", html.escape(name(before)), html.escape(name(after)), ""),
        ("Transit", f"{before.get('transit_days')} d", f"{after.get('transit_days')} d",
         delta(before.get("transit_days"), after.get("transit_days"), lambda v: f"{v} d")),
        ("Cost", money(before.get("est_cost_usd")), money(after.get("est_cost_usd")),
         delta(before.get("est_cost_usd"), after.get("est_cost_usd"), money)),
        ("Risk", str(before.get("residual_risk_score")), str(after.get("residual_risk_score")),
         delta(before.get("residual_risk_score"), after.get("residual_risk_score"), str)),
        ("Deadline", "met ✅" if before.get("meets_deadline") else "missed ❌",
         "met ✅" if after.get("meets_deadline") else "missed ❌", ""),
    ]
    body = "".join(
        f'<tr><td class="k">{k}</td><td>{b}</td><td>→</td>'
        f'<td class="{"ch" if b != a else ""}">{a}{d}</td></tr>' for k, b, a, d in rows)
    return (f'<div class="rg-diff"><div class="h">⚡ Update #{n} · {html.escape(bulletin["text"][:90])}'
            f'{"…" if len(bulletin["text"]) > 90 else ""} ({html.escape(bulletin["id"])})</div>'
            f'<table><tr><td></td><td class="k">Before</td><td></td><td class="k">After</td></tr>{body}</table></div>')


def build_map(scenario: dict, stage: int, ctx: dict) -> go.Figure:
    """stage 0: nothing, 1: optimizer route, 2: critic hotspots (route red), 3: arbiter route."""
    fig = go.Figure()
    # an invisible geo trace so the world map renders even before any route exists
    fig.add_trace(go.Scattergeo(lat=[0], lon=[0], mode="markers", marker=dict(size=0, opacity=0),
                                showlegend=False, hoverinfo="skip"))
    routes = scenario["routes"]

    shown: set[str] = set()

    def draw(route_id: str, color: str, width: float, opacity: float, name: str, dash: str | None = None):
        r = routes.get(route_id)
        if not r:
            return
        for i, leg in enumerate(r["legs"]):
            first = i == 0 and name not in shown
            shown.add(name)
            lats, lons = zip(*leg["pts"])
            style = dash or {"sea": "solid", "land": "dash", "air": "dot"}[leg["mode"]]
            fig.add_trace(go.Scattergeo(
                lat=lats, lon=lons, mode="lines", line=dict(width=width, color=color, dash=style),
                opacity=opacity, name=name, showlegend=first, legendgroup=name, hoverinfo="name"))
        first, last = r["legs"][0]["pts"][0], r["legs"][-1]["pts"][-1]
        fig.add_trace(go.Scattergeo(
            lat=[first[0], last[0]], lon=[first[1], last[1]], mode="markers+text",
            marker=dict(size=9, color=color, line=dict(width=1, color="white")),
            text=[r["via"][0], r["via"][-1]], textposition="top center",
            textfont=dict(color="#e2e8f0", size=11), showlegend=False, hoverinfo="skip", opacity=opacity))

    opt = ctx.get("optimizer", {}).get("route_id")
    plan = ctx.get("current_plan")
    if plan:  # re-check after breaking news: booked route, the new hotspot, then the decision
        booked, final = plan.get("final_route_id"), ctx.get("arbiter", {}).get("final_route_id")
        if stage >= 3 and final:
            if final != booked:
                draw(booked, "#94a3b8", 2.0, 0.5, "Previous plan", dash="dash")
            draw(final, "#22c55e", 4.5, 1.0, "Confirmed route" if final == booked else "New route")
        else:
            rejected = ctx.get("critic", {}).get("verdict") == "REJECT"
            draw(booked, "#ef4444" if rejected else "#f59e0b", 3.5, 1.0, "Booked route")
        old = [h for h in scenario["hotspots"] if not h.get("new")]
        if old:
            fig.add_trace(go.Scattergeo(
                lat=[h["lat"] for h in old], lon=[h["lon"] for h in old], mode="markers",
                marker=dict(size=10, color="#ef4444", symbol="x", opacity=0.6, line=dict(width=1, color="white")),
                text=[f"⚠ {h['label']}" for h in old], name="Earlier risks", hoverinfo="text"))
        new = [h for h in scenario["hotspots"] if h.get("new")]
        if new:
            fig.add_trace(go.Scattergeo(
                lat=[h["lat"] for h in new], lon=[h["lon"] for h in new], mode="markers",
                marker=dict(size=46, color="rgba(245,158,11,0.3)"), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scattergeo(
                lat=[h["lat"] for h in new], lon=[h["lon"] for h in new], mode="markers+text",
                marker=dict(size=16, color="#f59e0b", symbol="star", line=dict(width=1, color="white")),
                text=[f"⚡ BREAKING: {h['label']}" for h in new],
                textposition=[h.get("pos", "bottom right") for h in new],
                textfont=dict(color="#fcd34d", size=13), name="Breaking news", hoverinfo="text"))
    elif stage == 0 and scenario.get("live_data"):
        for rid in routes:
            draw(rid, "#64748b", 2.0, 0.8, "Candidate routes")
        hs = scenario["hotspots"]
        if hs:
            fig.add_trace(go.Scattergeo(
                lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers",
                marker=dict(size=11, color="#f59e0b", line=dict(width=1, color="white")),
                text=[h["label"] for h in hs], name="Intel on these lanes", hoverinfo="text"))
    if stage == 1 and opt and not plan:
        draw(opt, "#3b82f6", 3.5, 1.0, "Optimizer proposal")
    if stage >= 2 and opt and not plan:
        draw(opt, "#ef4444", 3.5 if stage == 2 else 2.0, 1.0 if stage == 2 else 0.35,
             "Rejected by Critic" if stage == 2 else "Rejected route")
        hs = scenario["hotspots"]
        fig.add_trace(go.Scattergeo(
            lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers",
            marker=dict(size=38, color="rgba(239,68,68,0.25)"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scattergeo(
            lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs],
            mode="markers+text" if len(hs) <= 4 else "markers",  # many hotspots: labels on hover
            marker=dict(size=13, color="#ef4444", symbol="x", line=dict(width=1, color="white")),
            text=[f"⚠ {h['label']}" for h in hs], textposition=[h.get("pos", "bottom right") for h in hs],
            textfont=dict(color="#fca5a5", size=12), name="Risk hotspots", hoverinfo="text"))
    if stage >= 3 and not plan:
        final = ctx.get("arbiter", {}).get("final_route_id")
        if final:
            draw(final, "#22c55e", 4.5, 1.0, "Arbiter final route")

    c = scenario["map_center"]
    fig.update_geos(
        projection_type="natural earth", projection_scale=c["scale"], center=dict(lat=c["lat"], lon=c["lon"]),
        showland=True, landcolor="#1e293b", showocean=True, oceancolor="#0b1220",
        showcountries=True, countrycolor="#334155", coastlinecolor="#475569", showlakes=False,
        bgcolor="rgba(0,0,0,0)", showframe=False)
    fig.update_layout(
        height=470, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.02, x=0, font=dict(color="#cbd5e1"), bgcolor="rgba(0,0,0,0)"),
        uirevision="keep")
    return fig


def banner(stage: int, ctx: dict, breaking: dict | None = None) -> str:
    if stage == 0:
        return ""
    if "current_plan" in ctx:
        return recheck_banner(ctx, breaking or {})
    if stage == 1:
        return '<div class="rg-banner blue">🧭 Optimizer is planning the fastest route…</div>'
    if stage == 2:
        c = ctx.get("critic")
        if not c:
            return '<div class="rg-banner blue">🧭 Proposal ready. Critic is attacking it…</div>'
        n = sum(1 for f in c.get("flags", []) if f.get("severity") == "CRITICAL")
        return (f'<div class="rg-banner red">🚨 {c.get("verdict")}: {n} critical threat(s) on the proposed route.'
                f' Risk score {c.get("risk_score")}/100</div>')
    a = ctx.get("arbiter")
    if not a:
        return '<div class="rg-banner red">⚖️ Arbiter is resolving the conflict…</div>'
    return f'<div class="rg-banner green">⚖️ {html.escape(a.get("summary", ""))}</div>'


def recheck_banner(ctx: dict, breaking: dict) -> str:
    c, a, plan = ctx.get("critic"), ctx.get("arbiter"), ctx["current_plan"]
    news = html.escape(breaking.get("text", ""))
    if not c:
        return f'<div class="rg-banner red">⚡ BREAKING: {news}<br><small>Critic is re-checking the booked plan…</small></div>'
    if not a:
        n = sum(1 for f in c.get("flags", []) if breaking.get("id", "?") in f.get("evidence", ""))
        return (f'<div class="rg-banner red">⚡ {html.escape(c.get("verdict", ""))}: {n} new flag(s) from '
                f'{html.escape(breaking.get("id", ""))} · risk {c.get("risk_score")}/100<br>'
                f'<small>Arbiter is deciding whether to hold course…</small></div>')
    summary = html.escape(a.get("summary", ""))
    if a.get("decision") == "PROCEED":
        return f'<div class="rg-banner green">🟢 HOLDING COURSE · {summary}</div>'
    if a.get("decision") == "PIVOT":
        return (f'<div class="rg-banner amber">🟠 RE-ROUTED · {html.escape(str(plan.get("final_route_id")))} → '
                f'{html.escape(str(a.get("final_route_id")))} · {summary}</div>')
    return f'<div class="rg-banner red">🔴 ON HOLD · {summary}</div>'


def kpis(ctx: dict, scenario: dict) -> str:
    o, c, a = ctx.get("optimizer"), ctx.get("critic"), ctx.get("arbiter")
    if not (o and c and a):
        return ""
    dl = scenario["manifest"]["deadline_days"]
    ddays = a["transit_days"] - o["transit_days"]
    return f"""
<div class="rg-kpis">
 <div class="rg-kpi"><div class="k">Final transit</div><div class="v">{a['transit_days']} days</div>
   <div class="d">{'+' if ddays >= 0 else ''}{ddays} vs naive plan · deadline {dl}d</div></div>
 <div class="rg-kpi"><div class="k">All-in cost</div><div class="v">{money(a['est_cost_usd'])}</div>
   <div class="d">naive quote {money(o['est_cost_usd'])}</div></div>
 <div class="rg-kpi"><div class="k">Risk score</div><div class="v" style="color:#22c55e">{a['residual_risk_score']}</div>
   <div class="d">down from <span style="color:#ef4444">{c['risk_score']}</span></div></div>
 <div class="rg-kpi"><div class="k">Cargo protected</div><div class="v">{money(scenario['manifest']['declared_value_usd'])}</div>
   <div class="d">deadline {'met ✅' if a.get('meets_deadline') else 'missed ❌'}</div></div>
</div>"""


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🛰️ RouteGuard")
    st.caption("Adversarial three-agent routing swarm")
    data_mode = st.radio("Data", ["Curated demo scenarios", "Connected sources (your shipment)"],
                         help="Connected mode loads a shipper manifest and pulls intel from the sources "
                              f"configured in {SOURCES_CONFIG}.")
    connected = data_mode.startswith("Connected")
    api_key = None
    if not connected:
        scen_key = st.radio("Scenario", list(SCENARIOS), format_func=lambda k: SCENARIOS[k]["title"], key="scenario")
        engine = st.radio(
            "Engine", ["Replay (offline, demo-safe)", "Live (Claude API)", "Live (Crusoe, open models)"],
            help="Replay streams pre-recorded agent output: identical every run, no network. "
                 "Live calls Claude, or open-weight models on Crusoe, with the same prompts; "
                 "if a call fails it falls back to replay.")
    else:
        up = st.file_uploader("Shipper manifest (JSON or CSV)", type=["json", "csv"])
        sample = st.selectbox("…or use a sample manifest", list(SAMPLE_MANIFESTS), disabled=up is not None)
        engine = st.radio("Engine", ["Live (Claude API)", "Live (Crusoe, open models)"],
                          help="Connected-data runs always use a live model.")
        sw_key = st.text_input("Similarweb API key (optional)", type="password", value="",
                               placeholder="paste to vet party websites (session only)",
                               help="Checks the web footprint of each party website in the manifest. "
                                    "Kept only in your session, never stored.").strip().strip('"').strip("'")
    provider = "crusoe" if "Crusoe" in engine else "claude"
    spec = PROVIDERS[provider]
    server_key = get_api_key(provider) if engine.startswith("Live") else None
    if engine.startswith("Live"):
        typed = st.text_input(spec["label"], type="password", value="", key=f"key_{provider}",
                              placeholder="paste your key (kept only in your session)")
        # A server-side key (Secrets / env) is private to the owner: it is only used after the
        # owner passcode is entered. On a hosted app with no passcode configured it is never used.
        unlocked = False
        if server_key and not typed:
            code = owner_passcode()
            if code:
                entered = st.text_input("Owner passcode", type="password",
                                        help="Unlocks the owner's saved API key for this session only.")
                unlocked = bool(entered) and hmac.compare_digest(entered.encode(), code.encode())
                if entered and not unlocked:
                    st.error("Wrong passcode.")
            elif not _secrets_present():
                unlocked = True  # running locally with an env var: the machine owner is the user
            else:
                st.caption("A saved key exists but is locked: set ROUTEGUARD_PASSCODE in Secrets to use it.")
        api_key = typed or (server_key if unlocked else None)
        model = st.text_input("Model", value=os.environ.get(spec["model_env"], spec["default_model"]),
                              key=f"model_{provider}")
        if unlocked and st.session_state.get("key_diag"):
            st.caption(f"🔑 owner key unlocked · {st.session_state['key_diag']}")
        elif typed:
            st.caption("🔑 using the key you pasted (this session only, never stored)")
        if not api_key:
            st.warning("No API key for this session." + ("" if connected else " Live runs will fall back to replay."))
    else:
        model = None
    speed = st.slider("Stream speed", 0.5, 4.0, 1.0, 0.25, help="Replay typing speed")
    st.divider()
    st.caption("Connected mode ships wired to SAMPLE source files; point config/sources.toml at live feeds."
               if connected else "Intel bulletins in demo scenarios are simulated. No live scraping.")

source_report: list[dict] = []
if connected:
    if up is not None:
        man_text, man_name = up.getvalue().decode("utf-8-sig"), up.name
    else:
        path = SAMPLE_MANIFESTS[sample]
        man_text, man_name = open(path, encoding="utf-8").read(), path
    try:
        cfg_mtime = os.path.getmtime(SOURCES_CONFIG)
        run_keys = {"SIMILARWEB_API_KEY": sw_key} if sw_key else {}
        fp = hashlib.sha256(sw_key.encode()).hexdigest()[:16] if sw_key else ""
        scenario, source_report = ingest(man_text, man_name, SOURCES_CONFIG, cfg_mtime, fp, run_keys)
    except Exception as exc:
        st.error(f"Could not build this shipment: {exc}")
        st.stop()
    scen_key = "live_" + str(abs(hash(man_text)) % 10**8)
else:
    scenario = SCENARIOS[scen_key]
m = scenario["manifest"]

# reset stored results when scenario changes
if st.session_state.get("last_scen") != scen_key:
    st.session_state["result"] = None
    st.session_state["history"] = []  # breaking-news re-checks on top of the result
    st.session_state["last_scen"] = scen_key
history: list[dict] = st.session_state.setdefault("history", [])
# the scenario as it stands after every injected bulletin so far
view_scen = history[-1]["scenario"] if history else scenario

# ------------------------------------------------------------------ header
st.markdown(safe('<h1 class="rg-title">🛰️ RouteGuard</h1>'
            '<p class="rg-sub">One agent plans. One hunts for geopolitical and legal flaws. '
            'One arbitrates. A safe, optimal route in seconds.</p>'), unsafe_allow_html=True)

st.markdown(safe(f"""
<div style="margin-bottom:8px"><span class="rg-pill">SHIPMENT {html.escape(str(m.get('shipment_id', '')))}</span>
<span class="rg-pill">{'CONNECTED SOURCES' if scenario.get('live_data') else html.escape(scenario['title'].upper())}</span></div>
<div class="rg-manifest">
 <div class="rg-m"><div class="k">Lane</div><div class="v">{html.escape(str(m['origin']))} → {html.escape(str(m['destination']))}</div></div>
 <div class="rg-m"><div class="k">Cargo</div><div class="v">{html.escape(str(m['cargo']))}</div></div>
 <div class="rg-m"><div class="k">Declared value</div><div class="v">{money(m['declared_value_usd'])}</div></div>
 <div class="rg-m"><div class="k">Deadline</div><div class="v">{html.escape(str(m.get('deadline_days', 'n/a')))} days · {html.escape(str(m.get('containers', 'n/a')))}</div></div>
</div>"""), unsafe_allow_html=True)

if source_report:
    ok = sum(1 for r in source_report if r["status"] == "ok")
    with st.expander(f"🔌 Connected sources: {ok}/{len(source_report)} OK · "
                     f"{len(scenario['routes'])} candidate routes · {len(scenario['intel'])} relevant bulletins"):
        st.dataframe(
            [{"Source": r["source"], "Type": r["kind"], "Status": r["status"], "Items": r["items"],
              "ms": r.get("ms")} for r in source_report],
            width="stretch", hide_index=True)
        st.caption(f"Config: {SOURCES_CONFIG}. Failing sources are skipped, never fatal.")

with st.expander("📡 Intelligence feed " + ("(from connected sources)" if scenario.get("live_data") else "(simulated)")
                 + " and full manifest"):
    c1, c2 = st.columns([3, 2])
    with c1:
        for b in view_scen["intel"]:
            st.markdown(safe(f'<div class="rg-intel">'
                + ('<span class="rg-new">BREAKING</span>' if b.get("time") == "BREAKING" else "")
                + f'<b style="color:{SEV_COLOR.get(b["severity"], "#94a3b8")}">'
                f'[{b["id"]}] {b["severity"]}</b> · {html.escape(str(b.get("time", "")))} · <i>{html.escape(b["source"])}</i><br>'
                f'{html.escape(b["text"])}'
                + (f' <a href="{html.escape(b["url"])}" target="_blank">source</a>' if b.get("url") else "")
                + '</div>'), unsafe_allow_html=True)
        if not scenario["intel"]:
            st.caption("No relevant bulletins for this shipment's routes.")
    with c2:
        st.json(m)

run = st.button("▶  Run the swarm", type="primary", width="stretch")

left, right = st.columns([11, 10], gap="large")
with left:
    st.markdown("#### 🗣️ War room")
    panel_ph = {a.key: st.empty() for a in AGENTS}
with right:
    st.markdown("#### 🗺️ Route")
    banner_ph = st.empty()
    map_ph = st.empty()
    kpi_ph = st.empty()
    news_box = st.container()


def render_static(result: dict | None):
    ctx = (result or {}).get("ctx", {})
    narr = (result or {}).get("narr", {})
    stage = 3 if "arbiter" in ctx else 0
    for a in AGENTS:
        status = "idle"
        if a.key in ctx:
            status = {"critic": "alert", "arbiter": "resolved"}.get(a.key, "done")
        text = narr.get(a.key, "") or ("Waiting for the swarm to start." if not result else "")
        panel_ph[a.key].markdown(safe(agent_panel(a.key, text, ctx.get(a.key), status, scenario)), unsafe_allow_html=True)
    banner_ph.markdown(safe(banner(stage, ctx)), unsafe_allow_html=True)
    map_ph.plotly_chart(build_map(scenario, stage, ctx), width="stretch",
                        config={"displayModeBar": False}, key=f"map_static_{scen_key}_{stage}")
    kpi_ph.markdown(safe(kpis(ctx, scenario)), unsafe_allow_html=True)


def render_recheck(entry: dict, n: int):
    """The latest breaking-news re-check: booked plan, Critic, Arbiter, map, what changed."""
    scen, ctx, narr = entry["scenario"], entry["ctx"], entry["narr"]
    panel_ph["optimizer"].markdown(safe(booked_panel(ctx["current_plan"], scen)), unsafe_allow_html=True)
    for key, status in (("critic", "alert"), ("arbiter", "resolved")):
        panel_ph[key].markdown(safe(agent_panel(key, narr.get(key, ""), ctx.get(key), status, scen)),
                               unsafe_allow_html=True)
    banner_ph.markdown(safe(banner(3, ctx, entry["bulletin"])), unsafe_allow_html=True)
    map_ph.plotly_chart(build_map(scen, 3, ctx), width="stretch",
                        config={"displayModeBar": False}, key=f"map_recheck_{scen_key}_{n}")
    kpi_ph.markdown(safe(diff_card(ctx["current_plan"], ctx["arbiter"], entry["bulletin"], n, scen)),
                    unsafe_allow_html=True)


def make_backend():
    """The engine picked in the sidebar; Live without a usable key falls back to replay."""
    replay = ReplayBackend(speed=speed)
    if engine.startswith("Live") and api_key:
        try:
            return make_live_backend(provider, model=model, api_key=api_key), replay
        except Exception as exc:
            st.toast(f"Live engine unavailable ({exc}); using replay.", icon="⚠️")
    return replay, replay


def stream_events(events, scen: dict, ctx: dict, breaking: dict | None = None) -> tuple[dict, dict, bool]:
    """Render a run as it streams. Returns (ctx, narrations, finished)."""
    narr: dict = {}
    run_id = str(time.time_ns())
    done = False

    def show_map(stage: int):
        map_ph.plotly_chart(build_map(scen, stage, ctx), width="stretch",
                            config={"displayModeBar": False}, key=f"map_{run_id}_{stage}_{len(ctx)}")

    show_map(2 if breaking else 0)
    buf = ""
    stage = 0

    def _guard(gen):
        try:
            yield from gen
        except Exception as exc:
            st.error(f"The swarm stopped: {type(exc).__name__}: {exc}")

    for ev in _guard(events):
        if ev.type == "agent_start":
            buf = ""
            stage = {"optimizer": 1, "critic": 2, "arbiter": 3}[ev.agent]
            banner_ph.markdown(safe(banner(stage, ctx, breaking)), unsafe_allow_html=True)
        elif ev.type == "token":
            buf += ev.text
            visible = buf.split("<json>")[0]
            status = "alert" if ev.agent == "critic" and len(visible) > 40 else "thinking"
            panel_ph[ev.agent].markdown(safe(agent_panel(ev.agent, visible, None, status, scen)), unsafe_allow_html=True)
        elif ev.type == "repair":
            st.toast(f"{AGENT_BY_KEY[ev.agent].name}: verdict block malformed, recovered via structured call.", icon="🔧")
        elif ev.type == "fallback":
            st.toast(f"Live call failed for {ev.agent}; switched to replay.", icon="⚠️")
            buf = ""
        elif ev.type == "agent_done":
            ctx[ev.agent] = ev.data
            narr[ev.agent] = ev.text
            status = {"critic": "alert", "arbiter": "resolved"}.get(ev.agent, "done")
            panel_ph[ev.agent].markdown(safe(agent_panel(ev.agent, ev.text, ev.data, status, scen)), unsafe_allow_html=True)
            banner_ph.markdown(safe(banner(stage, ctx, breaking)), unsafe_allow_html=True)
            show_map(stage)
            if ev.agent == "critic":
                time.sleep(1.2 / speed)  # let the red alert land before the Arbiter speaks
        elif ev.type == "swarm_done":
            done = True
    return ctx, narr, done


if not run:
    if history:
        render_recheck(history[-1], len(history))
    else:
        render_static(st.session_state.get("result"))
else:
    # ---------------------------------------------------------- live run
    if connected and not api_key:
        render_static(None)
        st.error("Connected-data runs need the Live engine: paste an API key for the selected engine in the sidebar.")
        st.stop()
    backend, replay = make_backend()
    history.clear()
    view_scen = scenario
    for a in AGENTS:
        panel_ph[a.key].markdown(safe(agent_panel(a.key, "", None, "idle", scenario)), unsafe_allow_html=True)
    kpi_ph.empty()
    ctx, narr, done = stream_events(run_swarm(scenario, backend, fallback=replay), scenario, {})
    if done:
        kpi_ph.markdown(safe(kpis(ctx, scenario)), unsafe_allow_html=True)
        st.session_state["result"] = {"ctx": ctx, "narr": narr}


# ------------------------------------------------------------------ breaking news
result = st.session_state.get("result")
if result and "arbiter" in result.get("ctx", {}):
    live = engine.startswith("Live") and bool(api_key)
    used = {h.get("twist") for h in history}
    twists = [t for t in scenario.get("twists", []) if t["id"] not in used]
    with news_box:
        st.markdown("##### ⚡ Breaking news")
        options = [t["label"] for t in twists] + (["✍️ Write my own bulletin…"] if live else [])
        if not options:
            st.caption("No more pre-recorded events for this scenario. Switch to the Live engine "
                       "to write your own bulletin.")
            choice, inject = None, False
        else:
            choice = st.selectbox("Event", options, key=f"twist_{scen_key}_{len(history)}",
                                  label_visibility="collapsed")
            custom = ""
            if choice == "✍️ Write my own bulletin…":
                custom = st.text_area("Bulletin", key=f"custom_{scen_key}_{len(history)}",
                                      placeholder="e.g. Dockworkers at Rotterdam begin a 72-hour strike on Monday",
                                      label_visibility="collapsed")
            inject = st.button("⚡ Inject & re-check", width="stretch", key=f"inject_{scen_key}_{len(history)}")
        if history:
            with st.expander(f"🕒 Decision history ({len(history) + 1} versions)"):
                versions = [("v1", "Initial decision", result["ctx"]["arbiter"])] + [
                    (f"v{i + 2}", f'{h["bulletin"]["id"]}: {h["bulletin"]["text"][:70]}…', h["ctx"]["arbiter"])
                    for i, h in enumerate(history)]
                st.dataframe([{"Version": v, "Trigger": t, "Decision": a.get("decision"),
                               "Route": a.get("final_route_id"), "Days": a.get("transit_days"),
                               "Cost": money(a.get("est_cost_usd")), "Risk": a.get("residual_risk_score")}
                              for v, t, a in versions], width="stretch", hide_index=True)

    if inject:
        bid = f"NEW-{len(history) + 1:02d}"
        twist = next((t for t in twists if t["label"] == choice), None)
        if twist:
            bulletin = {**twist["bulletin"], "id": bid}
            hotspot = twist.get("hotspot")
            if hotspot:
                hotspot = {**hotspot, "label": hotspot["label"].replace(twist["bulletin"]["id"], bid)}
            script = twist["script"] if bid == twist["bulletin"]["id"] else None  # replay cites its own id
        elif custom.strip():
            bulletin, hotspot = make_breaking_bulletin(custom, view_scen, bid)
            script = None
        else:
            st.warning("Write the bulletin first.")
            st.stop()
        backend, replay = make_backend()
        if not live and not script:
            st.warning("This event has no pre-recorded replay. Switch to the Live engine to run it.")
            st.stop()
        prior = history[-1]["ctx"] if history else result["ctx"]
        rescen = recheck_scenario(view_scen, bulletin, hotspot, script)
        st.toast(f"⚡ Breaking: {bulletin['text'][:80]}", icon="⚡")
        panel_ph["optimizer"].markdown(safe(booked_panel(prior["arbiter"], rescen)), unsafe_allow_html=True)
        for key in ("critic", "arbiter"):
            panel_ph[key].markdown(safe(agent_panel(key, "", None, "idle", rescen)), unsafe_allow_html=True)
        kpi_ph.empty()
        seed = {"current_plan": prior["arbiter"]}
        ctx, narr, done = stream_events(run_recheck(rescen, backend, prior, fallback=replay), rescen, seed, bulletin)
        if done:
            history.append({"twist": twist["id"] if twist else None, "bulletin": bulletin, "hotspot": hotspot,
                            "scenario": rescen, "ctx": ctx, "narr": narr})
            st.rerun()  # redraw with the history and the next set of events
