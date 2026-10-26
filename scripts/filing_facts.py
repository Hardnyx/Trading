"""Conservative extraction of consolidated standard facts from original SEC iXBRL.

Custom concepts, dimensional contexts, transformations we do not implement and
conflicting duplicates are deliberately omitted. No inferred accounting values.
"""
import datetime as dt
import io
import math
import re
import xml.etree.ElementTree as ET

XBRLI = 'http://www.xbrl.org/2003/instance'
IX = {'http://www.xbrl.org/2013/inlineXBRL', 'http://www.xbrl.org/2008/inlineXBRL'}
TAGS = {
    'EarningsPerShareDiluted', 'RevenueFromContractWithCustomerExcludingAssessedTax',
    'Revenues', 'SalesRevenueNet', 'RevenuesNetOfInterestExpense', 'OperatingIncomeLoss',
    'NetIncomeLoss', 'ProfitLoss', 'NetCashProvidedByUsedInOperatingActivities',
    'PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets',
    'ShareBasedCompensation', 'PaymentsForRepurchaseOfCommonStock',
}


def extract_filing_facts(raw, filing, cik, cutoff):
    """Return companyfacts-shaped observations, preserving publication/provenance."""
    filed = filing.get('filing_date', '')
    report = filing.get('report_date', '')
    if not filed or filed > cutoff or not report or report > cutoff:
        return {}
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Document type/entity declarations are not supported')
    namespaces = {}
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(raw), events=('start-ns',)):
        if prefix in namespaces and namespaces[prefix] != uri:
            raise ValueError('Rebound XML namespace')
        namespaces[prefix] = uri
    root = ET.fromstring(raw)
    contexts, units = {}, {}
    for node in root.iter():
        if node.tag == f'{{{XBRLI}}}context':
            # Segment, scenario and explicit/typed members cannot be treated as
            # consolidated totals, even when their text looks like the total.
            if any(n.tag.rsplit('}', 1)[-1] in {'segment', 'scenario', 'explicitMember', 'typedMember'} for n in node.iter()):
                continue
            identifier = node.find(f'.//{{{XBRLI}}}identifier')
            if identifier is None or (identifier.text or '').lstrip('0') != str(cik).lstrip('0'):
                continue
            period = node.find(f'{{{XBRLI}}}period')
            if period is None:
                continue
            start = period.findtext(f'{{{XBRLI}}}startDate')
            end = period.findtext(f'{{{XBRLI}}}endDate')
            if not start or not end or end > report:
                continue
            try:
                if not 60 <= (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days <= 390:
                    continue
            except ValueError:
                continue
            contexts[node.get('id')] = (start, end)
        elif node.tag == f'{{{XBRLI}}}unit':
            def measures(element):
                values = []
                for measure in element.iter(f'{{{XBRLI}}}measure'):
                    prefix, _, local = (measure.text or '').partition(':')
                    values.append((namespaces.get(prefix), local))
                return values
            divide = node.find(f'{{{XBRLI}}}divide')
            if divide is None and measures(node) == [('http://www.xbrl.org/2003/iso4217', 'USD')]:
                units[node.get('id')] = 'USD'
            elif divide is not None:
                numerator = divide.find(f'{{{XBRLI}}}unitNumerator')
                denominator = divide.find(f'{{{XBRLI}}}unitDenominator')
                if numerator is not None and denominator is not None and measures(numerator) == [('http://www.xbrl.org/2003/iso4217', 'USD')] and measures(denominator) == [(XBRLI, 'shares')]:
                    units[node.get('id')] = 'USD/shares'
    candidates = {}
    for node in root.iter():
        if node.tag not in {f'{{{uri}}}nonFraction' for uri in IX}:
            continue
        prefix, _, tag = node.get('name', '').partition(':')
        if not re.fullmatch(r'https?://fasb.org/us-gaap/\d{4}', namespaces.get(prefix, '')) or tag not in TAGS:
            continue
        period = contexts.get(node.get('contextRef'))
        unit = units.get(node.get('unitRef'))
        expected = 'USD/shares' if tag == 'EarningsPerShareDiluted' else 'USD'
        if not period or unit != expected:
            continue
        transform = node.get('format')
        if transform:
            transform_prefix, _, transform_name = transform.partition(':')
            if transform_name != 'num-dot-decimal' or namespaces.get(transform_prefix) not in {
                'http://www.xbrl.org/inlineXBRL/transformation/2022-02-16',
                'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12',
                'http://www.xbrl.org/inlineXBRL/transformation/2015-02-26',
            }:
                continue
        if node.get('{http://www.w3.org/2001/XMLSchema-instance}nil') in {'true', '1'} or node.get('sign', '') not in {'', '-'}:
            continue
        text = ''.join(node.itertext()).strip().replace(',', '')
        if not re.fullmatch(r'\d+(?:\.\d+)?', text):
            continue
        try:
            scale = int(node.get('scale', '0'))
            if not -12 <= scale <= 12:
                continue
            value = float(text) * 10 ** scale * (-1 if node.get('sign') == '-' else 1)
        except (ValueError, OverflowError):
            continue
        if math.isfinite(value):
            candidates.setdefault((tag, unit, *period), set()).add(value)
    facts = {}
    for (tag, unit, start, end), values in candidates.items():
        if len(values) != 1:
            continue
        row = {'start': start, 'end': end, 'val': values.pop(), 'filed': filed,
               'accn': filing['accession'], 'form': filing['form'],
               'source_url': filing['url'], 'source_kind': 'original_inline_xbrl'}
        facts.setdefault(tag, {'units': {}})['units'].setdefault(unit, []).append(row)
    return facts
