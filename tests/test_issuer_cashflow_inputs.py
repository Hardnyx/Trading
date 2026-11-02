import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from scripts.issuer_cashflow_inputs import BASE, NS, normalize, parse_pfizer, parse_microsoft


class IssuerCashflows(unittest.TestCase):
    def test_explicit_us_dates_and_payment_amounts_are_not_imputed(self):
        rows = parse_pfizer((BASE / "excerpts/PFE.txt").read_text())
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0], {"ex_date": "2025-01-24", "record_date": "2025-01-24",
                                  "pay_date": "2025-03-07", "amount_per_share": .43})
        text = (BASE / "excerpts/PFE.txt").read_text()
        for mutation in (text.replace("0.43", "nan", 1), text.replace("0.43", "-1", 1),
                         text + text.splitlines()[1] + "\n", text.replace("07/24/2026", "24/07/2026", 1)):
            with self.subTest(mutation=mutation[:30]), self.assertRaises(ValueError):
                parse_pfizer(mutation)

    def test_original_workbook_preserves_announcements_and_ex_dates_in_the_requested_window(self):
        rows = parse_microsoft((BASE / "originals/MSFT.xlsx").read_bytes())
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["ex_date"], "2025-02-20")
        self.assertEqual(rows[0]["pay_date"], "2025-03-13")
        self.assertEqual(rows[-1]["amount_per_share"], .91)
        self.assertTrue(all("2024-12-31" < r["ex_date"] <= "2026-10-30" for r in rows))

    def modified_workbook(self, name, mutate):
        original = zipfile.ZipFile(io.BytesIO((BASE / "originals/MSFT.xlsx").read_bytes()))
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w") as archive:
            for entry in original.infolist():
                content = original.read(entry.filename)
                if entry.filename == name:
                    root = ET.fromstring(content)
                    mutate(root)
                    content = ET.tostring(root)
                archive.writestr(entry.filename, content)
        return target.getvalue()

    def test_a_different_excel_epoch_or_formulas_fail_closed(self):
        def set_epoch(root):
            props = root.find("s:workbookPr", NS)
            props.set("date1904", "1")
        with self.assertRaisesRegex(ValueError, "date system"):
            parse_microsoft(self.modified_workbook("xl/workbook.xml", set_epoch))

        def formula(root):
            cell = root.find(".//s:c[@r='D3']", NS)
            ET.SubElement(cell, "{" + NS["s"] + "}f").text = "1+1"
        with self.assertRaisesRegex(ValueError, "Formula"):
            parse_microsoft(self.modified_workbook("xl/worksheets/sheet1.xml", formula))

    def test_source_identity_corruption_and_forecast_injection_are_rejected(self):
        manifest = json.loads((BASE / "manifest.json").read_bytes())
        output = normalize(manifest)
        self.assertEqual(len(output["assets"]), 2)
        self.assertFalse(output["forecast_input_eligible"])
        changed = copy.deepcopy(manifest); changed["forecast_input_eligible"] = True
        with self.assertRaisesRegex(ValueError, "outcomes"):
            normalize(changed)
        changed = copy.deepcopy(manifest); changed["sources"][0]["source_url"] = "https://unverified.example/PFE"
        with self.assertRaisesRegex(ValueError, "identity"):
            normalize(changed)
        changed = copy.deepcopy(manifest); changed["sources"] = [changed["sources"][0]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "excerpts"; path.mkdir()
            (path / "PFE.txt").write_text((BASE / "excerpts/PFE.txt").read_text().replace("0.43", "0.44"))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                normalize(changed, Path(directory))


if __name__ == "__main__":
    unittest.main()
