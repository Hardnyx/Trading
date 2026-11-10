"""Source-prolog inspection only reports bounded immutable original bytes."""
import hashlib
import unittest

from scripts.sec_xbrl_prolog_probe import inspect_document


class PrologProbeTests(unittest.TestCase):
    def test_ascii_whitespace_and_xml_declaration_positions_are_observed(self):
        prefix = b"\n \r\n<?xml version='1.0'?>\n<r>" + b"x"*100
        result = inspect_document(prefix)
        self.assertEqual(result["sha256"], hashlib.sha256(prefix).hexdigest())
        self.assertEqual(result["first_non_ascii_whitespace_offset"], 4)
        self.assertEqual(result["xml_declarations_in_first_1024_bytes"], [4])
        self.assertTrue(result["begins_with_xml_declaration_after_ascii_whitespace"])
        self.assertEqual(bytes.fromhex(result["first_160_bytes_hex"]), prefix)

    def test_bom_and_previous_declaration_are_not_silently_accepted(self):
        source = b"\xef\xbb\xbf\n<?xml version='1.0'?>\n<r>" + b"x"*100
        result = inspect_document(source)
        self.assertTrue(result["contains_utf8_bom_in_first_8_bytes"])
        self.assertFalse(result["begins_with_xml_declaration_after_ascii_whitespace"])
        self.assertEqual(result["xml_declarations_in_first_1024_bytes"], [4])


if __name__ == "__main__":
    unittest.main()
