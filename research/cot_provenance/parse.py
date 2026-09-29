"""Parse the frozen CME Bitcoin Legacy Futures Only short-format COT section.

This module has no market-price or performance dependency. It rejects ambiguous
or malformed content rather than guessing a field from neighboring contracts.
"""

import hashlib
import html
import json
import re

SCHEMA = 'RIE-006-COT-LEGACY-CME-SHORT/1'
FIELDS = (
    'noncommercial_long', 'noncommercial_short', 'noncommercial_spreading',
    'commercial_long', 'commercial_short', 'total_long', 'total_short',
    'nonreportable_long', 'nonreportable_short',
)


def parse_bitcoin(raw: bytes, report_date: str) -> dict:
    text = raw.decode('iso-8859-1')
    if '<html' not in text.lower() or '<pre' not in text.lower():
        raise ValueError('not a CFTC HTML report')
    pre = re.search(r'<pre\b[^>]*>(.*?)</pre>', text, re.I | re.S)
    if pre is None:
        raise ValueError('missing preformatted report')
    body = html.unescape(pre.group(1))
    matches = list(re.finditer(r'^BITCOIN - CHICAGO MERCANTILE EXCHANGE\s+Code-133741\s*$', body, re.M))
    if len(matches) != 1:
        raise ValueError(f'expected exactly one standard Bitcoin section, found {len(matches)}')
    section = body[matches[0].start():]
    first_line_end = section.find('\n')
    next_section = re.search(r'^\S.*Code-[0-9A-Za-z+]+\s*$', section[first_line_end+1:], re.M)
    if next_section:
        section = section[:first_line_end+1+next_section.start()]
    date = re.search(r'^FUTURES ONLY POSITIONS AS OF (\d\d)/(\d\d)/(\d\d)\s*\|', section, re.M)
    if not date or f'20{date[3]}-{date[1]}-{date[2]}' != report_date:
        raise ValueError('report date or Futures Only family mismatch')
    unit_oi = re.search(r'^\(5 Bitcoins\)\s+OPEN INTEREST:\s*([\d,]+)\s*$', section, re.M)
    if not unit_oi:
        raise ValueError('unit or open interest mismatch')
    commitments = re.search(r'^COMMITMENTS\s*\n([^\n]+)', section, re.M)
    if not commitments:
        raise ValueError('commitments row missing')
    numbers = re.findall(r'\d[\d,]*', commitments[1])
    if len(numbers) != 9:
        raise ValueError('commitments row must have nine columns')
    values = [int(n.replace(',', '')) for n in numbers]
    result = {'schema': SCHEMA, 'report_family': 'Legacy Futures Only',
              'exchange': 'Chicago Mercantile Exchange', 'contract_code': '133741',
              'contract_unit': '5 Bitcoins', 'report_date': report_date,
              'open_interest': int(unit_oi[1].replace(',', ''))}
    result.update(zip(FIELDS, values))
    return result


def semantic_sha256(record: dict) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(canonical).hexdigest()
