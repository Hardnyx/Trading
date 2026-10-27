"""Annual diluted EPS evidence from a CURRENT SEC companyfacts response.

Filing dates are retained, but they do not certify original historical API
vintages. Comparisons within one accession avoid mixing per-share split bases.
Nothing in this module changes production growth assumptions.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import defaultdict


MODEL_VERSION = "annual-eps-shrinkage-shadow-1"
ANNUAL_FORMS = {"10-K", "10-KT", "20-F", "40-F"}
PERIODIC_FORMS = ANNUAL_FORMS | {"10-Q", "10-QT"}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def annual_eps_history(facts, cik, cutoff, observed_at, years=12):
    """Retain every dated annual EPS version, rejecting ambiguous contexts."""
    cut = dt.date.fromisoformat(cutoff)
    lower = cut - dt.timedelta(days=math.ceil(years * 365.25))
    grouped = defaultdict(list)
    for row in facts.get("EarningsPerShareDiluted", {}).get("units", {}).get("USD/shares", []):
        try:
            start, end, filed = (dt.date.fromisoformat(row[k]) for k in ("start", "end", "filed"))
        except (KeyError, TypeError, ValueError):
            continue
        form = row.get("form", "")
        accn = row.get("accn", "")
        if (not finite(row.get("val")) or not isinstance(form, str) or
                form.removesuffix("/A") not in PERIODIC_FORMS or
                not isinstance(accn, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accn) or
                not 330 <= (end - start).days <= 390 or
                not lower <= end <= filed <= cut):
            continue
        grouped[(accn, start.isoformat(), end.isoformat())].append(row)
    records, conflicts = [], 0
    for (accn, start, end), rows in sorted(grouped.items()):
        # Multiple share classes/contexts cannot be selected by array order.
        if len({(r["val"], r["filed"], r["form"]) for r in rows}) != 1:
            conflicts += 1
            continue
        row = rows[0]
        records.append({
            "start": start, "period_end": end, "filed": row["filed"],
            "value": row["val"], "accn": accn, "form": row["form"],
            "source_kind": row.get("source_kind", "current_companyfacts"),
            "source_url": row.get("source_url") or
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{accn}-index.html",
        })
    records.sort(key=lambda r: (r["filed"], r["period_end"], r["accn"]))
    return {
        "schema_version": 1, "basis": "annual_diluted_reported_eps",
        "through_filing_date": cutoff, "observed_at": observed_at,
        "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        "vintage_mode": "current_response_with_filing_dates",
        "original_vintages_verified": False, "lookback_years": years,
        "conflicting_periods_excluded": conflicts, "records": records,
    }


def annual_origins(history):
    """One first annual release per fiscal end, with a same-filing comparator."""
    groups = defaultdict(list)
    for row in history.get("records", []):
        if row["form"].removesuffix("/A") in ANNUAL_FORMS:
            groups[(row["filed"], row["accn"])].append(row)
    origins = {}
    for (filed, accn), rows in sorted(groups.items()):
        current = max(rows, key=lambda r: r["period_end"])
        end = dt.date.fromisoformat(current["period_end"])
        # A later filing that only repeats old annual data is not a new origin.
        if not 0 <= (dt.date.fromisoformat(filed) - end).days <= 220:
            continue
        if current["period_end"] in origins:
            continue
        prior = [r for r in rows if
                 350 <= (end - dt.date.fromisoformat(r["period_end"])).days <= 380 and
                 350 <= (dt.date.fromisoformat(current["start"]) - dt.date.fromisoformat(r["start"])).days <= 380]
        comparator = min(prior, key=lambda r: abs((end - dt.date.fromisoformat(r["period_end"])).days - 365), default=None)
        positive = comparator is not None and current["value"] > 0 and comparator["value"] > 0
        origins[current["period_end"]] = {
            "period_end": current["period_end"], "filed": filed, "accn": accn,
            "eps": current["value"], "previous_eps_same_filing": comparator["value"] if comparator else None,
            "previous_period_end": comparator["period_end"] if comparator else None,
            "log_growth": math.log(current["value"] / comparator["value"]) if positive else None,
            "source_url": current["source_url"],
            "comparator_source_url": comparator["source_url"] if comparator else None,
        }
    return sorted(origins.values(), key=lambda r: (r["filed"], r["period_end"]))


def quantile(values, probability):
    ordered = sorted(values)
    p = (len(ordered) - 1) * probability
    low = math.floor(p)
    return ordered[low] + (ordered[math.ceil(p)] - ordered[low]) * (p - low)


def growth_candidate(origins, as_of, prior=0.06, prior_strength=5, window=5):
    """Fixed, explicit shrinkage; neither hyperparameters nor prior are fitted."""
    known = [r for r in origins if r["filed"] <= as_of and r["log_growth"] is not None][-window:]
    weight = len(known) / (len(known) + prior_strength)
    mean = sum(r["log_growth"] for r in known) / len(known) if known else 0
    predicted = (1 - weight) * math.log1p(prior) + weight * mean
    return {
        "log_growth": predicted, "annual_growth": math.expm1(predicted),
        "company_weight": weight, "training_observations": len(known),
        "training_period_ends": [r["period_end"] for r in known],
        "training_latest_filing": max((r["filed"] for r in known), default=None),
        "prior_growth": prior, "prior_strength": prior_strength, "window": window,
    }


def growth_replay(history, sector_growth=None):
    """Forward-chained diagnostic on reconstructed annual filing observations.

    A target growth ratio is measured inside its own filing so its denominator
    and numerator have a common per-share basis. It can include restatements.
    Empirical bands use ONLY errors whose outcome had been filed at the origin.
    """
    origins = annual_origins(history)
    results = []
    for origin in origins:
        if origin["eps"] <= 0:
            continue
        targets = [r for r in origins if r["previous_period_end"] == origin["period_end"]
                   and r["filed"] > origin["filed"] and r["log_growth"] is not None]
        if not targets:
            continue
        target = min(targets, key=lambda r: r["filed"])
        candidate = growth_candidate(origins, origin["filed"])
        matured = [r["log_error"] for r in results if r["outcome_filed"] < origin["filed"]]
        band = [candidate["log_growth"] + quantile(matured, p) for p in (.05, .95)] if len(matured) >= 5 else None
        actual = math.expm1(target["log_growth"])
        predictions = {"shrinkage": candidate["annual_growth"], "common_prior": .06}
        # The current catalog's sector convention is not a historical vintage.
        if finite(sector_growth) and sector_growth > -1:
            predictions["current_sector_convention"] = sector_growth
        if origin["log_growth"] is not None:
            predictions["last_growth"] = math.expm1(origin["log_growth"])
        results.append({
            "origin_period_end": origin["period_end"], "origin_filed": origin["filed"],
            "origin_source_url": origin["source_url"],
            "target_period_end": target["period_end"], "outcome_filed": target["filed"],
            "outcome_source_url": target["source_url"],
            "target_eps": target["eps"], "origin_eps_in_target_filing": target["previous_eps_same_filing"],
            "origin_eps_at_origin": origin["eps"],
            "actual_growth": actual, "predictions": predictions, "candidate": candidate,
            "log_error": target["log_growth"] - candidate["log_growth"],
            "band_log90": band, "band_calibration_observations": len(matured),
            "covered90": band[0] <= target["log_growth"] <= band[1] if band else None,
        })
    latest = growth_candidate(origins, history["through_filing_date"]) if origins and origins[-1]["eps"] > 0 else None
    return {
        "model_version": MODEL_VERSION, "status": "research_only_reconstructed",
        "production_eligible": False, "original_vintages_verified": False,
        "annual_origins": len(origins),
        "nonpositive_or_missing_comparator": sum(r["log_growth"] is None for r in origins),
        "latest_candidate": latest, "outcomes": results,
        "limitations": ["Current companyfacts response, not original historical API vintages",
                        "Current selected universe: survivorship and selection bias remain",
                        "Reported annual EPS, not continuing earnings or normalized cycle",
                        "Same-filing outcome comparisons may restate the origin EPS",
                        "One fiscal-year EPS growth is not a calibrated multi-year investment return",
                        "Prior 6%, strength 5 and window 5 are fixed research conventions"],
    }


def replay_metrics(results):
    """Paired model errors; no independence-based significance claims."""
    output = {}
    names = sorted({name for row in results for name in row["predictions"]})
    for name in names:
        rows = [r for r in results if name in r["predictions"]]
        errors = [r["predictions"][name] - r["actual_growth"] for r in rows]
        output[name] = {
            "observations": len(rows), "bias": sum(errors) / len(errors),
            "mae": sum(abs(e) for e in errors) / len(errors),
            "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
        }
    paired = [r for r in results if "last_growth" in r["predictions"]]
    output["paired_with_last_growth"] = {
        "observations": len(paired),
        "mae_shrinkage": sum(abs(r["predictions"]["shrinkage"] - r["actual_growth"]) for r in paired) / len(paired) if paired else None,
        "mae_last_growth": sum(abs(r["predictions"]["last_growth"] - r["actual_growth"]) for r in paired) / len(paired) if paired else None,
    }
    bands = [r for r in results if r["covered90"] is not None]
    output["empirical_band90"] = {"observations": len(bands),
                                  "coverage": sum(r["covered90"] for r in bands) / len(bands) if bands else None}
    return output
