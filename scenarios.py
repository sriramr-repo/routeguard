"""
Hardcoded demo scenarios. No live scraping: everything the agents need is here.

Each scenario has:
  manifest  - the shipment
  routes    - candidate route library (the only routes agents may choose)
              legs: list of {"mode": sea|land|air, "pts": [(lat, lon), ...]} for the map
  intel     - SIMULATED intelligence bulletins (clearly labelled as such in the UI)
  hotspots  - map markers that light up red when the Critic fires
  script    - pre-recorded agent output for Replay mode (demo-safe, identical every run)
"""

# ---------------------------------------------------------------- shared sea lanes
_MALACCA = [(1.26, 103.8), (3.5, 100.5), (5.8, 95.0)]
_TW_TO_SG = [(22.6, 120.3), (15.0, 114.0), (5.0, 106.0)]
_RED_SEA_NB = [(12.4, 45.0), (12.6, 43.3), (15.0, 41.8), (20.0, 38.5), (27.5, 34.0),
               (29.95, 32.55), (31.26, 32.3)]
_MED_WB = [(34.0, 25.0), (37.2, 11.0), (37.5, 3.0), (36.0, -5.6)]
_IBERIA_TO_NL = [(37.0, -10.0), (43.5, -10.0), (48.5, -5.5), (50.0, -1.0), (51.95, 4.1)]
_WEST_AFRICA_NB = [(-33.9, 18.4), (-20.0, 5.0), (-5.0, -5.0), (10.0, -20.0), (28.0, -19.0)]
_HH_TO_GIB = [(53.55, 9.97), (54.0, 8.0), (51.5, 2.0), (50.0, -1.0), (48.5, -5.5),
              (43.5, -10.0), (37.0, -10.0), (36.0, -5.6)]
_MED_EB = [(37.5, 3.0), (37.2, 11.0), (34.0, 25.0), (31.26, 32.3)]
_RED_SEA_SB = list(reversed(_RED_SEA_NB))


SCENARIOS = {
    # ============================================================== 1. RED SEA / SUEZ
    "red_sea": {
        "title": "Microchips vs. the Red Sea",
        "tagline": "$48M of advanced ICs, Kaohsiung to Rotterdam, 32-day window",
        "manifest": {
            "shipment_id": "RG-24817",
            "shipper": "Semiconductor supplier, Kaohsiung (TW)",
            "consignee": "Automotive Tier-1 electronics plant, Eindhoven (NL)",
            "origin": "Kaohsiung, TW",
            "destination": "Rotterdam, NL",
            "cargo": "Advanced logic ICs and automotive microcontrollers (HS 8542.31)",
            "containers": "6 x 40' HC, ESD-safe, high-security seals",
            "declared_value_usd": 48_000_000,
            "incoterm": "CIP Rotterdam",
            "deadline_days": 32,
            "priority_note": "Container #6 (MCU lot) is line-critical: plant stops if it is not in Eindhoven by day 25",
            "insurance": "All-risks cargo policy; war & strikes cover subject to listed-area exclusions",
        },
        "routes": {
            "SUEZ_FAST": {
                "id": "SUEZ_FAST", "name": "Suez Express",
                "via": ["Kaohsiung", "Singapore", "Colombo", "Bab el-Mandeb", "Suez Canal", "Rotterdam"],
                "transit_days": 23, "est_cost_usd": 410_000,
                "notes": "Shortest distance; Colombo transshipment; includes canal dues",
                "legs": [{"mode": "sea", "pts": _TW_TO_SG + _MALACCA + [(6.95, 79.85), (12.0, 60.0)]
                          + _RED_SEA_NB + _MED_WB + _IBERIA_TO_NL}],
            },
            "CAPE_STD": {
                "id": "CAPE_STD", "name": "Cape of Good Hope standard",
                "via": ["Kaohsiung", "Singapore", "Port Louis", "Cape Town", "Tangier", "Rotterdam"],
                "transit_days": 37, "est_cost_usd": 455_000,
                "notes": "Extra ~3,500 nm vs Suez; 5 port calls",
                "legs": [{"mode": "sea", "pts": _TW_TO_SG + _MALACCA + [(-5.0, 80.0), (-20.16, 57.5),
                          (-30.0, 40.0), (-35.5, 20.0)] + _WEST_AFRICA_NB
                          + [(35.8, -5.8), (37.0, -10.0)] + _IBERIA_TO_NL[1:]}],
            },
            "CAPE_EXPRESS": {
                "id": "CAPE_EXPRESS", "name": "Cape of Good Hope express",
                "via": ["Kaohsiung", "Singapore", "Cape Town", "Rotterdam"],
                "transit_days": 30, "est_cost_usd": 540_000,
                "notes": "Premium service, only 2 intermediate calls, higher bunker burn; no Colombo transshipment",
                "legs": [{"mode": "sea", "pts": _TW_TO_SG + _MALACCA + [(-10.0, 80.0), (-30.0, 45.0),
                          (-35.5, 20.0)] + _WEST_AFRICA_NB + _IBERIA_TO_NL}],
            },
            "AIR_ALL": {
                "id": "AIR_ALL", "name": "Full air freight TPE-AMS",
                "via": ["Taipei", "Amsterdam"],
                "transit_days": 3, "est_cost_usd": 2_900_000,
                "notes": "~96 t chargeable weight; ~$62k per single container-load",
                "legs": [{"mode": "air", "pts": [(25.08, 121.23), (52.31, 4.76)]}],
            },
        },
        "intel": [
            {"id": "RS-01", "time": "T-6h", "source": "Maritime security advisory", "severity": "CRITICAL",
             "text": "Two merchant vessels struck by one-way attack drones 40-60 nm NW of Bab el-Mandeb in the last 72h; one crew fatality. Threat level southern Red Sea / Gulf of Aden: SEVERE."},
            {"id": "RS-02", "time": "T-5h", "source": "War-risk underwriting circular", "severity": "CRITICAL",
             "text": "Additional war-risk premium for Red Sea transits raised to 1.0% of insured value per voyage (from 0.5%). Several underwriters declining cargo above $25M."},
            {"id": "RS-03", "time": "T-4h", "source": "Cargo insurer notice", "severity": "HIGH",
             "text": "Policyholder's all-risks cargo cover: war & strikes cover SUSPENDED for listed area 'Southern Red Sea & Gulf of Aden' effective 00:00 UTC."},
            {"id": "RS-04", "time": "T-3h", "source": "Port labour monitor", "severity": "HIGH",
             "text": "Canal-zone tug and pilot unions announce a 72-hour stoppage from Thursday over hazard pay; northbound convoy slots expected to slip 3-5 days."},
            {"id": "RS-05", "time": "T-2h", "source": "Carrier advisory", "severity": "MEDIUM",
             "text": "3 of the top-5 container lines suspending Red Sea routing; ships already at sea being diverted mid-voyage via the Cape, adding 10-14 days without notice."},
            {"id": "RS-06", "time": "T-1h", "source": "Cargo crime index", "severity": "MEDIUM",
             "text": "High-value electronics theft at transshipment hubs up 28% YoY; Colombo transshipment yard flagged for seal-tamper incidents."},
        ],
        "hotspots": [
            {"name": "Bab el-Mandeb", "lat": 12.6, "lon": 43.3, "label": "Drone attacks (RS-01)"},
            {"name": "Suez Canal", "lat": 30.5, "lon": 32.35, "label": "Tug & pilot strike (RS-04)"},
            {"name": "Colombo", "lat": 6.95, "lon": 79.85, "label": "Seal tampering (RS-06)"},
        ],
        "map_center": {"lat": 15, "lon": 60, "scale": 1.3},
        "script": {
            "optimizer": {
                "narration": (
                    "Six containers of advanced logic ICs, $48 million declared, 32-day window into Rotterdam. "
                    "The obvious play is the Suez Express: Kaohsiung, Singapore, Colombo, straight up the Red Sea and through the canal. "
                    "That's 23 days, nine days of buffer, and at $410,000 it's the cheapest ocean option on the table. "
                    "The Cape standard loop is $45,000 more and lands at 37 days, which blows the deadline. "
                    "Cape express makes it in 30 days, but it costs $130,000 more for no reason I can see. "
                    "Full air is $2.9 million for 96 tonnes. Not happening. "
                    "I'm locking in Suez: fastest, cheapest, and it even covers the day-25 need for container six."
                ),
                "json": {"route_id": "SUEZ_FAST", "transit_days": 23, "est_cost_usd": 410_000,
                         "meets_deadline": True,
                         "rationale": "Fastest and cheapest ocean option with 9 days of buffer."},
            },
            "critic": {
                "narration": (
                    "Stop. This route sails straight into a live combat zone. "
                    "Two merchant ships were hit by drones near Bab el-Mandeb in the last 72 hours, one crew member killed, threat level SEVERE (RS-01). "
                    "Worse, our own cargo insurer just suspended war and strikes cover for exactly that stretch of water (RS-03), so $48 million of microchips would cross it effectively uninsured. "
                    "If we can even find an underwriter, the war-risk premium is now 1% of insured value: $480,000, more than the entire freight bill (RS-02). "
                    "Then the canal itself: tug and pilot unions start a 72-hour strike on Thursday, slipping convoy slots three to five days (RS-04). "
                    "That pushes 23 days to 28 and misses the day-25 window for the line-critical container. "
                    "And carriers are diverting ships around the Cape mid-voyage anyway, which could land us at 37 days with no warning (RS-05). "
                    "Verdict: REJECT."
                ),
                "json": {
                    "verdict": "REJECT", "risk_score": 92,
                    "flags": [
                        {"severity": "CRITICAL", "category": "Security", "title": "Active drone attacks at Bab el-Mandeb",
                         "detail": "The route crosses the exact corridor where two ships were hit in 72 hours; threat level SEVERE. Crew and $48M of cargo exposed.",
                         "evidence": "RS-01"},
                        {"severity": "CRITICAL", "category": "Insurance", "title": "Cargo effectively uninsured in transit",
                         "detail": "War & strikes cover is suspended for the listed area. A single incident leaves the full $48M declared value uncovered.",
                         "evidence": "RS-03, manifest.insurance"},
                        {"severity": "HIGH", "category": "Insurance", "title": "War-risk premium adds $480,000",
                         "detail": "1.0% of $48M insured value per voyage = $480,000, more than the freight bill. Real Suez cost is ~$890,000, not $410,000.",
                         "evidence": "RS-02"},
                        {"severity": "HIGH", "category": "Labor", "title": "72-hour canal tug and pilot strike",
                         "detail": "Convoy slots slip 3-5 days: transit becomes 26-28 days, missing the day-25 deadline for line-critical container #6.",
                         "evidence": "RS-04, manifest.priority_note"},
                        {"severity": "MEDIUM", "category": "Canal/Port", "title": "Mid-voyage Cape diversion risk",
                         "detail": "Carriers are diverting ships already at sea, adding 10-14 days without notice: worst case 37 days, 5 days late.",
                         "evidence": "RS-05"},
                        {"severity": "MEDIUM", "category": "Cargo", "title": "Seal tampering at Colombo transshipment",
                         "detail": "High-value electronics theft at hubs up 28% YoY; Colombo yard specifically flagged.",
                         "evidence": "RS-06"},
                    ],
                },
            },
            "arbiter": {
                "narration": (
                    "The Optimizer is right that speed matters, and the Critic is right that the Suez plan isn't what it looks like. "
                    "Price in the $480,000 war-risk premium and Suez really costs about $890,000, while still carrying an uninsured $48 million exposure and a strike delay. "
                    "Cape of Good Hope express sails outside every listed war-risk area, so our standard cover applies with no surcharge. "
                    "With only two port calls it also skips the Colombo yard flagged for seal tampering. "
                    "It lands in 30 days, inside the 32-day deadline. "
                    "The one thing it can't do is hit day 25 for container six, so we fly that container Taipei to Amsterdam for about $62,000 and it arrives on day 3. "
                    "Total: $602,000, fully insured, on time. Decision: pivot."
                ),
                "json": {
                    "decision": "PIVOT", "final_route_id": "CAPE_EXPRESS", "transit_days": 30,
                    "est_cost_usd": 602_000, "residual_risk_score": 16, "meets_deadline": True,
                    "mitigations": [
                        "Book Cape of Good Hope express (2 calls, no Colombo transshipment)",
                        "Air-freight line-critical container #6 TPE to AMS: +$62,000, lands day 3",
                        "Standard war & strikes cover applies outside listed areas: no surcharge",
                        "GPS-tracked high-security seals with door-event alerts",
                        "Re-assess at Cape Town if Red Sea threat level drops",
                    ],
                    "summary": "Go around the Cape of Good Hope and fly the line-critical container: 30 days, $602k all-in and fully insured, versus ~$890k and an uninsured $48M through Suez.",
                },
            },
        },
    },

    # ============================================================== 2. EMBARGOED PORT
    "embargo": {
        "title": "Dual-use machine tools via a newly sanctioned port",
        "tagline": "$6.4M of 5-axis CNC centres, Hamburg to Tashkent, 45-day window",
        "manifest": {
            "shipment_id": "RG-31552",
            "shipper": "Machine-tool OEM, Stuttgart (DE)",
            "consignee": "Tashkent Precision Components LLC (UZ)",
            "notify_party": "Gulf Link Freight FZE, Dubai (forwarder)",
            "origin": "Hamburg, DE",
            "destination": "Tashkent, UZ (inland, rail terminal)",
            "cargo": "3 x 5-axis CNC machining centres + spindle spares (HS 8457.10)",
            "containers": "3 x 40' flat rack, 2 x 40' HC",
            "declared_value_usd": 6_400_000,
            "incoterm": "DAP Tashkent",
            "deadline_days": 45,
            "export_licence": "None filed (shipper self-classified as non-listed)",
            "stated_end_use": "Automotive components",
        },
        "routes": {
            "GULF_IRAN": {
                "id": "GULF_IRAN", "name": "Gulf gateway via Bandar Abbas",
                "via": ["Hamburg", "Suez Canal", "Jebel Ali", "Bandar Abbas", "Mashhad", "Tashkent"],
                "transit_days": 27, "est_cost_usd": 118_000,
                "notes": "Transship at Jebel Ali, feeder to Bandar Abbas terminal, rail north via Sarakhs border",
                "legs": [
                    {"mode": "sea", "pts": _HH_TO_GIB + _MED_EB + _RED_SEA_SB + [(14.0, 52.0), (18.0, 58.0),
                     (22.6, 60.0), (24.8, 58.0), (26.5, 56.4), (25.0, 55.06), (27.15, 56.2)]},
                    {"mode": "land", "pts": [(27.15, 56.2), (36.3, 59.6), (36.53, 61.16), (37.6, 61.8),
                     (39.77, 64.4), (39.65, 66.96), (41.3, 69.24)]},
                ],
            },
            "MIDDLE_CORRIDOR": {
                "id": "MIDDLE_CORRIDOR", "name": "Trans-Caspian Middle Corridor",
                "via": ["Hamburg", "Bosporus", "Poti", "Baku", "Aktau", "Tashkent"],
                "transit_days": 36, "est_cost_usd": 164_000,
                "notes": "Sea to Georgia, rail across the Caucasus, Caspian ferry Alat-Aktau, rail via Kazakhstan",
                "legs": [
                    {"mode": "sea", "pts": _HH_TO_GIB + [(37.5, 3.0), (37.2, 11.0), (36.5, 15.5), (36.0, 22.5),
                     (37.5, 25.0), (39.5, 25.8), (40.2, 26.4), (40.8, 28.0), (41.1, 29.05), (42.0, 33.0),
                     (42.3, 38.0), (42.15, 41.67)]},
                    {"mode": "land", "pts": [(42.15, 41.67), (41.7, 44.8), (39.95, 49.4)]},
                    {"mode": "sea", "pts": [(39.95, 49.4), (43.65, 51.2)]},
                    {"mode": "land", "pts": [(43.65, 51.2), (45.3, 55.2), (43.08, 58.9), (42.46, 59.6),
                     (39.77, 64.4), (41.3, 69.24)]},
                ],
            },
            "CHINA_LANDBRIDGE": {
                "id": "CHINA_LANDBRIDGE", "name": "Sea to Lianyungang + China-Central Asia rail",
                "via": ["Hamburg", "Suez Canal", "Singapore", "Lianyungang", "Khorgos", "Tashkent"],
                "transit_days": 49, "est_cost_usd": 149_000,
                "notes": "Very long sea leg plus ~4,500 km of rail; misses the deadline",
                "legs": [
                    {"mode": "sea", "pts": _HH_TO_GIB + _MED_EB + _RED_SEA_SB + [(12.0, 60.0), (6.95, 79.85),
                     (5.8, 95.0), (3.5, 100.5), (1.26, 103.8), (10.0, 110.0), (22.0, 117.0), (30.0, 123.5),
                     (34.6, 119.4)]},
                    {"mode": "land", "pts": [(34.6, 119.4), (34.3, 108.9), (36.06, 103.8), (43.8, 87.6),
                     (44.2, 80.3), (43.24, 76.9), (41.3, 69.24)]},
                ],
            },
        },
        "intel": [
            {"id": "EM-01", "time": "T-9h", "source": "Sanctions watch", "severity": "CRITICAL",
             "text": "New designation effective today: the Bandar Abbas container terminal operator and two affiliated feeder lines added to EU and UK sanctions lists. Asset freeze and prohibition on making goods available, directly or indirectly."},
            {"id": "EM-02", "time": "T-7h", "source": "Export-control bulletin", "severity": "CRITICAL",
             "text": "Reminder: 5-axis machine tools meeting positioning-accuracy thresholds are dual-use items (EU Annex I, 2B001). EU export requires an individual licence; catch-all applies to routing via high-risk jurisdictions."},
            {"id": "EM-03", "time": "T-5h", "source": "Denied-party screening", "severity": "HIGH",
             "text": "Screening hit: notify party 'Gulf Link Freight FZE' shares a registered address with an entity listed for procurement diversion."},
            {"id": "EM-04", "time": "T-4h", "source": "P&I / cargo insurer notice", "severity": "HIGH",
             "text": "Marine and cargo policies exclude any voyage or cargo exposing the insurer to sanctions; no cover for calls at designated terminals."},
            {"id": "EM-05", "time": "T-2h", "source": "Corridor monitor", "severity": "MEDIUM",
             "text": "Middle Corridor: Caspian ferry Alat-Aktau running 2-3 day waits; Poti rail link normal; Kazakh rail transit 6-7 days."},
            {"id": "EM-06", "time": "T-1h", "source": "Maritime security advisory", "severity": "MEDIUM",
             "text": "Red Sea threat level SEVERE; carriers routing Europe-Gulf cargo via the Cape, adding 10-12 days."},
        ],
        "hotspots": [
            {"name": "Bandar Abbas", "lat": 27.15, "lon": 56.2, "label": "Sanctioned terminal (EM-01)"},
            {"name": "Dubai", "lat": 25.2, "lon": 55.3, "label": "Flagged forwarder (EM-03)"},
            {"name": "Bab el-Mandeb", "lat": 12.6, "lon": 43.3, "label": "SEVERE threat (EM-06)"},
        ],
        "map_center": {"lat": 35, "lon": 38, "scale": 2.0},
        "script": {
            "optimizer": {
                "narration": (
                    "Five boxes of CNC machining centres, $6.4 million, Hamburg to Tashkent, 45-day window. "
                    "Tashkent is landlocked, so this is a sea-plus-rail job. "
                    "Fastest option is the Gulf gateway: ship to Jebel Ali, feeder across to Bandar Abbas, then rail north through Mashhad straight into Uzbekistan. "
                    "That's 27 days and $118,000, the cheapest option by a mile. "
                    "The Middle Corridor through Georgia and the Caspian works, but it's $46,000 more and takes 36 days. "
                    "The China landbridge misses the deadline outright at 49 days. "
                    "Gulf gateway it is: 18 days of buffer and the lowest freight bill."
                ),
                "json": {"route_id": "GULF_IRAN", "transit_days": 27, "est_cost_usd": 118_000,
                         "meets_deadline": True,
                         "rationale": "Cheapest and fastest sea-rail combination with 18 days of buffer."},
            },
            "critic": {
                "narration": (
                    "This plan is illegal before it leaves Hamburg. "
                    "As of today, the Bandar Abbas terminal operator and its feeder lines are on the EU and UK sanctions lists (EM-01). Routing cargo through them is making goods available to a designated party. "
                    "Even without that, these are 5-axis machining centres, which are dual-use items under category 2B001, and the manifest says no export licence was filed (EM-02). "
                    "Now look at the notify party: Gulf Link Freight shares a registered address with a known procurement-diversion entity (EM-03). "
                    "Dual-use tools, a Dubai forwarder, transshipment through a sanctioned port: that is a textbook diversion pattern. "
                    "Our insurers won't cover it either (EM-04), and the Red Sea leg adds a severe security risk on top (EM-06). "
                    "The penalties here are criminal, not commercial. REJECT, and put a compliance hold on the whole shipment."
                ),
                "json": {
                    "verdict": "REJECT", "risk_score": 98,
                    "flags": [
                        {"severity": "CRITICAL", "category": "Sanctions", "title": "Transshipment via newly sanctioned terminal",
                         "detail": "The Bandar Abbas terminal operator and feeder lines were designated today. Using them makes goods available to a sanctioned party: criminal exposure for shipper and carrier.",
                         "evidence": "EM-01"},
                        {"severity": "CRITICAL", "category": "Export Control", "title": "Dual-use machine tools without a licence",
                         "detail": "5-axis machining centres fall under 2B001 and need an individual licence. Manifest shows 'None filed'.",
                         "evidence": "EM-02, manifest.export_licence"},
                        {"severity": "HIGH", "category": "Sanctions", "title": "Notify party matches diversion network",
                         "detail": "Gulf Link Freight FZE shares a registered address with a listed procurement-diversion entity: a classic re-export red flag.",
                         "evidence": "EM-03, manifest.notify_party"},
                        {"severity": "HIGH", "category": "Insurance", "title": "No cover for a sanctioned voyage",
                         "detail": "Cargo and P&I policies are void for calls at designated terminals: $6.4M uninsured.",
                         "evidence": "EM-04"},
                        {"severity": "MEDIUM", "category": "Security", "title": "Red Sea leg at SEVERE threat",
                         "detail": "The route transits the Red Sea; a Cape diversion would add 10-12 days.",
                         "evidence": "EM-06"},
                    ],
                },
            },
            "arbiter": {
                "narration": (
                    "No version of the Gulf route can be executed: a sanctioned terminal and unlicensed dual-use goods are hard stops, whatever the savings. "
                    "The Middle Corridor avoids every designated party and every war-risk area: sea to Poti through the Bosporus, rail across Georgia to Baku, the Caspian ferry to Aktau, then rail to Tashkent. "
                    "At 36 days, including the current two-to-three-day ferry wait, it still fits the 45-day deadline, for $164,000. "
                    "But no cargo moves until the paperwork is clean. "
                    "We file the dual-use licence with a signed end-user certificate from the Tashkent consignee, and we drop Gulf Link Freight for a screened forwarder. "
                    "The booking is made now and the cargo is released only when the licence is granted; the licence clock is the real deadline risk. "
                    "Decision: pivot, behind a compliance gate."
                ),
                "json": {
                    "decision": "PIVOT", "final_route_id": "MIDDLE_CORRIDOR", "transit_days": 36,
                    "est_cost_usd": 164_000, "residual_risk_score": 26, "meets_deadline": True,
                    "mitigations": [
                        "Compliance gate: release only after dual-use (2B001) licence is granted",
                        "Obtain a signed end-user certificate from the Tashkent consignee",
                        "Replace notify party Gulf Link Freight FZE with a screened forwarder",
                        "Re-screen all parties against EU/UK/US lists at booking and each handover",
                        "Hold a 3-day buffer for the Caspian ferry queue at Alat",
                    ],
                    "summary": "Reroute through the Trans-Caspian Middle Corridor and gate release on a dual-use licence: 36 days, $164k, no sanctioned party touched.",
                },
            },
        },
    },

    # ============================================================== 3. COLD CHAIN / PANAMA
    "cold_chain": {
        "title": "Biologics vs. a jammed Panama Canal",
        "tagline": "$31M of 2-8°C antibody vials, Antwerp to Los Angeles, 28-day window",
        "manifest": {
            "shipment_id": "RG-40978",
            "shipper": "Biologics manufacturer, Geel (BE)",
            "consignee": "Pharma distribution centre, Ontario, CA (US)",
            "origin": "Antwerp, BE",
            "destination": "Los Angeles, US",
            "cargo": "Monoclonal antibody vials, 2-8°C (HS 3002.15)",
            "containers": "4 x 40' reefer, set point +5°C, genset-equipped",
            "declared_value_usd": 31_000_000,
            "incoterm": "CIP Los Angeles",
            "deadline_days": 28,
            "temperature_tolerance": "Product destroyed after >2h continuous outside 2-8°C",
        },
        "routes": {
            "PANAMA": {
                "id": "PANAMA", "name": "All-water via Panama Canal",
                "via": ["Antwerp", "Cristóbal", "Panama Canal", "Balboa", "Los Angeles"],
                "transit_days": 21, "est_cost_usd": 96_000,
                "notes": "Single vessel, no rehandling; canal transit on first-come queue (no reserved slot)",
                "legs": [{"mode": "sea", "pts": [(51.27, 4.35), (51.4, 3.0), (50.5, 0.0), (49.5, -5.0),
                          (45.0, -20.0), (35.0, -45.0), (24.0, -62.0), (18.3, -64.3), (14.0, -72.0),
                          (11.0, -77.0), (9.35, -79.92), (9.1, -79.7), (8.95, -79.57), (7.5, -79.3),
                          (6.5, -81.0), (10.0, -90.0), (18.0, -104.0), (25.0, -113.0), (32.0, -118.0),
                          (33.73, -118.26)]}],
            },
            "HOUSTON_BRIDGE": {
                "id": "HOUSTON_BRIDGE", "name": "Sea to Houston + reefer truck landbridge",
                "via": ["Antwerp", "Houston", "San Antonio", "El Paso", "Phoenix", "Los Angeles"],
                "transit_days": 23, "est_cost_usd": 142_000,
                "notes": "17 days sea, ~2 days port & customs, ~2.5 days team-driver reefer trucking on I-10",
                "legs": [
                    {"mode": "sea", "pts": [(51.27, 4.35), (51.4, 3.0), (50.5, 0.0), (49.5, -5.0),
                     (40.0, -40.0), (30.0, -65.0), (28.0, -78.0), (25.5, -79.8), (24.2, -81.5),
                     (24.5, -84.0), (27.0, -90.0), (28.9, -94.5), (29.73, -95.0)]},
                    {"mode": "land", "pts": [(29.73, -95.0), (29.42, -98.49), (31.76, -106.49),
                     (33.45, -112.07), (33.73, -118.26)]},
                ],
            },
            "AIR_PHARMA": {
                "id": "AIR_PHARMA", "name": "Pharma air freight BRU-LAX",
                "via": ["Brussels", "Los Angeles"],
                "transit_days": 2, "est_cost_usd": 468_000,
                "notes": "Active temperature-controlled ULDs",
                "legs": [{"mode": "air", "pts": [(50.9, 4.48), (33.94, -118.41)]}],
            },
        },
        "intel": [
            {"id": "CC-01", "time": "T-8h", "source": "Canal operations notice", "severity": "CRITICAL",
             "text": "Gatún Lake below operating level after the dry season: maximum draft cut to 44 ft and daily transits reduced from 36 to 24. Unreserved vessels facing 12-16 day queues."},
            {"id": "CC-02", "time": "T-6h", "source": "Vessel schedule update", "severity": "HIGH",
             "text": "Booked vessel (47 ft loaded draft) must offload ~1,200 TEU at Cristóbal to meet the draft limit; deck-bay reefers not guaranteed onward space."},
            {"id": "CC-03", "time": "T-4h", "source": "Reefer operations", "severity": "HIGH",
             "text": "Genset fuel autonomy on queued vessels ~9-10 days; refuelling at anchorage limited. 3 reefer temperature excursions reported in the queue this month."},
            {"id": "CC-04", "time": "T-3h", "source": "Weather service", "severity": "MEDIUM",
             "text": "Tropical storm forecast to cross the Caribbean approach to Colón in 5-7 days; possible 48h anchorage closures."},
            {"id": "CC-05", "time": "T-1h", "source": "Gulf ports monitor", "severity": "MEDIUM",
             "text": "Port Houston reefer terminal operating normally; pre-cooled cross-dock capacity available with 24h booking."},
        ],
        "hotspots": [
            {"name": "Panama Canal", "lat": 9.1, "lon": -79.7, "label": "12-16 day queue (CC-01)"},
            {"name": "Colón approach", "lat": 12.5, "lon": -77.5, "label": "Tropical storm (CC-04)"},
        ],
        "map_center": {"lat": 28, "lon": -60, "scale": 1.6},
        "script": {
            "optimizer": {
                "narration": (
                    "Four reefers of antibody vials, $31 million, Antwerp to Los Angeles, 28-day window. "
                    "All-water through the Panama Canal is the natural choice: 21 days, one ship, and no rehandling of temperature-sensitive boxes. "
                    "It's also the cheapest at $96,000. "
                    "The Houston landbridge is two days slower and $46,000 more because of the trucking leg. "
                    "Air is $468,000, five times the ocean cost. "
                    "Panama gives us a week of buffer at the lowest price. Booking it."
                ),
                "json": {"route_id": "PANAMA", "transit_days": 21, "est_cost_usd": 96_000,
                         "meets_deadline": True,
                         "rationale": "Cheapest, single-vessel routing with 7 days of buffer and no rehandling."},
            },
            "critic": {
                "narration": (
                    "That week of buffer doesn't exist. "
                    "The canal has cut daily transits from 36 to 24 because Gatún Lake is too low, and ships without a reserved slot are queueing 12 to 16 days (CC-01). "
                    "We don't have a slot. That turns 21 days into 33 to 37, up to nine days late. "
                    "It gets worse for this cargo: gensets on queued ships last about 9 to 10 days (CC-03). "
                    "When they run dry the vials leave 2 to 8 degrees, and after two hours $31 million of biologics is scrap. "
                    "Our vessel also has to offload about 1,200 boxes at Cristóbal to meet the draft limit, and deck reefers aren't guaranteed a slot onward (CC-02). "
                    "And a tropical storm is heading for the Colón approach right in our queue window (CC-04). REJECT."
                ),
                "json": {
                    "verdict": "REJECT", "risk_score": 84,
                    "flags": [
                        {"severity": "CRITICAL", "category": "Canal/Port", "title": "12-16 day queue at the canal",
                         "detail": "Unreserved vessels wait 12-16 days. 21 days becomes 33-37: 5-9 days past the 28-day deadline.",
                         "evidence": "CC-01, route notes"},
                        {"severity": "CRITICAL", "category": "Cargo", "title": "Reefer power runs out in the queue",
                         "detail": "Genset autonomy ~9-10 days vs a 12-16 day wait. Product is destroyed after 2h outside 2-8°C: $31M at risk.",
                         "evidence": "CC-03, manifest.temperature_tolerance"},
                        {"severity": "HIGH", "category": "Canal/Port", "title": "Boxes may be offloaded for draft",
                         "detail": "Vessel must drop ~1,200 TEU at Cristóbal; deck-bay reefers have no guaranteed onward slot.",
                         "evidence": "CC-02"},
                        {"severity": "MEDIUM", "category": "Canal/Port", "title": "Tropical storm at the Colón approach",
                         "detail": "A possible 48h anchorage closure lands inside our queue window.",
                         "evidence": "CC-04"},
                    ],
                },
            },
            "arbiter": {
                "narration": (
                    "The canal isn't a 21-day route this month. It's a 33-plus-day route with a real chance of losing the entire cargo. "
                    "The Houston landbridge avoids the canal completely: 17 days at sea to a Gulf port that's running normally with pre-cooled cross-dock capacity (CC-05). "
                    "From there, team-driver reefer trucks run non-stop on I-10 to Los Angeles. "
                    "It lands in 23 days, five days inside the deadline, for $142,000. "
                    "That's $46,000 more than the canal quote, set against $31 million of product at risk. "
                    "We add live temperature loggers with alerts and a standby reefer unit in Houston. "
                    "Decision: pivot to the landbridge."
                ),
                "json": {
                    "decision": "PIVOT", "final_route_id": "HOUSTON_BRIDGE", "transit_days": 23,
                    "est_cost_usd": 142_000, "residual_risk_score": 14, "meets_deadline": True,
                    "mitigations": [
                        "Book pre-cooled cross-dock at Port Houston (24h notice)",
                        "Team-driver reefer trucks, non-stop I-10 to Los Angeles",
                        "Live IoT temperature loggers with 15-minute excursion alerts",
                        "Standby reefer unit and genset at the Houston cross-dock",
                    ],
                    "summary": "Skip the jammed canal: sea to Houston, then reefer trucks to LA in 23 days for $142k, protecting $31M of biologics.",
                },
            },
        },
    },
}
