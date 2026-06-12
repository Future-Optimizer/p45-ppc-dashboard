#!/usr/bin/env python3
"""
fetch_google_ads_data.py

Extrage date din Google Ads API si genereaza ../ppc-data.js, fisierul de
date consumat de ppc-dashboard-live.html.

Necesita:
  - config/google-ads.yaml completat (vezi google-ads.yaml.template)
  - config/accounts.json completat (customer_ids + optional destination_mapping)

Instalare:
  pip install -r requirements.txt

Rulare:
  python fetch_google_ads_data.py                 # genereaza toate perioadele
  python fetch_google_ads_data.py --period 7d     # perioada implicita activa = ultimele 7 zile

Scriptul genereaza datele pentru TOATE perioadele suportate (azi, 7/14/30/90
zile, luna aceasta, luna trecuta, tot timpul) intr-un singur fisier
ppc-data.js, sub window.PPC_DATA_BY_PERIOD. Argumentul --period seteaza doar
care perioada e activa la prima incarcare a dashboardului
(window.PPC_DATA) — comutarea intre perioade in dashboard se face instant,
fara a rula din nou scriptul.

Dupa rulare, deschide/reincarca ppc-dashboard-live.html pentru a vedea
datele actualizate.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    print("Lipseste pachetul 'google-ads'. Ruleaza: pip install -r requirements.txt")
    sys.exit(1)


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
GOOGLE_ADS_YAML = CONFIG_DIR / "google-ads.yaml"
ACCOUNTS_JSON = CONFIG_DIR / "accounts.json"
OUTPUT_JS = BASE_DIR / "ppc-data.js"

RO_MONTHS = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]

RO_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PERIOD_KEYS = ["today", "7d", "14d", "30d", "90d", "this_month", "last_month", "all_time"]

NOT_CONNECTED_PLATFORM = {
    "name": None,  # filled per platform
    "status": "not_connected",
    "status_label": "⚠ Not connected",
    "status_class": "warn",
    "spend_display": "—",
    "roas": None,
    "roas_class": "off",
    "conversions": None,
    "cpa_display": "—",
    "share_pct": 0,
}

PLATFORM_LABELS = {
    "meta": "Meta Ads",
    "bing": "Bing Ads",
    "tiktok": "TikTok Ads",
}


# ─────────────────────────── helpers: formatting ───────────────────────────

def fmt_int_ro(value) -> str:
    """1247 -> '1,247' (thousands separator, English style)."""
    return f"{round(value):,}"


def split_compact(value: float):
    """328000 -> ('328', 'K'); 3820000 -> ('3.82', 'M'); 512 -> ('512', '')."""
    value = float(value)
    if abs(value) >= 1_000_000:
        num = value / 1_000_000
        s = f"{num:.2f}".rstrip("0").rstrip(".")
        return s, "M"
    if abs(value) >= 10_000:
        return f"{value/1000:.0f}", "K"
    if abs(value) >= 1_000:
        s = f"{value/1000:.1f}".rstrip("0").rstrip(".")
        return s, "K"
    return f"{value:.0f}", ""


def compact_display(value: float) -> str:
    num, suffix = split_compact(value)
    return f"{num}{suffix}"


def roas_class(roas):
    if roas is None:
        return "off"
    if roas >= 5:
        return "good"
    if roas >= 4:
        return "warn"
    return "bad"


def pct_delta(current: float, previous: float):
    """Returneaza (delta_display, delta_dir) pentru variatie procentuala."""
    if previous == 0:
        return "—", "up"
    change = (current - previous) / previous * 100
    arrow = "↑" if change >= 0 else "↓"
    return f"{arrow} {abs(change):.0f}%", ("up" if change >= 0 else "down")


def cpa_delta(current: float, previous: float):
    """Pentru CPA, o scadere e 'buna' (clasa up/verde) desi sageata e ↓."""
    if previous == 0:
        return "—", "up"
    change = (current - previous) / previous * 100
    arrow = "↑" if change >= 0 else "↓"
    direction = "down" if change >= 0 else "up"  # CPA crescut = rau (rosu)
    return f"{arrow} {abs(change):.0f}%", direction


def roas_delta(current: float, previous: float):
    diff = current - previous
    arrow = "↑" if diff >= 0 else "↓"
    direction = "up" if diff >= 0 else "down"
    return f"{arrow} {abs(diff):.1f}x", direction


# ─────────────────────────── helpers: date ranges ───────────────────────────

def resolve_period(period_key: str):
    today = date.today()

    if period_key == "today":
        start = end = today
        prev_start = prev_end = today - timedelta(days=1)
        label = f"OVERVIEW — TODAY ({today.strftime('%d.%m.%Y')})"

    elif period_key == "7d":
        end = today
        start = today - timedelta(days=6)
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        label = "OVERVIEW — LAST 7 DAYS"

    elif period_key == "14d":
        end = today
        start = today - timedelta(days=13)
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        label = "OVERVIEW — LAST 14 DAYS"

    elif period_key == "90d":
        end = today
        start = today - timedelta(days=89)
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        label = "OVERVIEW — LAST 90 DAYS"

    elif period_key == "this_month":
        start = today.replace(day=1)
        end = today
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        label = f"OVERVIEW — {RO_MONTHS[today.month - 1]} {today.year} (CURRENT MONTH)"

    elif period_key == "last_month":
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        start = end.replace(day=1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        label = f"OVERVIEW — {RO_MONTHS[end.month - 1]} {end.year} (LAST MONTH)"

    elif period_key == "all_time":
        # Limitam "tot timpul" la ultimii 2 ani, pentru performanta API-ului.
        end = today
        start = today - timedelta(days=730)
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        label = "OVERVIEW — ALL TIME (LAST 2 YEARS)"

    else:  # "30d" default
        end = today
        start = today - timedelta(days=29)
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        label = f"OVERVIEW — {RO_MONTHS[today.month - 1]} {today.year}"

    return {
        "start": start, "end": end,
        "prev_start": prev_start, "prev_end": prev_end,
        "label": label,
    }


def daterange_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# ─────────────────────────── Google Ads queries ───────────────────────────

CAMPAIGN_QUERY = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND campaign.status != 'REMOVED'
"""

AD_GROUP_QUERY = """
SELECT
  campaign.name,
  ad_group.name,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM ad_group
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND campaign.status != 'REMOVED'
  AND ad_group.status != 'REMOVED'
"""

# Campaniile Performance Max nu raporteaza metrici la nivel de 'ad_group'
# (folosesc 'asset_group' in schimb), asa ca le interogam separat si le
# combinam cu randurile de mai sus pentru breakdown-ul pe destinatii.
ASSET_GROUP_QUERY = """
SELECT
  campaign.name,
  asset_group.name,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM asset_group
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND campaign.status != 'REMOVED'
  AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
"""

DAILY_QUERY = """
SELECT
  segments.date,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM customer
WHERE segments.date BETWEEN '{start}' AND '{end}'
"""

TODAY_QUERY = """
SELECT
  metrics.cost_micros
FROM customer
WHERE segments.date = '{day}'
"""


def run_query(ga_service, customer_id: str, query: str):
    return ga_service.search(customer_id=customer_id, query=query)


def fetch_campaign_totals(ga_service, customer_ids, start, end):
    """Returneaza (totals_dict, campaigns_list)."""
    totals = {"cost": 0.0, "conversions": 0.0, "conv_value": 0.0}
    campaigns = []
    query = CAMPAIGN_QUERY.format(start=daterange_str(start), end=daterange_str(end))
    for cid in customer_ids:
        for row in run_query(ga_service, cid, query):
            cost = row.metrics.cost_micros / 1_000_000
            conv = row.metrics.conversions
            conv_val = row.metrics.conversions_value
            totals["cost"] += cost
            totals["conversions"] += conv
            totals["conv_value"] += conv_val
            if cost > 0 or conv > 0:
                campaigns.append({
                    "name": row.campaign.name,
                    "cost": cost,
                    "conversions": conv,
                    "conv_value": conv_val,
                    "roas": (conv_val / cost) if cost > 0 else 0.0,
                })
    return totals, campaigns


def fetch_ad_group_totals(ga_service, customer_ids, start, end):
    """Pentru breakdown pe destinatii: cost/conversii/valoare per ad group.

    Numele destinatiei e dedus din 'campanie + ad group' (ex: ad group
    'Plecari din Bucuresti - Grecia' -> destinatia 'Grecia'), pe baza
    regulilor din config/accounts.json -> destination_mapping.rules.
    """
    rows_out = []
    query = AD_GROUP_QUERY.format(start=daterange_str(start), end=daterange_str(end))
    for cid in customer_ids:
        for row in run_query(ga_service, cid, query):
            cost = row.metrics.cost_micros / 1_000_000
            conv_val = row.metrics.conversions_value
            conv = row.metrics.conversions
            if cost <= 0 and conv_val <= 0:
                continue
            rows_out.append({
                "label": f"{row.campaign.name} | {row.ad_group.name}",
                "cost": cost,
                "conversions": conv,
                "conv_value": conv_val,
            })
    return rows_out


def fetch_asset_group_totals(ga_service, customer_ids, start, end):
    """La fel ca fetch_ad_group_totals, dar pentru campaniile Performance Max
    (raporteaza pe 'asset_group', nu pe 'ad_group')."""
    rows_out = []
    query = ASSET_GROUP_QUERY.format(start=daterange_str(start), end=daterange_str(end))
    for cid in customer_ids:
        try:
            results = run_query(ga_service, cid, query)
        except GoogleAdsException:
            continue
        for row in results:
            cost = row.metrics.cost_micros / 1_000_000
            conv_val = row.metrics.conversions_value
            conv = row.metrics.conversions
            if cost <= 0 and conv_val <= 0:
                continue
            rows_out.append({
                "label": f"{row.campaign.name} | {row.asset_group.name}",
                "cost": cost,
                "conversions": conv,
                "conv_value": conv_val,
            })
    return rows_out


def fetch_period_totals(ga_service, customer_ids, start, end):
    totals = {"cost": 0.0, "conversions": 0.0, "conv_value": 0.0}
    query = CAMPAIGN_QUERY.format(start=daterange_str(start), end=daterange_str(end))
    for cid in customer_ids:
        for row in run_query(ga_service, cid, query):
            totals["cost"] += row.metrics.cost_micros / 1_000_000
            totals["conversions"] += row.metrics.conversions
            totals["conv_value"] += row.metrics.conversions_value
    return totals


def _series_point(d: date, entry: dict, granularity: str):
    cost = entry["cost"]
    conv_value = entry["conv_value"]
    roas = (conv_value / cost) if cost > 0 else 0.0

    if granularity == "week":
        wk_end = d + timedelta(days=6)
        label = d.strftime("%d.%m")
        full_label = f"Week {d.strftime('%d.%m')}–{wk_end.strftime('%d.%m.%Y')}"
    elif granularity == "month":
        label = f"{RO_MONTHS_SHORT[d.month - 1]} {str(d.year)[2:]}"
        full_label = f"{RO_MONTHS[d.month - 1]} {d.year}"
    else:  # day
        label = d.strftime("%d")
        full_label = f"{d.day:02d} {RO_MONTHS_SHORT[d.month - 1]} {d.year}"

    return {
        "label": label,
        "full_label": full_label,
        "date": d.isoformat(),
        "spend": round(cost, 2),
        "conversions": round(entry["conversions"], 2),
        "revenue": round(conv_value, 2),
        "roas": round(roas, 2),
    }


def fetch_series(ga_service, customer_ids, start, end, granularity="day"):
    """Serie de date (zilnica, saptamanala sau lunara) pentru grafice + diagnostic."""
    query = DAILY_QUERY.format(start=daterange_str(start), end=daterange_str(end))
    by_key = {}
    for cid in customer_ids:
        for row in run_query(ga_service, cid, query):
            d = date.fromisoformat(row.segments.date)
            if granularity == "week":
                key_date = d - timedelta(days=d.weekday())
            elif granularity == "month":
                key_date = d.replace(day=1)
            else:
                key_date = d
            key = key_date.isoformat()
            entry = by_key.setdefault(key, {"cost": 0.0, "conversions": 0.0, "conv_value": 0.0})
            entry["cost"] += row.metrics.cost_micros / 1_000_000
            entry["conversions"] += row.metrics.conversions
            entry["conv_value"] += row.metrics.conversions_value

    points = []
    if granularity == "day":
        cur = start
        while cur <= end:
            key = cur.isoformat()
            entry = by_key.get(key, {"cost": 0.0, "conversions": 0.0, "conv_value": 0.0})
            points.append(_series_point(cur, entry, granularity))
            cur += timedelta(days=1)
    else:
        for key in sorted(by_key.keys()):
            points.append(_series_point(date.fromisoformat(key), by_key[key], granularity))

    return points


def fetch_today_spend(ga_service, customer_ids):
    today_str = daterange_str(date.today())
    query = TODAY_QUERY.format(day=today_str)
    total = 0.0
    for cid in customer_ids:
        for row in run_query(ga_service, cid, query):
            total += row.metrics.cost_micros / 1_000_000
    return total


# ─────────────────────────── build output ───────────────────────────

def to_campaign_dict(c):
    return {
        "platform": "google",
        "name": c["name"],
        "spend": round(c["cost"], 2),
        "spend_display": compact_display(c["cost"]),
        "conversions": round(c["conversions"]),
        "revenue": round(c["conv_value"], 2),
        "revenue_display": compact_display(c["conv_value"]),
        "roas": round(c["roas"], 1),
        "roas_class": roas_class(c["roas"]),
    }


def build_destinations(ad_groups, mapping_rules, limit=8):
    if not mapping_rules:
        return []
    buckets = {}
    for row in ad_groups:
        label_lc = row["label"].lower()
        for rule in mapping_rules:
            if rule["match"].lower() in label_lc:
                dest = rule["destination"]
                bucket = buckets.setdefault(dest, {"cost": 0.0, "conv_value": 0.0, "conversions": 0.0})
                bucket["cost"] += row["cost"]
                bucket["conv_value"] += row["conv_value"]
                bucket["conversions"] += row.get("conversions", 0.0)
                break
    result = []
    for dest, vals in buckets.items():
        roas = (vals["conv_value"] / vals["cost"]) if vals["cost"] > 0 else 0.0
        result.append({
            "platform": "google",
            "name": dest,
            "spend": round(vals["cost"], 2),
            "spend_display": compact_display(vals["cost"]),
            "conversions": round(vals["conversions"]),
            "revenue": round(vals["conv_value"], 2),
            "revenue_display": compact_display(vals["conv_value"]),
            "roas": round(roas, 1),
        })
    result.sort(key=lambda d: d["revenue"], reverse=True)
    return result if limit is None else result[:limit]


def build_alerts(campaigns, thresholds):
    alerts = []
    crit = thresholds.get("roas_critical_below", 3.0)
    warn = thresholds.get("roas_warning_below", 4.5)

    worst = sorted([c for c in campaigns if c["cost"] > 0], key=lambda c: c["roas"])[:3]
    for c in worst:
        if c["roas"] < crit:
            alerts.append({
                "severity": "crit",
                "icon": "🔴",
                "title": f"Google Ads: ROAS below critical ({c['roas']:.1f}x) — {c['name']}",
                "desc": f"This campaign spends {compact_display(c['cost'])} RON with a ROAS of {c['roas']:.1f}x, below the critical threshold of {crit:.1f}x. Needs urgent review.",
                "time": "today",
            })
        elif c["roas"] < warn:
            alerts.append({
                "severity": "warn",
                "icon": "🟠",
                "title": f"Google Ads: ROAS below target ({c['roas']:.1f}x) — {c['name']}",
                "desc": f"This campaign spends {compact_display(c['cost'])} RON with a ROAS of {c['roas']:.1f}x, below the target of {warn:.1f}x.",
                "time": "today",
            })

    if not alerts:
        alerts.append({
            "severity": "info",
            "icon": "🔵",
            "title": "All Google Ads campaigns are on target",
            "desc": "No ROAS below the thresholds configured in config/accounts.json.",
            "time": "azi",
        })

    alerts.append({
        "severity": "info",
        "icon": "🔵",
        "title": "Meta, Bing and TikTok not connected",
        "desc": "Connect these platforms' APIs for live data — see README_PPC_DASHBOARD.md.",
        "time": "azi",
    })
    return alerts


def build_kpis(current, previous):
    spend_disp, spend_unit = split_compact(current["cost"])
    rev_disp, rev_unit = split_compact(current["conv_value"])
    roas_global = (current["conv_value"] / current["cost"]) if current["cost"] > 0 else 0.0
    roas_prev = (previous["conv_value"] / previous["cost"]) if previous["cost"] > 0 else 0.0
    cpa = (current["cost"] / current["conversions"]) if current["conversions"] > 0 else 0.0
    cpa_prev = (previous["cost"] / previous["conversions"]) if previous["conversions"] > 0 else 0.0

    spend_delta, spend_dir = pct_delta(current["cost"], previous["cost"])
    rev_delta, rev_dir = pct_delta(current["conv_value"], previous["conv_value"])
    roas_delta_disp, roas_dir = roas_delta(roas_global, roas_prev)
    conv_delta, conv_dir = pct_delta(current["conversions"], previous["conversions"])
    cpa_delta_disp, cpa_dir = cpa_delta(cpa, cpa_prev)

    return {
        "spend_total": {"display": spend_disp, "unit": f"{spend_unit} RON".strip(), "delta_display": spend_delta, "delta_dir": spend_dir},
        "revenue": {"display": rev_disp, "unit": f"{rev_unit} RON".strip(), "delta_display": rev_delta, "delta_dir": rev_dir},
        "roas_global": {"display": f"{roas_global:.2f}", "unit": "x", "delta_display": roas_delta_disp, "delta_dir": roas_dir},
        "conversions": {"display": fmt_int_ro(current["conversions"]), "unit": "", "delta_display": conv_delta, "delta_dir": conv_dir},
        "cpa_avg": {"display": f"{cpa:.0f}", "unit": "RON", "delta_display": cpa_delta_disp, "delta_dir": cpa_dir},
    }


def build_google_platform(current):
    roas = (current["conv_value"] / current["cost"]) if current["cost"] > 0 else 0.0
    cpa = (current["cost"] / current["conversions"]) if current["conversions"] > 0 else 0.0
    return {
        "name": "Google Ads",
        "status": "connected",
        "status_label": "● Active",
        "status_class": "ok",
        "spend_display": compact_display(current["cost"]),
        "roas": round(roas, 1),
        "roas_class": roas_class(roas),
        "conversions": round(current["conversions"]),
        "cpa_display": f"{fmt_int_ro(cpa)} RON",
        "share_pct": 100 if current["cost"] > 0 else 0,
    }


def not_connected_platform(key):
    p = dict(NOT_CONNECTED_PLATFORM)
    p["name"] = PLATFORM_LABELS[key]
    return p


def build_period_output(ga_service, customer_ids, accounts, period_key, today_spend):
    period = resolve_period(period_key)

    current_totals, campaigns_raw = fetch_campaign_totals(
        ga_service, customer_ids, period["start"], period["end"])
    previous_totals = fetch_period_totals(
        ga_service, customer_ids, period["prev_start"], period["prev_end"])
    ad_groups_raw = fetch_ad_group_totals(
        ga_service, customer_ids, period["start"], period["end"])
    ad_groups_raw += fetch_asset_group_totals(
        ga_service, customer_ids, period["start"], period["end"])

    granularity = "month" if period_key == "all_time" else "day"
    series = fetch_series(ga_service, customer_ids, period["start"], period["end"], granularity)

    # Campanii: lista completa (sortata pe spend) + top 8 pentru overview (sortat pe ROAS)
    campaigns_active = sorted(
        [c for c in campaigns_raw if c["cost"] > 0],
        key=lambda c: c["cost"], reverse=True
    )
    campaigns_top = sorted(campaigns_active, key=lambda c: c["roas"], reverse=True)[:8]

    campaigns_all_out = [to_campaign_dict(c) for c in campaigns_active]
    campaigns_top_out = [to_campaign_dict(c) for c in campaigns_top]

    destinations_all = build_destinations(
        ad_groups_raw, accounts.get("destination_mapping", {}).get("rules", []), limit=None)
    destinations_top = destinations_all[:8]

    alerts = build_alerts(campaigns_raw, accounts.get("alert_thresholds", {}))

    return {
        "meta": {
            "generated_at": date.today().isoformat() + "T00:00:00",
            "period_label": period["label"],
            "period_key": period_key,
            "source": "live",
        },
        "kpis": build_kpis(current_totals, previous_totals),
        "platforms": {
            "google": build_google_platform(current_totals),
            "meta": not_connected_platform("meta"),
            "bing": not_connected_platform("bing"),
            "tiktok": not_connected_platform("tiktok"),
        },
        "campaigns": campaigns_top_out,
        "campaigns_all": campaigns_all_out,
        "destinations": destinations_top,
        "destinations_all": destinations_all,
        "alerts": alerts,
        "daily": {
            "days": [p["label"] for p in series],
            "full_labels": [p["full_label"] for p in series],
            "spend": [p["spend"] for p in series],
            "roas": [p["roas"] for p in series],
            "revenue": [p["revenue"] for p in series],
            "conversions": [p["conversions"] for p in series],
            "granularity": granularity,
        },
        "daily_table": [dict(p, platform="google") for p in series],
        "sidebar_spend_today": {
            "google": f"{fmt_int_ro(today_spend)} RON",
            "meta": "— RON",
            "bing": "— RON",
            "tiktok": "— RON",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="30d", choices=PERIOD_KEYS,
                         help="Perioada activa implicit la incarcarea dashboardului (default: 30d)")
    args = parser.parse_args()

    if not GOOGLE_ADS_YAML.exists():
        print(f"Nu gasesc {GOOGLE_ADS_YAML}.")
        print(f"Copiaza {GOOGLE_ADS_YAML.with_suffix('.yaml.template')} -> google-ads.yaml si completeaza credentialele.")
        sys.exit(1)
    if not ACCOUNTS_JSON.exists():
        print(f"Nu gasesc {ACCOUNTS_JSON}.")
        sys.exit(1)

    accounts = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    customer_ids = [c for c in accounts.get("google_ads", {}).get("customer_ids", []) if c and "INSERT" not in c]
    if not customer_ids:
        print("config/accounts.json: 'google_ads.customer_ids' este gol sau contine placeholder-ul implicit.")
        print("Adauga ID-urile conturilor Google Ads (10 cifre, fara liniute).")
        sys.exit(1)

    client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = client.get_service("GoogleAdsService")

    try:
        today_spend = fetch_today_spend(ga_service, customer_ids)
        output_by_period = {}
        for period_key in PERIOD_KEYS:
            output_by_period[period_key] = build_period_output(
                ga_service, customer_ids, accounts, period_key, today_spend)
    except GoogleAdsException as ex:
        print("Eroare Google Ads API:")
        for error in ex.failure.errors:
            print(f"  - {error.message}")
        sys.exit(1)

    default_period = args.period if args.period in output_by_period else "30d"

    js_content = (
        "/* Generat automat de scripts/fetch_google_ads_data.py — nu edita manual. */\n"
        "window.PPC_DATA_BY_PERIOD = "
        + json.dumps(output_by_period, ensure_ascii=False, indent=2)
        + ";\n"
        f"window.PPC_DATA = window.PPC_DATA_BY_PERIOD['{default_period}'];\n"
    )
    OUTPUT_JS.write_text(js_content, encoding="utf-8")

    default_out = output_by_period[default_period]
    kpis = default_out["kpis"]
    print(f"OK — date scrise in {OUTPUT_JS}")
    print(f"Perioade generate: {', '.join(PERIOD_KEYS)}")
    print(f"Perioada activa implicit: {default_out['meta']['period_label']}")
    print(f"Spend: {kpis['spend_total']['display']}{kpis['spend_total']['unit']} | "
          f"Revenue: {kpis['revenue']['display']}{kpis['revenue']['unit']} | "
          f"ROAS: {kpis['roas_global']['display']}x")


if __name__ == "__main__":
    main()
