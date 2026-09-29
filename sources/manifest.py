"""
Shipper manifest loader: JSON or CSV exports from a TMS/ERP, normalized to the
manifest fields the agents use. Unknown fields are kept and passed through.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime

ALIASES = {
    "shipment_id": ["shipment_id", "shipment", "booking", "booking_ref", "reference", "ref", "id"],
    "shipper": ["shipper", "shipper_name", "exporter", "seller"],
    "consignee": ["consignee", "consignee_name", "importer", "buyer"],
    "notify_party": ["notify_party", "notify", "notify_party_name"],
    "forwarder": ["forwarder", "freight_forwarder"],
    "end_user": ["end_user", "ultimate_consignee"],
    "origin": ["origin", "port_of_loading", "pol", "origin_port", "from"],
    "destination": ["destination", "port_of_discharge", "pod", "destination_port", "place_of_delivery", "to"],
    "destination_country": ["destination_country", "country_of_destination"],
    "cargo": ["cargo", "commodity", "description", "goods_description", "cargo_description"],
    "hs_code": ["hs_code", "hs", "hscode", "hts", "tariff_code"],
    "containers": ["containers", "equipment", "container_count"],
    "declared_value_usd": ["declared_value_usd", "value_usd", "cargo_value", "value", "invoice_value"],
    "incoterm": ["incoterm", "incoterms"],
    "deadline_days": ["deadline_days", "deadline", "required_by", "delivery_by", "due_date"],
    "export_licence": ["export_licence", "export_license", "licence", "license", "licence_number"],
    "insurance": ["insurance", "insurance_terms"],
    "temperature_tolerance": ["temperature_tolerance", "temperature", "reefer_setpoint"],
    "priority_note": ["priority_note", "notes", "special_instructions"],
}
REQUIRED = ("origin", "destination", "cargo")


def _key(k: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", k.strip().lower()).strip("_")


def _to_days(v) -> int | None:
    s = str(v).strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return max(0, (datetime.strptime(s, fmt).date() - date.today()).days)
        except ValueError:
            continue
    return None


def normalize(raw: dict) -> dict:
    flat = {_key(k): v for k, v in raw.items() if v not in (None, "")}
    out: dict = {}
    used = set()
    for field, names in ALIASES.items():
        for n in names:
            if n in flat:
                out[field] = flat[n]
                used.add(n)
                break
    for k, v in flat.items():  # keep anything else (parties, notes...)
        if k not in used:
            out.setdefault(k, v)
    if "declared_value_usd" in out:
        try:
            out["declared_value_usd"] = int(float(re.sub(r"[^\d.]", "", str(out["declared_value_usd"]))))
        except ValueError:
            pass
    if "deadline_days" in out:
        out["deadline_days"] = _to_days(out["deadline_days"]) or out["deadline_days"]
    if isinstance(out.get("parties"), str):
        out["parties"] = [p.strip() for p in out["parties"].split("|") if p.strip()]
    missing = [f for f in REQUIRED if not out.get(f)]
    if missing:
        raise ValueError(f"manifest is missing required field(s): {', '.join(missing)}")
    out.setdefault("shipment_id", "UPLOAD-1")
    return out


def load_manifest(content: str, filename: str = "manifest.json") -> dict:
    """JSON object, or CSV either as one header row + one data row, or as key,value pairs."""
    if filename.lower().endswith(".json") or content.lstrip().startswith("{"):
        return normalize(json.loads(content))
    rows = list(csv.reader(io.StringIO(content.lstrip("﻿"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if rows and len(rows[0]) == 2 and _key(rows[0][0]) in ("field", "key", "name"):
        rows = rows[1:]
    if rows and all(len(r) == 2 for r in rows) and len(rows) > 2:
        return normalize({r[0]: r[1] for r in rows})
    return normalize(dict(zip(rows[0], rows[1])))
