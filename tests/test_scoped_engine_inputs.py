import copy
import unittest
from unittest.mock import patch

from scripts.scoped_engine_inputs import reconstruct_stock, reconstructed_holdings, compile_inputs
from scripts.historical_sources import MARKET_COMMIT


class ScopedEngineInputs(unittest.TestCase):
    def setUp(self):
        self.cut = '2024-12-31'
        self.original = {'symbol': 'AAA', 'type': 'stock', 'currency': 'USD',
            'financials': {'revenue': {'value': 999}}, 'analyst_estimates': {'eps': 999},
            'bond_profile': {'yield': .5}, 'splits': [{'date': '2025-06-01', 'ratio': 10}],
            'assumptions': {'growth': .04, 'multiple': 15},
            'distribution_index': {'complete_ex_date_index': True, 'currency': 'USD',
                'coverage_start': '2020-01-01', 'coverage_end': '2026-01-01',
                'records': [{'ex_date': '2024-06-01', 'amount_per_share': .1},
                            {'ex_date': self.cut, 'amount_per_share': 1000},
                            {'ex_date': '2025-01-01', 'amount_per_share': 2000}]}}
        self.history = {'declared_split_reversal_factor': 10,
                        'history': [{'date': self.cut, 'close': 100, 'adj_close': 90}]}
        self.source = {'rows': [{'filed': '2025-02-01', 'end': '2024-12-31', 'form': '10-K'}],
                       'observed_at': '2026-10-30T00:00:00Z', 'full_response_sha256': 'abc'}
        self.eps = {'value': .2, 'reported_value': 2, 'future_split_divisor': 10,
                    'filed': '2024-11-01', 'period_end': '2024-09-30'}

    def stock(self):
        with patch('scripts.scoped_engine_inputs.eps_at', return_value=(self.eps, None)):
            return reconstruct_stock(self.original, self.history, self.source, self.cut, '2026-10-28')

    def test_eps_price_dividend_same_origin_share_units(self):
        a, reason = self.stock()
        self.assertIsNone(reason)
        self.assertEqual(a['financials']['eps']['value'], 2)
        self.assertEqual(a['price'], 100)
        self.assertEqual(a['dividend_per_share'], 1)
        self.assertNotIn('future_split_divisor', a['financials']['eps'])
        self.assertEqual(a['splits'], [])
        self.assertEqual(a['filings'], [])

    def test_current_quality_analyst_and_profiles_are_not_copied(self):
        a, _ = self.stock()
        self.assertNotIn('analyst_estimates', a)
        self.assertNotIn('bond_profile', a)
        self.assertNotIn('revenue', a['financials'])
        self.assertEqual(a['financials']['observed_at'], self.source['observed_at'])
        self.assertFalse(a['historical_reconstruction']['original_financial_quality_verified'])

    def test_invalid_or_duplicated_dividends_fail_closed(self):
        records = self.original['distribution_index']['records']
        for amount in (float('nan'), float('inf'), -1, True):
            with self.subTest(amount=amount):
                records[0]['amount_per_share'] = amount
                self.assertEqual(self.stock()[1], 'invalid-trailing-dividends')
        records[0]['amount_per_share'] = .1
        records.append(copy.deepcopy(records[0]))
        self.assertEqual(self.stock()[1], 'invalid-trailing-dividends')

    def test_missing_distribution_coverage_is_not_zero_dividends(self):
        self.original['distribution_index']['complete_ex_date_index'] = False
        self.assertEqual(self.stock()[1], 'incomplete-trailing-provider-dividends')

    def test_missing_eps_never_gets_a_current_fallback(self):
        with patch('scripts.scoped_engine_inputs.eps_at', return_value=(None, 'missing_ttm_or_fy_fallback')):
            self.assertEqual(reconstruct_stock(self.original, self.history, self.source, self.cut, '2026-10-28'),
                             (None, 'missing_ttm_or_fy_fallback'))

    def test_holdings_clock_covers_identifier_evidence_and_preserves_retrieval(self):
        def position(ticker, weight):
            return {'weight': weight, 'ticker_observation': {'source_ticker': ticker,
                    'evidence': [{'available_after_day': '2024-12-10'}]}}
        origin = {'cut': self.cut, 'spy_source': {'available_after_day': '2024-11-01',
                  'as_of': '2024-09-30', 'accession': '123-456'},
                  'positions': [position('AAA', .4), position('DUP', .1), position('DUP', .1), position('BAD/A', .1)]}
        h = reconstructed_holdings(origin, '2026-10-30T00:00:00Z')
        self.assertEqual(h['observed_at'], '2024-12-11T12:00:00Z')
        self.assertEqual(h['retrieved_at'], '2026-10-30T00:00:00Z')
        self.assertFalse(h['original_capture_verified'])
        self.assertEqual(h['positions'], [{'symbol': 'AAA', 'weight': .4}])
        origin['positions'][0]['ticker_observation']['evidence'][0]['available_after_day'] = self.cut
        with self.assertRaisesRegex(ValueError, 'availability'):
            reconstructed_holdings(origin, '2026-10-30T00:00:00Z')

    def test_selection_is_chronological_not_input_order_or_future_returns(self):
        dates = ['2025-04-30', '2025-05-30', '2024-12-31', '2023-01-31']
        protocol = {'source_market_commit': MARKET_COMMIT,
                    'selection': {'minimum_weight': .7, 'maximum_origins': 2}}
        market = {'price_as_of': '2026-10-28', 'assets': [{'symbol': 'SPY', 'type': 'etf',
                  'history': [{'date': d, 'close': 100, 'adj_close': 100} for d in sorted(dates)]}]}
        prices = {'matrix': [{'cut': d, 'research_history_weight': .8 if d != '2023-01-31' else .6,
                              'future_return': 999 if d == '2025-05-30' else -999} for d in dates]}
        identifiers = {'matrix': [{'cut': d, 'spy_source': {'as_of': '2024-09-30',
            'available_after_day': '2024-11-01', 'accession': '123'}, 'positions': []} for d in dates]}
        r = compile_inputs(market, {'price_cut': market['price_as_of'], 'input_market_sha256': 'x'}, prices,
            {'origins': {d: [] for d in dates}}, identifiers, {'macro': {d: {} for d in dates}},
            protocol, '2026-10-31T00:00:00Z', {'123': '2026-10-30T00:00:00Z'})
        self.assertEqual([o['cut'] for o in r['origins']], ['2024-12-31', '2025-04-30'])
        self.assertEqual(len(r['schedule']), 4)
        self.assertFalse(r['production_eligible'])
        self.assertEqual(r['predictive_validation'], 'not-established')


if __name__ == '__main__':
    unittest.main()
