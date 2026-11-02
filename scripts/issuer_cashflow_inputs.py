"""Normalize preserved issuer outcome facts without injecting them into forecasts."""
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/historical/issuer-cashflows-v1"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADERS = ["Dividend Period", "Amount", "Announcement Date", "Ex-Dividend Date", "Record Date", "Payable Date"]
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def validate(rows):
    seen = set()
    for row in rows:
        for key in ("ex_date", "record_date", "pay_date"):
            if dt.date.fromisoformat(row[key]).isoformat() != row[key]:
                raise ValueError("Noncanonical issuer date")
        amount = row["amount_per_share"]
        if (row["ex_date"] in seen or row["pay_date"] < row["ex_date"] or
                row["record_date"] < row["ex_date"] or type(amount) not in (float, int) or
                not math.isfinite(amount) or amount <= 0):
            raise ValueError("Invalid or duplicate issuer distribution")
        seen.add(row["ex_date"])
    if not rows:
        raise ValueError("Empty issuer distribution source")
    return sorted(rows, key=lambda r: r["ex_date"])


def parse_pfizer(text):
    lines = text.strip().splitlines()
    if lines[0] != "Ex Date | Record Date | Payable Date | Amount | Type":
        raise ValueError("Pfizer table header changed")
    rows = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split("|")]
        if len(cells) != 5 or cells[4] != "Regular Cash":
            raise ValueError("Unsupported Pfizer distribution row")
        dates = [dt.datetime.strptime(value, "%m/%d/%Y").date().isoformat() for value in cells[:3]]
        rows.append(dict(zip(("ex_date", "record_date", "pay_date"), dates), amount_per_share=float(cells[3])))
    return validate(rows)


def parse_microsoft(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 10_000_000:
            raise ValueError("Issuer workbook exceeds extraction limit")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        props = workbook.find("s:workbookPr", NS)
        if props is not None and props.get("date1904") not in (None, "0", "false"):
            raise ValueError("Unsupported issuer workbook date system")
        strings = ["".join(row.itertext()) for row in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        rows = []
        for number in (1, 2, 3):
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{number}.xml"))
            table = ET.fromstring(archive.read(f"xl/tables/table{number}.xml"))
            match = re.fullmatch(r"A1:F(\d+)", table.get("ref", ""))
            if not match:
                raise ValueError("Issuer workbook table range changed")
            content = []
            for row in sheet.findall(".//s:row", NS):
                if int(row.get("r")) > int(match[1]):
                    continue
                values = {}
                for cell in row:
                    col = re.sub(r"\d", "", cell.get("r", ""))
                    if col not in set("ABCDEF"):
                        continue
                    if cell.find("s:f", NS) is not None:
                        raise ValueError("Formula cannot replace an issuer distribution fact")
                    value = cell.findtext("s:v", default="", namespaces=NS)
                    values[col] = strings[int(value)] if cell.get("t") == "s" else value
                content.append([values.get(c) for c in "ABCDEF"])
            if not content or content[0] != HEADERS:
                raise ValueError("Microsoft distribution headers changed")
            for record in content[1:]:
                dates = []
                for serial in record[2:]:
                    if not serial or not float(serial).is_integer():
                        raise ValueError("Invalid issuer Excel date")
                    dates.append((dt.date(1899, 12, 30) + dt.timedelta(days=int(float(serial)))).isoformat())
                rows.append({"announcement_date": dates[0], "ex_date": dates[1],
                             "record_date": dates[2], "pay_date": dates[3], "amount_per_share": float(record[1])})
    # The study window excludes older regular/special payments sharing an ex-date;
    # do not claim support for combining those historical payment schedules.
    return validate([row for row in rows if "2024-12-31" < row["ex_date"] <= "2026-10-30"])


def normalize(manifest, base=BASE):
    if manifest.get("outcome_only") is not True or manifest.get("forecast_input_eligible") is not False:
        raise ValueError("Issuer data is restricted to realized outcomes")
    assets = []
    allowed = {"PFE": "https://investors.pfizer.com/", "MSFT": "https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/"}
    for source in manifest["sources"]:
        symbol = source["symbol"]
        if symbol not in allowed or not source["source_url"].startswith(allowed[symbol]):
            raise ValueError("Issuer identity or source mismatch")
        raw = (base / source["path"]).read_bytes()
        if sha(raw) != source["sha256"]:
            raise ValueError("Issuer source hash mismatch")
        rows = parse_pfizer(raw.decode()) if symbol == "PFE" else parse_microsoft(raw)
        rows = [row for row in rows if "2024-12-31" < row["ex_date"] <= "2026-10-30"]
        validate(rows)
        observed_at = source["archived_at"]
        assets.append({"symbol": symbol, "issuer_distributions": {
            "symbol": symbol, "currency": "USD", "source_layer": "issuer",
            "source_url": source["source_url"], "source_sha256": source["sha256"],
            "source_representation": source["representation"], "observed_at": observed_at,
            "records": [{**row, "currency": "USD", "observed_at": observed_at} for row in rows]}})
    return {"protocol": manifest["protocol"], "outcome_only": True, "forecast_input_eligible": False,
            "production_eligible": False, "predictive_validation": "not-established", "assets": assets}


def main():
    raw = (BASE / "manifest.json").read_bytes()
    output = normalize(json.loads(raw))
    output.update(manifest_sha256=sha(raw), normalizer_sha256=sha(Path(__file__).read_bytes()))
    path = BASE / "normalized.json"
    data = json.dumps(output, indent=2) + "\n"
    if path.exists() and path.read_text() != data:
        raise ValueError("Published issuer normalization differs; use a new version")
    if not path.exists():
        path.write_text(data)
    print(json.dumps({"issuers": len(output["assets"]), "events": sum(len(a["issuer_distributions"]["records"]) for a in output["assets"])}))
    return output


if __name__ == "__main__":
    main()
