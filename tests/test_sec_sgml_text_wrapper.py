"""Observed SEC SGML transport tags are removed only as exact pairs."""
import unittest

from scripts.sec_sgml_text_wrapper import unwrap_sec_xml_payload


class SecSgmlTextWrapperTests(unittest.TestCase):
    def test_transport_envelope_matches_observed_original_lengths(self):
        for kind in ("XBRL", "XML"):
            with self.subTest(kind=kind):
                content = (b"<?xml version='1.0'?>\n<root>"
                           + b"x"*50 + b"</root>")
                wrapped = b"<" + kind.encode() + b">\n" + content + (
                    b"\n</" + kind.encode() + b">")
                self.assertEqual(unwrap_sec_xml_payload(wrapped,kind), content)
                self.assertEqual(unwrap_sec_xml_payload(wrapped+b"\n",kind), content)
                self.assertEqual(unwrap_sec_xml_payload(wrapped+b"\r\n",kind), content)
                self.assertEqual(len(wrapped)-len(content),
                                 15 if kind=="XBRL" else 13)
                self.assertEqual(unwrap_sec_xml_payload(content,kind), content)

    def test_unsafe_or_incomplete_transport_envelope_fails(self):
        content = b"<?xml version='1.0'?><root>" + b"x"*50 + b"</root>"
        for raw, kind in (
            (b"<XML>\n"+content+b"\n</XBRL>", "XML"),
            (b"<XML>\n"+content, "XML"),
            (b"<XML>\n"+content+b"\n</XML>extra", "XML"),
            (b"<XML>\n"+content+b"\n</XML>\n\n", "XML"),
            (b"<XBRL>\n"+content+b"\n</XBRL>", "XML"),
            (b"<XBRL> "+content+b"\n</XBRL>", "XBRL"),
            (b"<XML>\n<XML>\n"+content+b"\n</XML>", "XML"),
        ):
            with self.subTest(raw=raw[:30],kind=kind), self.assertRaises(ValueError):
                unwrap_sec_xml_payload(raw,kind)
        with self.assertRaises(ValueError):
            unwrap_sec_xml_payload("XML text", "XML")
        with self.assertRaises(ValueError):
            unwrap_sec_xml_payload(content,"UNTRUSTED")


if __name__ == "__main__":
    unittest.main()
