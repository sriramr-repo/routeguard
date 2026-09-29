"""
RouteGuard - live Streamlit view of the three-agent routing swarm.

    streamlit run app.py
"""

from __future__ import annotations

import hmac
import html
import os
import time

import plotly.graph_objects as go
import streamlit as st

from agents import AGENTS
from pipeline import ClaudeBackend, ReplayBackend, run_swarm
from scenarios import SCENARIOS
from sources import build_scenario, load_manifest

SOURCES_CONFIG = os.environ.get("ROUTEGUARD_SOURCES", "config/sources.toml")
SAMPLE_MANIFESTS = {
    "Sample: CNC machines, Hamburg → Tashkent": "examples/manifests/cnc_tashkent.json",
    "Sample: EV batteries, Shanghai → Rotterdam": "examples/manifests/batteries_rotterdam.csv",
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
.rg-kpis {display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin-top:6px;}
.rg-kpi {background:#111a2e; border:1px solid #1e293b; border-radius:12px; padding:10px 12px;}
.rg-kpi .k {color:#94a3b8; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em;}
.rg-kpi .v {font-size:1.35rem; font-weight:700;}
.rg-kpi .d {font-size:0.78rem; color:#94a3b8;}
.rg-intel {font-size:0.84rem; padding:6px 0; border-bottom:1px solid #1e293b;}
@media (max-width: 900px) {.rg-manifest, .rg-kpis {grid-template-columns: repeat(2, minmax(0,1fr));}}
</style>
""", unsafe_allow_html=True)


try:
    for _k, _v in st.secrets.items():
        # connector keys (e.g. TRADE_GOV_API_KEY) go to env; the Anthropic key never does
        if isinstance(_v, str) and "anthropic" not in _k.lower() and not _v.strip().startswith("sk-ant-"):
            os.environ.setdefault(_k, _v)
except Exception:
    pass


@st.cache_data(ttl=900, show_spinner="Ingesting connected sources…")
def ingest(manifest_text: str, filename: str, config_path: str, config_mtime: float):
    manifest = load_manifest(manifest_text, filename)
    return build_scenario(manifest, config_path)


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


def get_api_key() -> str | None:
    """Server-side Anthropic key from Streamlit secrets (any casing, top level or inside a section)
    or the environment. Never displayed or logged. Callers must gate it (see sidebar)."""
    def clean(v: str) -> str:
        return v.strip().strip('"').strip("'").strip()

    def scan(d, path="") -> tuple[str, str] | None:
        try:
            items = list(d.items())
        except Exception:
            return None
        for k, v in items:
            if isinstance(v, str) and clean(v).startswith("sk-ant-"):
                return clean(v), f"{path}{k}"
        for k, v in items:
            if isinstance(v, str) and "anthropic" in k.lower() and "key" in k.lower():
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
    if not found and os.environ.get("ANTHROPIC_API_KEY"):
        found = (clean(os.environ["ANTHROPIC_API_KEY"]), "env ANTHROPIC_API_KEY")
    if not found:
        st.session_state["key_diag"] = "no key in secrets or environment"
        return None
    key, where = found
    # safe diagnostic: field name, length, prefix check. Never the key itself.
    st.session_state["key_diag"] = (f"key from '{where}', {len(key)} chars, "
                                    f"{'starts with sk-ant-' if key.startswith('sk-ant-') else 'does NOT start with sk-ant-'}")
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
        flags = "".join(
            f'<div class="rg-flag" style="--s:{SEV_COLOR.get(f.get("severity"), "#ef4444")};animation-delay:{i * 0.12:.2f}s">'
            f'<div class="t"><span style="color:{SEV_COLOR.get(f.get("severity"), "#ef4444")}">{html.escape(f.get("severity", ""))}</span>'
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


def build_map(scenario: dict, stage: int, ctx: dict) -> go.Figure:
    """stage 0: nothing, 1: optimizer route, 2: critic hotspots (route red), 3: arbiter route."""
    fig = go.Figure()
    # an invisible geo trace so the world map renders even before any route exists
    fig.add_trace(go.Scattergeo(lat=[0], lon=[0], mode="markers", marker=dict(size=0, opacity=0),
                                showlegend=False, hoverinfo="skip"))
    routes = scenario["routes"]

    shown: set[str] = set()

    def draw(route_id: str, color: str, width: float, opacity: float, name: str):
        r = routes.get(route_id)
        if not r:
            return
        for i, leg in enumerate(r["legs"]):
            first = i == 0 and name not in shown
            shown.add(name)
            lats, lons = zip(*leg["pts"])
            dash = {"sea": "solid", "land": "dash", "air": "dot"}[leg["mode"]]
            fig.add_trace(go.Scattergeo(
                lat=lats, lon=lons, mode="lines", line=dict(width=width, color=color, dash=dash),
                opacity=opacity, name=name, showlegend=first, legendgroup=name, hoverinfo="name"))
        first, last = r["legs"][0]["pts"][0], r["legs"][-1]["pts"][-1]
        fig.add_trace(go.Scattergeo(
            lat=[first[0], last[0]], lon=[first[1], last[1]], mode="markers+text",
            marker=dict(size=9, color=color, line=dict(width=1, color="white")),
            text=[r["via"][0], r["via"][-1]], textposition="top center",
            textfont=dict(color="#e2e8f0", size=11), showlegend=False, hoverinfo="skip", opacity=opacity))

    opt = ctx.get("optimizer", {}).get("route_id")
    if stage == 0 and scenario.get("live_data"):
        for rid in routes:
            draw(rid, "#64748b", 2.0, 0.8, "Candidate routes")
        hs = scenario["hotspots"]
        if hs:
            fig.add_trace(go.Scattergeo(
                lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers",
                marker=dict(size=11, color="#f59e0b", line=dict(width=1, color="white")),
                text=[h["label"] for h in hs], name="Intel on these lanes", hoverinfo="text"))
    if stage == 1 and opt:
        draw(opt, "#3b82f6", 3.5, 1.0, "Optimizer proposal")
    if stage >= 2 and opt:
        draw(opt, "#ef4444", 3.5 if stage == 2 else 2.0, 1.0 if stage == 2 else 0.35,
             "Rejected by Critic" if stage == 2 else "Rejected route")
        hs = scenario["hotspots"]
        fig.add_trace(go.Scattergeo(
            lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers",
            marker=dict(size=38, color="rgba(239,68,68,0.25)"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scattergeo(
            lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers+text",
            marker=dict(size=13, color="#ef4444", symbol="x", line=dict(width=1, color="white")),
            text=[f"⚠ {h['label']}" for h in hs], textposition=[h.get("pos", "bottom right") for h in hs],
            textfont=dict(color="#fca5a5", size=12), name="Risk hotspots", hoverinfo="text"))
    if stage >= 3:
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


def banner(stage: int, ctx: dict) -> str:
    if stage == 0:
        return ""
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
    server_key = get_api_key()
    api_key = None
    if not connected:
        scen_key = st.radio("Scenario", list(SCENARIOS), format_func=lambda k: SCENARIOS[k]["title"], key="scenario")
        engine = st.radio(
            "Engine", ["Replay (offline, demo-safe)", "Live (Claude API)"],
            help="Replay streams pre-recorded agent output: identical every run, no network. "
                 "Live calls Claude with the same prompts; if a call fails it falls back to replay.")
    else:
        up = st.file_uploader("Shipper manifest (JSON or CSV)", type=["json", "csv"])
        sample = st.selectbox("…or use a sample manifest", list(SAMPLE_MANIFESTS), disabled=up is not None)
        engine = "Live (Claude API)"
        st.caption("Connected-data runs always use the Live engine.")
    if engine.startswith("Live"):
        typed = st.text_input("Anthropic API key", type="password", value="",
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
        model = st.text_input("Model", value=os.environ.get("ROUTEGUARD_MODEL", "claude-sonnet-5-5"))
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
        scenario, source_report = ingest(man_text, man_name, SOURCES_CONFIG, cfg_mtime)
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
    st.session_state["last_scen"] = scen_key

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
              "ms": r.get("ms", "")} for r in source_report],
            use_container_width=True, hide_index=True)
        st.caption(f"Config: {SOURCES_CONFIG}. Failing sources are skipped, never fatal.")

with st.expander("📡 Intelligence feed " + ("(from connected sources)" if scenario.get("live_data") else "(simulated)")
                 + " and full manifest"):
    c1, c2 = st.columns([3, 2])
    with c1:
        for b in scenario["intel"]:
            st.markdown(safe(f'<div class="rg-intel"><b style="color:{SEV_COLOR.get(b["severity"], "#94a3b8")}">'
                f'[{b["id"]}] {b["severity"]}</b> · {html.escape(str(b.get("time", "")))} · <i>{html.escape(b["source"])}</i><br>'
                f'{html.escape(b["text"])}'
                + (f' <a href="{html.escape(b["url"])}" target="_blank">source</a>' if b.get("url") else "")
                + '</div>'), unsafe_allow_html=True)
        if not scenario["intel"]:
            st.caption("No relevant bulletins for this shipment's routes.")
    with c2:
        st.json(m)

run = st.button("▶  Run the swarm", type="primary", use_container_width=True)

left, right = st.columns([11, 10], gap="large")
with left:
    st.markdown("#### 🗣️ War room")
    panel_ph = {a.key: st.empty() for a in AGENTS}
with right:
    st.markdown("#### 🗺️ Route")
    banner_ph = st.empty()
    map_ph = st.empty()
    kpi_ph = st.empty()


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
    map_ph.plotly_chart(build_map(scenario, stage, ctx), use_container_width=True,
                        config={"displayModeBar": False}, key=f"map_static_{scen_key}_{stage}")
    kpi_ph.markdown(safe(kpis(ctx, scenario)), unsafe_allow_html=True)


if not run:
    render_static(st.session_state.get("result"))
else:
    # ---------------------------------------------------------- live run
    replay = ReplayBackend(speed=speed)
    backend = replay
    if connected and not api_key:
        render_static(None)
        st.error("Connected-data runs need the Live engine: add ANTHROPIC_API_KEY in Secrets or paste it in the sidebar.")
        st.stop()
    if engine.startswith("Live"):
        try:
            backend = ClaudeBackend(model=model, api_key=api_key) if api_key else replay
        except Exception as exc:
            st.toast(f"Live engine unavailable ({exc}); using replay.", icon="⚠️")
            backend = replay

    ctx: dict = {}
    narr: dict = {}
    run_id = str(time.time_ns())
    for a in AGENTS:
        panel_ph[a.key].markdown(safe(agent_panel(a.key, "", None, "idle", scenario)), unsafe_allow_html=True)
    kpi_ph.empty()

    def show_map(stage: int):
        map_ph.plotly_chart(build_map(scenario, stage, ctx), use_container_width=True,
                            config={"displayModeBar": False}, key=f"map_{run_id}_{stage}_{len(ctx)}")

    show_map(0)
    buf = ""
    stage = 0
    def _guard(gen):
        try:
            yield from gen
        except Exception as exc:
            st.error(f"The swarm stopped: {type(exc).__name__}: {exc}")

    for ev in _guard(run_swarm(scenario, backend, fallback=replay)):
        if ev.type == "agent_start":
            buf = ""
            stage = {"optimizer": 1, "critic": 2, "arbiter": 3}[ev.agent]
            banner_ph.markdown(safe(banner(stage, ctx)), unsafe_allow_html=True)
        elif ev.type == "token":
            buf += ev.text
            visible = buf.split("<json>")[0]
            status = "alert" if ev.agent == "critic" and len(visible) > 40 else "thinking"
            panel_ph[ev.agent].markdown(safe(agent_panel(ev.agent, visible, None, status, scenario)), unsafe_allow_html=True)
        elif ev.type == "repair":
            st.toast(f"{AGENT_BY_KEY[ev.agent].name}: verdict block malformed, recovered via structured call.", icon="🔧")
        elif ev.type == "fallback":
            st.toast(f"Live call failed for {ev.agent}; switched to replay.", icon="⚠️")
            buf = ""
        elif ev.type == "agent_done":
            ctx[ev.agent] = ev.data
            narr[ev.agent] = ev.text
            status = {"critic": "alert", "arbiter": "resolved"}.get(ev.agent, "done")
            panel_ph[ev.agent].markdown(safe(agent_panel(ev.agent, ev.text, ev.data, status, scenario)), unsafe_allow_html=True)
            banner_ph.markdown(safe(banner(stage, ctx)), unsafe_allow_html=True)
            show_map(stage)
            if ev.agent == "critic":
                time.sleep(1.2 / speed)  # let the red alert land before the Arbiter speaks
        elif ev.type == "swarm_done":
            kpi_ph.markdown(safe(kpis(ctx, scenario)), unsafe_allow_html=True)
            st.session_state["result"] = {"ctx": ctx, "narr": narr}
