"""Optional data sources. Credentials are only read by the server-side collector."""
import datetime as dt
import csv
import io
import json
import math
import urllib.error
import urllib.parse


FRED_SERIES = [
    ("CPIAUCSL", "CPI", "IPC EE.UU.", "índice", "IPC desestacionalizado"),
    ("UNRATE", "UNRATE", "Desempleo", "%", "Tasa de desempleo desestacionalizada"),
    ("DFF", "DFF", "Fed funds efectiva", "%", "Tasa efectiva de fondos federales"),
    ("T10YIE", "T10YIE", "Breakeven 10Y", "%", "Compensación por inflación a diez años"),
    ("PAYEMS", "PAYEMS", "Nóminas no agrícolas", "miles de personas", "Empleo total no agrícola desestacionalizado"),
    ("INDPRO", "INDPRO", "Producción industrial", "índice", "Índice de producción industrial desestacionalizado"),
]


class ProviderError(ValueError):
    """Public diagnostics never include request URLs, payloads or credentials."""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def iso_day(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def observation_time(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ProviderError("La observación necesita zona horaria")
    return result.astimezone(dt.timezone.utc)


def request_json(download, base, params, cache_key):
    try:
        body = json.loads(download(base + "?" + urllib.parse.urlencode(params), cache_key))
    except urllib.error.HTTPError as error:
        raise ProviderError("Acceso al proveedor rechazado" if error.code in (401, 403) else "Error HTTP del proveedor", error.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise ProviderError("Proveedor no disponible") from None
    except (ValueError, UnicodeError):
        raise ProviderError("Respuesta del proveedor no válida") from None
    if isinstance(body, dict) and any(key in body for key in ("error_code", "Error Message", "error")):
        raise ProviderError("El proveedor rechazó la consulta; revisar clave, acceso y plan")
    return body


def fred_series(download, definition, cutoff, api_key, observed_at):
    if not api_key:
        raise ProviderError("Falta FRED_API_KEY")
    source_id, target_id, label, unit, description = definition
    end = dt.date.fromisoformat(cutoff)
    body = request_json(download, "https://api.stlouisfed.org/fred/series/observations", {
        "api_key": api_key, "file_type": "json", "series_id": source_id,
        "observation_start": f"{end.year - 5}-01-01", "observation_end": cutoff,
        "realtime_start": cutoff, "realtime_end": cutoff, "sort_order": "asc",
    }, f"fred-{source_id}-{cutoff}.json")
    return normalize_fred_series(body, definition, cutoff, observed_at, "api_realtime_period")


def fred_csv_series(download, definition, cutoff, observed_at):
    if observation_time(observed_at).date().isoformat() != cutoff:
        raise ProviderError("El CSV actual de FRED no se incorpora a un corte histórico")
    source_id = definition[0]
    query = urllib.parse.urlencode({"id": source_id, "cosd": f"{int(cutoff[:4]) - 5}-01-01", "coed": cutoff})
    try:
        raw = download("https://fred.stlouisfed.org/graph/fredgraph.csv?" + query, f"fred-csv-{source_id}-{cutoff}.csv")
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if source_id not in (reader.fieldnames or []):
            raise ProviderError("La exportación FRED no contiene la serie solicitada")
        observations = [{"date": row.get("observation_date") or row.get("DATE") or row.get("date"), "value": row.get(source_id)} for row in reader]
    except urllib.error.HTTPError as error:
        raise ProviderError("La exportación FRED no está disponible", error.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise ProviderError("La exportación FRED no está disponible") from None
    except (UnicodeError, csv.Error):
        raise ProviderError("La exportación FRED no contiene un CSV válido") from None
    return normalize_fred_series({"observations": observations}, definition, cutoff, observed_at, "observed_current")


def normalize_fred_series(body, definition, cutoff, observed_at, vintage_mode):
    source_id, target_id, label, unit, description = definition
    if not isinstance(body, dict) or not isinstance(body.get("observations"), list):
        raise ProviderError("FRED no devolvió una serie válida")
    observations = {}
    for row in body["observations"]:
        if not isinstance(row, dict):
            continue
        day = iso_day(row.get("date"))
        value = numeric(row.get("value"))
        available_from = iso_day(row.get("realtime_start"))
        available_until = iso_day(row.get("realtime_end"))
        if (day and f"{int(cutoff[:4]) - 5}-01-01" <= day <= cutoff and value is not None
                and (not available_from or available_from <= cutoff)
                and (not available_until or available_until >= cutoff)):
            observations[day] = {"date": day, "value": value}
    rows = [observations[day] for day in sorted(observations)]
    if not rows:
        raise ProviderError("FRED no devolvió observaciones disponibles al corte")
    latest = rows[-1]
    prior_year = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"
    prior = observations.get(prior_year)
    return {
        "id": target_id, "label": label, "unit": unit, "description": description,
        "value": latest["value"], "date": latest["date"],
        "previous": rows[-2]["value"] if len(rows) > 1 else None,
        "yoy": latest["value"] / prior["value"] - 1 if target_id == "CPI" and prior and prior["value"] else None,
        "history": rows, "provider": "FRED", "source_id": source_id,
        "vintage_date": cutoff, "vintage_mode": vintage_mode, "observed_at": observed_at,
        "source_url": f"https://fred.stlouisfed.org/series/{source_id}",
    }


def retained_estimates(previous, cutoff):
    if not isinstance(previous, dict) or not previous.get("observed_at"):
        return None
    try:
        known_day = observation_time(previous["observed_at"]).date().isoformat()
    except (ValueError, TypeError):
        return None
    return previous if known_day <= cutoff else None


def analyst_estimates(download, symbol, cutoff, api_key, observed_at, previous=None):
    if not api_key:
        raise ProviderError("Falta FMP_API_KEY")
    # This endpoint returns the current consensus, not historical consensus vintages.
    if observation_time(observed_at).date().isoformat() != cutoff:
        raise ProviderError("El consenso actual no se incorpora a un corte histórico")
    body = request_json(download, "https://financialmodelingprep.com/stable/analyst-estimates", {
        "symbol": symbol, "period": "annual", "page": 0, "limit": 10, "apikey": api_key,
    }, f"fmp-estimates-{symbol}-{cutoff}.json")
    if not isinstance(body, list):
        raise ProviderError("FMP no devolvió una lista de consensos")
    previous = retained_estimates(previous, cutoff)
    if previous and observation_time(previous["observed_at"]) >= observation_time(observed_at):
        previous = None
    prior = {r["period_end"]: r for r in (previous or {}).get("periods", [])}
    periods = {}
    for row in body:
        if not isinstance(row, dict):
            continue
        day = iso_day(row.get("date"))
        if row.get("symbol") != symbol or not day or day <= cutoff:
            continue
        record = {"period_end": day, "frequency": "annual"}
        for prefix, field in [("eps", "eps"), ("revenue", "revenue")]:
            for suffix, target in [("Avg", "mean"), ("Low", "low"), ("High", "high")]:
                record[f"{prefix}_{target}"] = numeric(row.get(field + suffix))
            count = numeric(row.get("numAnalystsEps" if prefix == "eps" else "numAnalystsRevenue"))
            record[f"{prefix}_analysts"] = int(count) if count is not None and count >= 0 and count.is_integer() else None
        if record["eps_mean"] is None and record["revenue_mean"] is None:
            continue
        record["currency"] = row.get("currency") if row.get("currency") in {"USD", "EUR", "GBP", "JPY", "CAD", "CHF"} else None
        record["eps_basis"] = "non_gaap"  # FMP analyst-estimates FAQ; never infer GAAP comparability.
        old = prior.get(day)
        if old and old.get("frequency") == "annual" and old.get("currency") == record["currency"] and old.get("eps_basis") == record["eps_basis"]:
            record["comparison_observed_at"] = previous["observed_at"]
            for prefix in ("eps", "revenue"):
                before, after = numeric(old.get(f"{prefix}_mean")), record[f"{prefix}_mean"]
                if before is not None and after is not None:
                    record[f"{prefix}_revision"] = after - before
                    record[f"{prefix}_revision_pct"] = (after - before) / abs(before) if before else None
        periods[day] = record
    return {
        "provider": "FMP", "observed_at": observed_at, "periods": [periods[day] for day in sorted(periods)][:4],
        "source_url": "https://site.financialmodelingprep.com/developer/docs/stable/financial-estimates",
    }
