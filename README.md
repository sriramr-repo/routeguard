# 🛰️ RouteGuard: an adversarial routing swarm

When trade rules change or regional conflicts flare, supply chains stall. RouteGuard puts three AI agents in a war room:

| Agent | Job |
|---|---|
| 🧭 **Optimizer** | Plans the fastest, cheapest route. Deliberately blind to risk. |
| 🚨 **Critic** | Attacks the plan: security, war-risk insurance, sanctions, export controls, strikes, canal limits, cargo-specific risk. |
| ⚖️ **Arbiter** | Resolves the conflict and issues one binding, executable route with mitigations. |

The agents run in a simple sequential loop (`Optimizer → Critic → Arbiter`). Each one sees the manifest plus every earlier verdict, and the Streamlit UI streams each agent "talking" in real time. The Critic lights the UI up red, and the map redraws as the Arbiter pivots the cargo.

## Demo scenarios (hardcoded, no live scraping)

1. **Microchips vs. the Red Sea:** $48M of ICs, Kaohsiung → Rotterdam. Suez gets rejected (drone attacks, suspended war-risk cover, a $480k premium, a canal strike). The Arbiter pivots around the Cape of Good Hope and air-freights the line-critical container.
2. **Dual-use machine tools via a newly sanctioned port:** 5-axis CNC centres, Hamburg → Tashkent via Bandar Abbas. The Critic catches the sanctioned terminal, the missing dual-use licence and a flagged forwarder. The Arbiter reroutes via the Trans-Caspian Middle Corridor, with release held until the licence clears.
3. **Biologics vs. a jammed Panama Canal:** $31M of 2-8 °C vials, Antwerp → Los Angeles. A 12-16 day canal queue would outlast the reefer gensets. The Arbiter pivots to a sea-to-Houston plus reefer-truck landbridge.

Intelligence bulletins in the scenarios are **simulated for demonstration**.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Engines
- **Replay (default, demo-safe):** streams pre-recorded agent output. It needs no network and produces the same result every run.
- **Live (Claude API):** calls Claude with the prompts in `agents.py`. Set `ANTHROPIC_API_KEY` as an environment variable, in `.streamlit/secrets.toml`, or in the sidebar. If a live call fails mid-demo, that run switches to replay automatically.

Terminal version:

```bash
python pipeline.py --scenario red_sea          # replay
python pipeline.py --scenario embargo --live   # live Claude
```

## Deploy on Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → pick this repo, branch `main`, file `app.py`.
2. (Optional, for live mode) under **Advanced settings → Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

## Files
- `agents.py`: the three agent prompts and the context each agent sees
- `pipeline.py`: the sequential loop, the replay and Claude backends, auto-fallback and CLI
- `scenarios.py`: manifests, route library (with map geometry), simulated intel and replay scripts
- `app.py`: the Streamlit live view
