# 🛰️ RouteGuard

**An adversarial three-agent swarm that re-routes cargo when geopolitics, sanctions or disruptions break the plan.**

One agent plans. One aggressively hunts for geopolitical and legal flaws. One arbitrates the conflict and issues a safe, optimal route in seconds. The agents run on curated demo scenarios, or on **your own manifest and real-world sources**: maritime security advisories, OFAC/EU/UK sanctions lists, export-control lists, canal and port notices, carrier schedules and rates.

- **Live demo:** https://routeguard39.streamlit.app
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Contents
- [The problem](#the-problem)
- [The solution](#the-solution)
- [Demo walkthrough](#demo-walkthrough)
- [Run it yourself](#run-it-yourself)
- [Connect your own data](#connect-your-own-data)
- [Judge FAQ](#judge-faq)
- [Limitations (honestly)](#limitations-honestly)
- [Roadmap](#roadmap)
- [Repository layout](#repository-layout)

---

## The problem

When trade regulations change or regional conflicts flare, supply chains stall. Traditional routing software optimizes time and cost against a rate table. It doesn't notice that:

- a canal is under attack, and the war-risk premium now exceeds the freight bill;
- the cargo insurer just suspended cover for that stretch of water;
- the transshipment port was sanctioned this morning;
- the cargo is a dual-use item that needs an export licence nobody filed;
- the canal queue will outlast the refrigerated containers' fuel.

A person has to connect these dots across news, sanctions lists, insurer notices and port bulletins, usually after the booking is made. Mistakes mean missed deadlines, uninsured losses, spoiled cargo or sanctions violations.

## The solution

RouteGuard puts three specialized agents in a war room and makes them argue:

| Agent | Mandate | Sees |
|---|---|---|
| 🧭 **Optimizer** | Fastest, cheapest route that meets the deadline. Deliberately optimistic. | Manifest + candidate routes (**no** risk intel) |
| 🚨 **Critic** | Break the plan: security, war-risk insurance, sanctions, export controls, strikes, canal limits, cargo-specific risk. Every flag must cite evidence. | Everything above + the intel feed + the Optimizer's plan |
| ⚖️ **Arbiter** | Issue one binding, executable decision with mitigations. Priorities: **legal → safety → deadline → total cost including risk**. | Everything above + the Critic's findings |

Judges watch the whole debate stream live. The Critic's panel turns red and risk hotspots light up on the map. Then the Arbiter's route redraws in green, with before-and-after numbers.

Under the agents, a **connector layer** (`sources/`) turns real-world feeds, lists and APIs into one citable bulletin format, so the same agents work on any shipment.

## Demo walkthrough

Pick a scenario in the sidebar and click **▶ Run the swarm**.

| Scenario | Optimizer proposes | Critic finds | Arbiter decides |
|---|---|---|---|
| **Microchips vs. the Red Sea**: $48M of ICs, Kaohsiung → Rotterdam, 32 days | Suez: 23 days, $410k | Drone attacks at Bab el-Mandeb, war & strikes cover suspended, **+$480k war-risk premium**, 72-hour canal strike, diversion risk, seal tampering at Colombo. Risk **92/100**. | **Pivot** around the Cape of Good Hope (express) + air-freight the one line-critical container: **30 days, $602k, fully insured**, risk 16 |
| **Dual-use machine tools via a newly sanctioned port**: $6.4M of 5-axis CNC centres, Hamburg → Tashkent | Via Bandar Abbas: 27 days, $118k | Newly sanctioned terminal operator, **dual-use items with no export licence**, forwarder linked to a diversion network, no insurance cover. Risk **98/100**. | **Pivot** to the Trans-Caspian Middle Corridor, cargo released only once the licence is granted: **36 days, $164k**, risk 26 |
| **Biologics vs. a jammed Panama Canal**: $31M of 2-8 °C vials, Antwerp → Los Angeles | Panama: 21 days, $96k | 12–16 day canal queue, **refrigerated-container fuel lasts 9–10 days**, boxes offloaded to meet the draft limit, tropical storm. Risk **84/100**. | **Pivot** to sea-to-Houston + refrigerated-truck landbridge: **23 days, $142k**, risk 14 |

**⚡ Breaking news:** once the Arbiter has decided, pick a breaking event under the map and click **Inject & re-check**. The new bulletin (cited as `NEW-01`) lights up on the map, the Critic re-attacks the *booked* route with it, and the Arbiter either holds course or pivots again. A "What changed" card compares before and after, and a decision history keeps every version. The Optimizer doesn't run again: it can't see intel, so it would only propose the same route.

| Scenario | Breaking event | Arbiter's update |
|---|---|---|
| Red Sea | Strike and gales at the Cape Town terminal | **Holds course**: skip the Cape Town call and refuel at Port Louis. 31 days, $620k |
| Dual-use | Caspian ferry suspended for 10 days | **Holds course**: the cargo can't reach the ferry before it reopens. Pre-book a slot: 38 days, $169k |
| Biologics | Hurricane forecast to hit Houston as the ship arrives | **Re-routes** to temperature-controlled air freight: 2 days, $483k |

In Live mode you can also write your own bulletin. It's pinned to the first port or chokepoint it names on a candidate route.

**Engine:** "Replay" (the default) streams pre-recorded agent output: offline, identical every run, safe for the stage. "Live" calls Claude with the same prompts and data.

**Your own shipment:** set the sidebar's **Data** option to *Connected sources (your shipment)*. Upload a manifest (JSON/CSV) or pick a sample. RouteGuard pulls candidate routes and intel from every source in `config/sources.toml`, shows a per-source status table and previews the lanes on the map. Then the agents run live on the result.

## Run it yourself

```bash
git clone https://github.com/sriramr-repo/routeguard && cd routeguard
pip install -r requirements.txt
streamlit run app.py
```

Live mode (and connected-data runs) need an Anthropic API key, provided in any one of these ways:
- **the sidebar**, pasted in at runtime: kept only in your browser session;
- locally, an environment variable: `export ANTHROPIC_API_KEY=sk-ant-...`;
- on a hosted app, Streamlit Secrets `ANTHROPIC_API_KEY = "sk-ant-..."` **plus** `ROUTEGUARD_PASSCODE = "..."`. The saved key stays locked until the owner enters the passcode, so visitors can't spend your credits.

To change the model, set `ROUTEGUARD_MODEL` or edit it in the sidebar. The default is `claude-sonnet-5-5`.

Terminal version, with no UI:

```bash
python pipeline.py --scenario red_sea                                              # curated demo, replay
python pipeline.py --scenario embargo --live                                       # curated demo, live Claude
python pipeline.py --scenario cold_chain --twist                                   # then inject breaking news and re-check
python pipeline.py --manifest examples/manifests/cnc_tashkent.json --ingest-only   # show what the sources produce
python pipeline.py --manifest my_shipment.csv                                      # full live run on your data
python -m unittest discover -s tests                                               # connector tests
```

---

## Connect your own data

The agents are source-agnostic. Every feed, list and API is converted by an adapter in `sources/` into one **bulletin** format (id, time, source, category, severity, text, url, location), the same format the Critic already cites. Which sources are on, and where they point, is set in **`config/sources.toml`**.

| Real-world source | Adapter `type` | Formats supported |
|---|---|---|
| Maritime security advisories | `rss`, `json` | RSS 2.0, Atom, any JSON API via field mapping |
| Sanctions lists (OFAC, EU, UK) | `sanctions_list`, `country_embargo` | OFAC `SDN.CSV`, EU Financial Sanctions Files CSV, UK consolidated CSV, generic CSV; ISO-2 jurisdiction map |
| Export-control lists | `export_rules`, `trade_gov_csl` | HS-code/keyword rule CSV (your EU dual-use / US CCL mapping); US Consolidated Screening List API |
| Canal & port authority notices | `rss`, `json` | RSS 2.0, Atom, JSON |
| Carrier schedules & rates | `dcsa`, `route_csv` | DCSA Commercial Schedules point-to-point routings + rate sheet; your own route-library CSV |
| Shipper manifest | `load_manifest()` | JSON or CSV from a TMS/ERP, with common field aliases (`port_of_loading`, `commodity`, `invoice_value`...) |

What happens when you run a shipment:
1. The manifest is normalized and candidate routes are loaded from the route sources.
2. Each route is drawn along a global sea-lane graph, so the system knows which chokepoints it passes (Suez, Bab el-Mandeb, Hormuz, Malacca, Panama, the Cape...).
3. Every intel source runs:
   - Feed items are kept only if they mention a port or chokepoint on a candidate route.
   - Sanctions lists screen **every party**: shipper, consignee, notify party, forwarder, carrier and route operators.
   - Export rules check the HS code and cargo against the destination and the licence on file.
4. Bulletins are deduped, ranked by severity and given citable IDs (`SEC-01`, `SAN-02`, `EXP-01`...), then handed to the agents.
5. A broken source is reported in the status table and skipped. It never stops the run.

**Out of the box** the config points at **sample files** in `examples/`: fictional feed items, fictional list entries, and a sample DCSA response. That way connected mode works offline and in tests. For real use, copy `config/sources.production.example.toml` to `config/sources.toml`, fill in the endpoints and licences you have, and set API keys as environment variables or Streamlit secrets (`TRADE_GOV_API_KEY`, carrier keys...).

**Adding a source** is one class with `fetch(ctx) -> list[Bulletin]`, registered in `sources/registry.py`. Details and diagrams are in [ARCHITECTURE.md §6](ARCHITECTURE.md#6-connecting-real-data-built).

---

## Judge FAQ

### Product & value

**Who is the customer?**
Freight forwarders, shipping lines, and shippers with high-value or regulated cargo (semiconductors, pharma, industrial equipment). Inside those companies, the users are logistics planners and trade-compliance teams.

**What does it actually save?**
In the Red Sea scenario, the "cheap" Suez route really costs about $890k once the war-risk premium is included, and it leaves $48M of cargo uninsured. RouteGuard's answer costs $602k and keeps the cargo covered. The bigger savings are the tail risks it avoids: a sanctions violation, a spoiled $31M biologics shipment, a production line stopped for want of one container.

**How is this different from existing supply-chain visibility or risk tools?**
Many tools track shipments and raise risk alerts, and a person still has to turn an alert into a decision. RouteGuard closes that loop. It takes a specific shipment, finds the specific ways the specific plan fails, and outputs an executable alternative with mitigations and cited evidence.

**Why does speed matter?**
Disruptions such as a new sanctions designation, an insurer notice or a canal restriction change the right answer within hours. RouteGuard re-evaluates a shipment in seconds, so it can re-check every active booking whenever the intel changes.

**Could a company actually plug this in?**
Yes, that's what the connector layer is for. Point `config/sources.toml` at your feeds, lists and carrier APIs, export manifests from your TMS as JSON or CSV, and run. See [Connect your own data](#connect-your-own-data).

### AI design

**Why three agents instead of one big prompt?**
One model asked to "find the best safe route" tends to settle on a middle answer and anchors on its first idea. Splitting the roles creates real tension. The Optimizer commits to the commercial answer, and the Critic's only job is to attack it, which surfaces second-order failures (insurance exclusions, a line-critical container's window, a forwarder's address match). Then an Arbiter with explicit priorities resolves the conflict. It also makes the reasoning auditable: you can see who argued what.

**Why is the Optimizer blind to the risk feed?**
On purpose. It plays the role of today's routing software. The gap between its plan and the Critic's findings is exactly the value RouteGuard adds, and the demo makes that gap visible.

**How do the agents communicate?**
They run in a simple sequential loop. Each one receives the manifest and candidate routes, plus the structured JSON verdicts of the agents before it. There's no shared hidden state, so everything an agent knows is in its input. See the sequence diagram in [ARCHITECTURE.md](ARCHITECTURE.md#3-the-agent-loop).

**How do you prevent hallucinations?**
- **Constrained choices.** Agents may only pick a `route_id` from the candidate routes, so they select and justify rather than invent routes.
- **Evidence required.** Every Critic flag must cite a bulletin ID or manifest field (for example `RS-02`, `SAN-01` or `manifest.export_licence`), and the prompt forbids facts the inputs don't support.
- **Deterministic facts.** In connected mode, sanctions screening, jurisdiction checks, export-control rule matching and route relevance are plain Python, not the model. The model reasons about the results.
- **Structured output.** Every agent ends with a strict JSON verdict, and the UI renders from that JSON, not from free text.
- **Fixed decision rules.** The Arbiter's priority order is written into its prompt.

**Which model?**
Claude via the Anthropic Messages API, streamed. The default is `claude-sonnet-5-5`, configurable per run.

**What does a live run cost, and how long does it take?**
Three sequential model calls, each with a few thousand input tokens and a few hundred output tokens. That's typically tens of seconds end to end and a few cents per run at Sonnet-class pricing; exact figures depend on the model and current pricing. Ingesting sources adds little: local files take milliseconds, and remote feeds are cached.

### Data

**Where does the data come from?**
It depends on the mode:
- **Curated demo scenarios** (the stage demo): everything is **hardcoded** in `scenarios.py`, with no live scraping, so the demo can't break on stage.
- **Connected sources**: a real manifest (uploaded JSON/CSV) plus the feeds, lists and APIs configured in `config/sources.toml`, through the adapters in `sources/`. As shipped, that config points at bundled **sample** files so it works offline. Point it at live endpoints to use real data.

**Is the intel in the demo scenarios real?**
No. Those bulletins are **simulated**, and the app labels them that way. They're modeled on real kinds of disruption: attacks on Red Sea shipping, war-risk premium spikes, insurer listed-area exclusions, sanctions designations, EU dual-use controls on high-precision machine tools, and Panama Canal draft restrictions during drought. The specific events, dates, companies and figures are invented. Route transit times and costs are plausible estimates, not carrier quotes. The sample files in `examples/` are fictional too, and are marked SAMPLE.

**Are the agents' answers scripted?**
In **Replay** mode, yes: the narration is pre-recorded so the demo is repeatable. In **Live** mode and in every connected-data run, the three agents reason in real time using the same prompts.

**Have the connectors been tested against the live endpoints?**
They're tested (`tests/test_sources.py`, 18 tests) against sample files in each publisher's documented format: OFAC SDN CSV, EU FSF CSV, UK consolidated CSV, RSS, Atom, JSON, and DCSA point-to-point routings. They have **not** been validated against every live endpoint; publishers change URLs and layouts, and some need keys or licences. Verify each feed when you switch it on. The per-source status table makes a broken feed obvious.

**How do you avoid flooding the Critic with irrelevant news?**
Relevance is geographic and deterministic. Each candidate route is expanded along a sea-lane graph, and a feed item is kept only if it mentions a port or chokepoint on one of the routes (for example, a Gulf of Guinea piracy report is dropped for a Shanghai → Rotterdam shipment). Items are also age-limited, deduped, ranked by severity and capped.

**Is sanctions screening done by the LLM?**
No. List screening is deterministic: normalized name matching of every party against the actual list entries, plus a jurisdiction check on every place a route passes through. The model only reasons about the hits. For production compliance, your screening provider stays the source of truth; RouteGuard adds the routing decision on top.

### Reliability & safety

**What happens if the API or network fails during the demo?**
In the curated scenarios, the live engine falls back to replay automatically for the rest of that run, with a small on-screen notice. Replay mode needs no network after the page loads. In connected mode, a failing *source* is skipped and reported; a failing *model call* stops the run with a clear error, because there's no script to fall back to.

**Who can use the API key on the public app?**
Only its owner. A key pasted into the sidebar lives only in that browser session and is never stored. A key saved in Streamlit Secrets is **locked**: it's used only after the owner enters the passcode set as `ROUTEGUARD_PASSCODE` in Secrets. With no passcode configured, a saved key is never used on the hosted app. Everyone else can watch the Replay demo, or paste their own key.

**Is the Arbiter's decision final?**
Not in production. The decision goes to a human logistics or compliance approver before anything is booked, and every input, verdict and cited piece of evidence goes into an audit log. RouteGuard is decision support, not legal advice.

**Could it recommend something illegal?**
The Arbiter's first rule is legal compliance, and it can only choose from the candidate routes. In connected mode, deterministic screening flags sanctioned parties, embargoed jurisdictions and unlicensed controlled goods before the agents run. In production, anything flagged CRITICAL would also be hard-blocked from booking until a human clears it.

### Engineering

**Tech stack?**
Python 3.11+, Streamlit (UI and real-time streaming), Plotly (geo map), Anthropic Python SDK. The connectors use only the standard library (urllib, csv, xml, tomllib). Hosted on Streamlit Community Cloud, which redeploys on every push.

**How would it scale?**
Each shipment evaluation is independent, so the work runs in parallel across shipments. Source ingestion is cached and shared across shipments (a sanctions list is downloaded once, not per shipment). The expensive part is the three model calls, and the relevance filter keeps the Critic's context small. Evaluations would be triggered when a new bulletin touches an active lane, not on a fixed poll.

**How do you know it's right?**
- **Demo:** every recommended route is checked by hand against the scenario data, and each scenario includes a trap that must be caught (sanctioned terminal, missing licence, refrigerated-container fuel shorter than the queue).
- **Connectors:** unit tests cover parsing, filtering, screening, deduping and end-to-end scenario building.
- **Next:** a benchmark of labelled historical disruptions, scoring Critic recall on known risks and whether the Arbiter's pick is compliant, on time and cost-effective, compared against a single-prompt baseline.

---

## Limitations (honestly)

- The curated demo scenarios use simulated intel and illustrative prices.
- Connected mode ships pointed at **sample** files. Live endpoints need configuring, keys or licences, and verification.
- Sanctions matching is name-based (normalized and fuzzy). It doesn't use addresses, dates of birth or IDs, so treat hits as leads for review.
- The sea-lane graph is coarse: good for maps and chokepoint detection, not navigation.
- Cost and risk scores in the agents' verdicts come from model judgment, not a calibrated model.
- No human-approval step, audit log or TMS integration yet.
- Live output varies run to run; use Replay for a repeatable stage demo.

## Roadmap

1. ~~Upload your own manifest and run it live~~ ✅ built
2. ~~Connectors: maritime security, sanctions, export controls, canal/port notices, carrier schedules~~ ✅ built (sample-wired)
3. Verify and switch on live endpoints; add insurer listed-area and AIS vessel-position adapters.
4. Deterministic tools the agents can call: cost and transit calculators.
5. Continuous monitoring: re-check in-flight shipments whenever new intel arrives. *First step built: breaking-news injection re-checks a booked plan on demand.*
6. Human approval, audit log and TMS integration.
7. Evaluation benchmark against historical disruptions.

## Repository layout

```
app.py                 Streamlit live view (war room, map, KPIs, connected-sources mode)
pipeline.py            Sequential agent loop, Replay + Claude engines, fallback, CLI
agents.py              The three system prompts and per-agent context
scenarios.py           Curated demo data: manifests, routes, simulated intel, replay scripts
sources/               Data connectors
  base.py              Bulletin schema, HTTP/file reader with cache, severity heuristics
  manifest.py          Shipper manifest loader (JSON/CSV, field aliases)
  feeds.py             RSS/Atom + JSON feeds (maritime security, canal/port notices)
  sanctions.py         OFAC/EU/UK list parsers, party screening, jurisdiction check
  export_controls.py   HS/keyword control rules, US Consolidated Screening List API
  carriers.py          Route-library CSV, DCSA schedules, rate sheet
  geo.py, sealanes.py  Ports, chokepoints, sea-lane routing, place matching
  registry.py          Reads config, runs sources, builds the scenario
config/                sources.toml (sample-wired) + production example
data/ports.csv         Port lookup (UN/LOCODE, coordinates)
examples/              Sample manifests, feeds, lists, schedules (fictional)
tests/                 Connector and re-check tests
ARCHITECTURE.md        System design, diagrams, connector layer, production roadmap
requirements.txt       streamlit, plotly, anthropic
.streamlit/            Dark theme config
```
