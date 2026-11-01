"""Bind and preserve an integration cohort without recomputing its decisions."""
import argparse
import gzip
import json
from pathlib import Path

if __package__:
    from .historical_sources import ROOT, canonical, sha
else:
    from historical_sources import ROOT, canonical, sha


def summarize(inputs_raw, results_raw, archive_dir):
    bundle = json.loads(gzip.decompress(inputs_raw))
    full = json.loads(gzip.decompress(results_raw))
    if (full['input_file_sha256'] != sha(inputs_raw) or full['protocol'] != bundle['protocol'] or
            full['certified_full_engine_cuts'] != 0 or full['production_eligible'] is not False or
            full['predictive_validation'] != 'not-established'):
        raise ValueError('Cohort identity or scope mismatch')
    expected = [r['cut'] for r in bundle['origins']]
    if [r['cut'] for r in full['results']] != expected:
        raise ValueError('Missing or reordered origin')
    manifest_json = json.dumps(full['production_sources'], separators=(',', ':'), ensure_ascii=False).encode()
    if sha(manifest_json) != full['production_sources_sha256']:
        raise ValueError('Production source manifest hash mismatch')
    for origin, result in zip(bundle['origins'], full['results']):
        if sha(canonical(origin['snapshot'])) != origin['snapshot_sha256'] or result['stored_snapshot_sha256'] != origin['snapshot_sha256']:
            raise ValueError('Snapshot hash mismatch')
    rows = []
    for r in full['results']:
        p, prepared = r['proposal'], r['prepared']
        selection, robust = p['diagnostics']['reliableSelection'], p['diagnostics']['robustDecision']
        volatility = {v['symbol']: v['value'] for v in prepared['annual_volatility']}
        rows.append({'cut': r['cut'], 'usable_stocks': r['usable_stocks'], 'eps_exclusions': r['eps_exclusions'],
            'stored_snapshot_sha256': r['stored_snapshot_sha256'],
            'engine_snapshot_json_sha256': r['engine_snapshot_json_sha256'], 'request_sha256': r['request_sha256'],
            'forecasts': [{'symbol': a['symbol'], 'annual_anchor': a['annual'], 'low': a['low'], 'high': a['high'],
                          'annual_volatility': volatility[a['symbol']], 'source': a['source'],
                          'confidence': a['confidence']} for a in prepared['anchors']],
            'risk': {k: prepared[k] for k in ('conditional_risk', 'calibration_end', 'observations', 'regime_probabilities', 'factor_covariance')},
            'decision': {'status': p['status'], 'reason': p['reason'], 'positions': p['positions'],
                'trade_plan': p['trade_plan'], 'current_account': p['current_account'], 'excluded': p['excluded'],
                'published': p['selection']['published'], 'eligible': p['selection']['eligible'],
                'simulated': p['selection']['simulated'], 'benchmark_only_proxy': p['selection']['benchmarkOnlyProxy'],
                'robust_status': robust['status'], 'robust_paths': robust['paths'],
                'robust_screened': selection['screened'], 'robust_finalists': selection['finalists'],
                'robust_admissible': selection['admissible'], 'global_optimality_claim': selection['globalOptimalityClaim'],
                'confirmation_attempts': selection['confirmationAttempts'],
                'allocation_ranges': p['diagnostics']['stability']['ranges'],
                'range_scope': 'Fallback hold when no transition is admissible; not evidence of a stable optimum',
                'cash_yield': p['mandate']['cashYield'], 'model_version': p['model_version']}})
    return {'protocol': full['protocol'], 'generated_at': full['generated_at'],
        'production_eligible': False, 'prospective': False, 'predictive_validation': 'not-established',
        'executed_development_cuts': len(rows), 'certified_full_engine_cuts': 0,
        'input_file': str(archive_dir / 'inputs.json.gz'), 'input_file_sha256': sha(inputs_raw),
        'full_results_file': str(archive_dir / 'results.json.gz'), 'full_results_sha256': sha(results_raw),
        'runner_sha256': full['runner_sha256'], 'production_sources_sha256': full['production_sources_sha256'],
        'input_provenance': {k: bundle[k] for k in ('source_market_commit', 'canonical_market_sha256',
            'price_audit_sha256', 'eps_archive_sha256', 'pilot_protocol_sha256', 'builder_sha256')},
        'hash_formats': {'stored_snapshot': 'Python canonical sorted JSON',
                        'engine_snapshot_json': 'JSON.stringify in runner; intentionally distinct serialization'},
        'schedule': bundle['schedule'], 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', default='out/scoped-engine-inputs-v1.json.gz')
    parser.add_argument('--results', default='out/scoped-engine-results-v1.json.gz')
    parser.add_argument('--archive-dir', default='data/historical/scoped-engine-pilot-v1')
    parser.add_argument('--report', default='data/historical/scoped-engine-pilot-v1/report.json')
    args = parser.parse_args()
    inputs_raw, results_raw = Path(args.inputs).read_bytes(), Path(args.results).read_bytes()
    archive_dir = Path(args.archive_dir)
    report = summarize(inputs_raw, results_raw, archive_dir)
    # Refuse to replace a different cohort. Use a new directory for another run.
    for name, raw in [('inputs.json.gz', inputs_raw), ('results.json.gz', results_raw)]:
        target = archive_dir / name
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('Immutable cohort already exists; choose a new archive directory')
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / 'inputs.json.gz').write_bytes(inputs_raw)
    (archive_dir / 'results.json.gz').write_bytes(results_raw)
    path = Path(args.report); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(report) + b'\n')
    print(json.dumps({'executed_development_cuts': report['executed_development_cuts'],
                      'certified_full_engine_cuts': 0, 'production_eligible': False}))


if __name__ == '__main__':
    main()
