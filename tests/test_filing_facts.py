import unittest
from unittest.mock import patch
from scripts import refresh_data
from scripts.filing_facts import extract_filing_facts
from scripts.refresh_data import ttm

FILING = {'form': '10-Q', 'filing_date': '2026-07-29', 'report_date': '2026-06-30',
          'accession': '0000000001-26-000001', 'url': 'https://www.sec.gov/original.htm'}


def document(values='', context_extra='', identifier='1', unit='iso4217:USD', period='2026-06-30'):
    return f'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:us-gaap="http://fasb.org/us-gaap/2026"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:custom="http://example.com/custom">
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier>{identifier}</xbrli:identifier>{context_extra}</xbrli:entity>
      <xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>{period}</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:unit id="u"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit>
      <xbrli:unit id="e"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
      <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
      {values}</html>'''.encode()


def fact(value='12.34', name='us-gaap:EarningsPerShareDiluted', unit='e', extra=''):
    return f'<ix:nonFraction name="{name}" contextRef="c" unitRef="{unit}" {extra}>{value}</ix:nonFraction>'


class OriginalFilingFacts(unittest.TestCase):
    def extract(self, raw, cutoff='2026-10-26'):
        return extract_filing_facts(raw, FILING, 1, cutoff)

    def test_scale_sign_and_provenance(self):
        facts = self.extract(document(fact('1,234', 'us-gaap:NetIncomeLoss', 'u', 'scale="6" sign="-"')))
        row = facts['NetIncomeLoss']['units']['USD'][0]
        self.assertEqual(row['val'], -1234000000)
        self.assertEqual(row['filed'], FILING['filing_date'])
        self.assertEqual(row['source_url'], FILING['url'])

    def test_rejects_segments_other_entities_and_future_periods(self):
        for options in [{'context_extra': '<xbrli:segment/>'}, {'identifier': '2'}, {'period': '2026-09-30'}]:
            self.assertEqual(self.extract(document(fact(), **options)), {})
        self.assertEqual(self.extract(document(fact()), cutoff='2026-07-28'), {})

    def test_rejects_custom_concepts_units_formats_and_ambiguous_duplicates(self):
        for content in [fact(name='custom:EarningsPerShareDiluted'), fact(unit='u'),
                        fact(extra='format="custom:num-comma-decimal"'), fact()+fact('22.34'),
                        fact('NaN'), fact(extra='scale="99999"')]:
            self.assertEqual(self.extract(document(content)), {})
        self.assertEqual(len(self.extract(document(fact()+fact()))['EarningsPerShareDiluted']['units']['USD/shares']), 1)

    def test_ttm_retains_original_and_annual_components(self):
        facts = self.extract(document(fact('3')))
        rows = facts['EarningsPerShareDiluted']['units']['USD/shares']
        rows.extend([{'start': '2025-01-01', 'end': '2025-12-31', 'val': 5, 'filed': '2026-02-01'},
                     {'start': '2025-01-01', 'end': '2025-06-30', 'val': 2, 'filed': '2026-07-29'}])
        eps = ttm(facts, ['EarningsPerShareDiluted'], '2026-10-26', 'USD/shares')
        self.assertEqual(eps['value'], 6)
        self.assertEqual(eps['period_end'], '2026-06-30')
        self.assertEqual(len(eps['components']), 3)
        self.assertEqual(eps['components'][1]['source_kind'], 'original_inline_xbrl')

    def test_blocks_entity_declarations(self):
        with self.assertRaises(ValueError):
            self.extract(b'<!DOCTYPE x><x/>')


class FilingRecoveryIntegration(unittest.TestCase):
    def build(self, recovered, splits=None):
        old = {'eps': {'value': 1, 'period_end': '2026-03-31', 'filed': '2026-04-30'}, 'refresh_status': 'available'}
        price = {'history': [{'date': '2025-01-01', 'close': 10}, {'date': '2026-10-26', 'close': 11}],
                 'splits': splits or [], 'source_url': 'https://example.com/price'}
        with patch.object(refresh_data, 'prices', return_value=price), patch.object(refresh_data, 'filings', return_value=[FILING]), patch.object(refresh_data, 'financials', side_effect=[old, recovered]) as fetch:
            asset, errors = refresh_data.build_asset(('TEST', 'Test', 'Test', 1, .05, 15), '2026-10-26', {})
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(fetch.call_args.kwargs['original_filing'], FILING)
        return asset, errors

    def test_newer_report_uses_original_and_preserves_filing_date(self):
        eps = {'value': 2, 'period_end': '2026-06-30', 'filed': '2026-07-29'}
        asset, errors = self.build({'eps': eps, 'refresh_status': 'available'})
        self.assertEqual(asset['financials']['eps'], eps)
        self.assertEqual(errors, [])

    def test_failed_recovery_retains_old_data(self):
        asset, errors = self.build(ValueError('Unsupported document'))
        self.assertEqual(asset['financials']['eps']['period_end'], '2026-03-31')
        self.assertEqual(asset['financials']['original_filing_recovery']['status'], 'failed')
        self.assertEqual(len(errors), 1)

    def test_mixed_split_vintages_remain_blocked(self):
        recovered = {'eps': {'value': 2, 'period_end': '2026-06-30', 'filed': '2026-07-29',
                            'components': [{'end': '2025-12-31', 'accn': 'older'}, {'end': '2026-06-30', 'accn': FILING['accession']}]},
                     'original_filing_recovery': {'accession': FILING['accession']}, 'refresh_status': 'available'}
        asset, errors = self.build(recovered, [{'date': '2026-04-01', 'ratio': 2}])
        self.assertIsNone(asset['financials']['eps'])
        self.assertIn('original_eps_split_vintage_unverified', asset['quality_flags'])
        self.assertEqual(len(errors), 1)
