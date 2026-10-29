"""Read-only model diagnostics and immutable monthly review, never model fitting."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import scipy
from scipy.stats import beta, binomtest

try:
    from .risk_ledger import kupiec, christoffersen
except ImportError:
    from risk_ledger import kupiec, christoffersen

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "monthly-validation-review-v1"
HORIZONS = (1, 5, 21)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def publication(root, path, raw):
    """Bind a forecast to its first committed blob, not a claimed old date."""
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)
    try:
        relative = path.relative_to(root).as_posix()
        commit = git("log", "--reverse", "--diff-filter=A", "--format=%H", "--", relative).decode().splitlines()[0]
        if digest(git("show", commit+":"+relative)) != digest(raw):
            return None
        return {"commit": commit, "committed_at": git("show", "-s", "--format=%cI", commit).decode().strip()}
    except (subprocess.CalledProcessError, IndexError):
        return None


def ny_day(stamp):
    from zoneinfo import ZoneInfo
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()


def holm(tests, alpha):
    """Fixed family includes unavailable tests as p=1; dependence is allowed."""
    ordered = sorted(tests, key=lambda t: (t["p_value"] if t["p_value"] is not None else 1, t["id"]))
    previous, output = 0, []
    for i, test in enumerate(ordered):
        p = test["p_value"] if test["p_value"] is not None else 1
        previous = max(previous, min(1, (len(ordered)-i)*p))
        output.append({**test, "holm_p": previous, "reject": test["p_value"] is not None and previous <= alpha})
    return output


def origin_interval(values):
    """Five nonoverlapping-origin blocks, twenty origins before an interval."""
    if len(values) < 20:
        return None
    a, rng = np.asarray(values, float), np.random.default_rng(20261029)
    means = []
    for _ in range(1000):
        starts = rng.integers(0, len(a)-4, math.ceil(len(a)/5))
        means.append(float(np.concatenate([a[k:k+5] for k in starts])[:len(a)].mean()))
    return [float(x) for x in np.quantile(means, [.025, .975])]


def series_diagnostic(entries):
    """One instrument or basket; never pool correlated asset hits as n."""
    selected, previous_end = [], ""
    for row in sorted(entries, key=lambda r: r["origin_date"]):
        if row["origin_date"] >= previous_end:
            selected.append(row)
            previous_end = row["maturity_date"]
    available = [r for r in selected if r["status"] == "scored"]
    hits = [bool(r["kernel"]["var95_exception"]) for r in available]
    n, k = len(hits), sum(hits)
    sequences, sequence, previous_maturity = [], [], None
    for row in selected:
        if row["status"] == "scored":
            if sequence and row["origin_date"] != previous_maturity:
                sequences.append(sequence)
                sequence = []
            sequence.append(bool(row["kernel"]["var95_exception"]))
            previous_maturity = row["maturity_date"]
        else:
            if sequence:
                sequences.append(sequence)
            sequence = []
            previous_maturity = None
    if sequence:
        sequences.append(sequence)
    missing = len(selected)-n
    coverage = [float(beta.ppf(.025, k, n-k+1)) if k else 0,
                float(beta.ppf(.975, k+1, n-k)) if k < n else 1] if n else None
    # Coverage uses an exact binomial p-value. Kupiec is shown separately as
    # an asymptotic diagnostic. Independence LR remains approximate and needs
    # at least 100 transitions and five exceptions before entering the family.
    independence = christoffersen(sequences)
    formal = n >= 20 and missing == 0
    independence_ready = formal and independence["transitions"] >= 100 and k >= 5
    gains = [r["ewma_zero_mean"]["crps"]-r["kernel"]["crps"] for r in available]
    qlike = [r["ewma_zero_mean"]["qlike"]-r["kernel"]["qlike"] for r in available
             if all(isinstance(r[m].get("qlike"), (int, float)) and math.isfinite(r[m]["qlike"]) for m in ("kernel", "ewma_zero_mean"))]
    return {"nonoverlapping_origins": n, "missing_outcomes": missing, "exceptions": k,
            "exception_rate": k/n if n else None, "exact_binomial_95": coverage,
            "kupiec": kupiec(k, n), "christoffersen": independence,
            "coverage_p": float(binomtest(k, n, .05).pvalue) if formal else None,
            "independence_p": independence["p_value"] if independence_ready else None,
            "crps_gain": sum(gains)/n if n else None, "crps_gain_block95": origin_interval(gains),
            "qlike_gain": sum(qlike)/len(qlike) if qlike else None, "qlike_pairs": len(qlike),
            "mean_es_residual": sum(r["kernel"]["es_residual"] for r in available)/n if n else None,
            "tail_observations": k, "formal_coverage_ready": formal,
            "formal_independence_ready": independence_ready,
            "cumulative": [{"origin_date": r["origin_date"], "maturity_date": r["maturity_date"],
                            "exceptions": sum(hits[:i+1]), "observations": i+1,
                            "crps_gain": sum(gains[:i+1])/(i+1),
                            "qlike_gain": sum(q)/len(q) if (q := [x["ewma_zero_mean"]["qlike"]-x["kernel"]["qlike"] for x in available[:i+1]
                              if all(isinstance(x[m].get("qlike"), (int, float)) and math.isfinite(x[m]["qlike"]) for m in ("kernel", "ewma_zero_mean"))]) else None}
                           for i, r in enumerate(available)]}


def review_decision(series, index, blocked=False):
    alpha = .05/(index*(index+1))
    tests = []
    for key, row in sorted(series.items()):
        for kind, field in (("coverage-exact", "coverage_p"), ("independence-asymptotic", "independence_p")):
            tests.append({"id": key+":"+kind, "series": key, "kind": kind, "p_value": row[field]})
    adjusted = holm(tests, alpha)
    rejected = [t for t in adjusted if t["reject"]]
    ready = sum(r["formal_coverage_ready"] for r in series.values())
    verdict = "incomplete" if blocked else "review-required" if rejected else "not-rejected-unvalidated" if ready else "accumulating"
    action = {"incomplete": "repair-evidence", "review-required": "suspend-promotion-and-review",
              "not-rejected-unvalidated": "review-precision-and-baselines", "accumulating": "continue-shadow-evaluation"}[verdict]
    return {"protocol": PROTOCOL, "review_index": index, "alpha": alpha, "family_size": len(tests),
            "tests": adjusted, "rejections": rejected, "verdict": verdict, "action": action,
            "automatic_parameter_change": False, "automatic_trade_authorization": False,
            "inference": "Exact coverage and asymptotic independence diagnostics, Holm within review and alpha spending across reviews of this kernel. Guarantees depend on valid p-values and observed outcomes; no predictive certification."}


def build_diagnostics(snapshot, forecasts, scores, current_kernel):
    issues, series, origins = [], defaultdict(list), []
    dates = sorted(r["date"] for a in snapshot["assets"] if a["symbol"] == "SPY" for r in a["history"] if r["date"] <= snapshot["price_as_of"])
    for forecast in forecasts:
        if forecast["price_kernel_version"] != current_kernel:
            continue
        cut, pub = forecast["input_price_as_of"], forecast.get("publication")
        if not pub:
            issues.append({"area": "kernel", "code": "unverified-publication", "origin": cut})
            continue
        future = [d for d in dates if d > cut]
        origins.append(cut)
        for horizon in HORIZONS:
            eligible = [r for r in forecast["records"] if r["horizon_sessions"] == horizon]
            # Keep every issued series in the family even before it matures.
            for row in eligible:
                series[str(horizon)+"|"+row["symbol"]]
            score = scores.get((cut, horizon))
            if score and dates and cut < dates[0] and score.get("status") == "scored":
                # The first mature score keeps its original observed dates
                # after the provider's rolling history drops that old window.
                start, end = score["origin_date"], score["maturity_date"]
            else:
                if len(future) < forecast["lead_sessions"]+horizon:
                    continue
                start, end = future[forecast["lead_sessions"]-1], future[forecast["lead_sessions"]+horizon-1]
            if start <= max(forecast["issue_ny_date"], ny_day(pub["committed_at"])):
                issues.append({"area": "kernel", "code": "nonprospective-origin", "origin": cut, "horizon": horizon})
                continue
            if not score or score.get("status") != "scored" or score.get("price_kernel_version") != current_kernel or score.get("issued_at") != forecast["issued_at"] or score.get("origin_date") != start or score.get("maturity_date") != end or end <= start:
                issues.append({"area": "kernel", "code": "missing-or-incompatible-mature-score", "origin": cut, "horizon": horizon})
                continue
            by_symbol = {r["symbol"]: r for r in score["rows"]}
            for row in eligible:
                value = by_symbol.get(row["symbol"], {"status": "missing-original-outcome"})
                if value["status"] == "scored":
                    if not all(isinstance(value.get(m, {}).get("crps"), (int, float)) and math.isfinite(value[m]["crps"]) for m in ("kernel", "ewma_zero_mean")) or not isinstance(value["kernel"].get("var95_exception"), bool) or not isinstance(value["kernel"].get("es_residual"), (int, float)):
                        issues.append({"area": "kernel", "code": "invalid-score", "origin": cut, "symbol": row["symbol"]})
                        value = {"status": "invalid-score"}
                if value["status"] != "scored":
                    issues.append({"area": "kernel", "code": "missing-outcome", "origin": cut, "symbol": row["symbol"], "horizon": horizon})
                series[str(horizon)+"|"+row["symbol"]].append({**value, "origin_date": start, "maturity_date": end})
    return {"sealed": len(origins), "series": {k: series_diagnostic(v) for k, v in sorted(series.items())}, "issues": issues}


def update_watch(root=ROOT, now=None, persist=True, upstream="not-requested"):
    now = now or datetime.now(timezone.utc).isoformat()
    root = Path(root).resolve()
    read = lambda p: json.loads(p.read_bytes())
    market_path = root/"dist/data/market.json"
    snapshot = read(market_path)
    if datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00")) > datetime.fromisoformat(now.replace("Z", "+00:00")):
        raise ValueError("Review predates observed market")
    kernel_summary = read(root/"dist/data/simulator-validation.json")
    kernel = kernel_summary["price_kernel_version"]
    forecasts, scores, hashes, score_issues = [], {}, {"dist/data/market.json": digest(market_path.read_bytes())}, []
    for p in sorted((root/"data/simulator-validation/forecasts").glob("*.json.gz")):
        raw = p.read_bytes();r = json.loads(gzip.decompress(raw))
        r["publication"] = publication(root, p, raw);forecasts.append(r);hashes[p.relative_to(root).as_posix()] = digest(raw)
    for p in sorted((root/"data/simulator-validation/scores").glob("*.json.gz")):
        raw = p.read_bytes();r = json.loads(gzip.decompress(raw))
        key = (r["input_price_as_of"], r["horizon_sessions"])
        if key in scores:
            raise ValueError("Duplicate score identity")
        if publication(root, p, raw):
            scores[key] = r
        else:
            score_issues.append({"area": "kernel", "code": "unverified-score-publication", "origin": key[0]})
        hashes[p.relative_to(root).as_posix()] = digest(raw)
    diagnostics = build_diagnostics(snapshot, forecasts, scores, kernel)
    issues = diagnostics["issues"]
    issues.extend(score_issues)
    physical = sum(f["price_kernel_version"] == kernel for f in forecasts)
    if "sealed" in kernel_summary and kernel_summary["sealed"] != physical:
        issues.append({"area": "kernel", "code": "seal-count-mismatch"})
    report_path = root/"dist/data/validation-review.json"
    if upstream == "not-requested" and report_path.exists():
        previous_report = read(report_path)
        if previous_report.get("source_market_generated_at") == snapshot["generated_at"]:
            upstream = previous_report.get("upstream_refresh", upstream)
    if upstream not in ("not-requested", "success"):
        issues.append({"area": "refresh", "code": "market-refresh-"+upstream})
    signal_path = root/"dist/data/signal-validation.json"
    signal = read(signal_path) if signal_path.exists() else None
    if not signal:
        issues.append({"area": "signal", "code": "missing-signal-summary"})
    elif signal.get("observed_price_as_of") != snapshot["price_as_of"]:
        issues.append({"area": "signal", "code": "stale-signal-summary"})
    elif any(c.get("publication_verified", 0) < c["sealed"] for c in signal.get("cohorts", {}).values()):
        issues.append({"area": "signal", "code": "unverified-signal-publication"})
    month = ny_day(now)[:7]
    directory = root/"data/validation-reviews"
    path = directory/(month+".kernel-"+kernel+".json.gz")
    if path.exists():
        review = json.loads(gzip.decompress(path.read_bytes()))
        if review["protocol"] != PROTOCOL:
            raise ValueError("Review protocol changed; preserve the old review and define a new protocol")
    else:
        previous = [p for p in directory.glob("*.json.gz") if p.name.endswith(".kernel-"+kernel+".json.gz")]
        review = {**review_decision(diagnostics["series"], len(previous)+1, any(i["area"] == "kernel" for i in issues)),
                  "month": month, "reviewed_at": now, "price_cut": snapshot["price_as_of"],
                  "price_kernel_version": kernel, "input_hashes": hashes, "series": diagnostics["series"],
                  "source_script_sha256": digest(Path(__file__).read_bytes()),
                  "source_hashes": {p: digest((ROOT/p).read_bytes()) for p in ("scripts/validation_watch.py", "scripts/risk_ledger.py", "requirements-research.txt")},
                  "software": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__}}
        if persist and upstream in ("not-requested", "success"):
            directory.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                f.write(gzip.compress(json.dumps(review, allow_nan=False, separators=(",", ":")).encode(), mtime=0))
    report = {"schema_version": 1, "protocol": PROTOCOL, "updated_at": now,
              "price_cut": snapshot["price_as_of"], "source_market_generated_at": snapshot["generated_at"],
              "price_kernel_version": kernel, "health": "incomplete" if issues else "complete", "issues": issues,
              "upstream_refresh": upstream,
              "predictive_validation": "not-established", "automatic_promotion": False,
              "kernel": diagnostics, "signals": {"available": signal is not None, "sealed": signal.get("sealed") if signal else None,
                 "cohorts": signal.get("cohorts") if signal else None, "current_cohort": signal.get("current_cohort") if signal else None},
              "monthly_review": review, "review_path": path.relative_to(root).as_posix(),
              "scope": "Per-series prospective diagnostics, no pooled asset-day p-values. Monthly review is immutable; current counters are descriptive. No parameter, portfolio or price-kernel change."}
    if persist:
        report_path.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":"))+"\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--upstream-status", choices=("not-requested", "success", "failure", "cancelled", "timed_out", "skipped"), default="not-requested")
    args = parser.parse_args()
    result = update_watch(persist=not args.preview, upstream=args.upstream_status)
    if args.preview:
        (ROOT/"out").mkdir(exist_ok=True)
        (ROOT/"out/validation-review-preview.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
    print(json.dumps({"health": result["health"], "kernel_seals": result["kernel"]["sealed"],
                      "review": result["monthly_review"]["verdict"], "issues": result["issues"], "predictive_validation": result["predictive_validation"]}))
