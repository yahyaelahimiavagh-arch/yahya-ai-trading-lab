import hashlib
import json
import unittest
from pathlib import Path

from research.cot_provenance.parse import parse_bitcoin, semantic_sha256

ROOT = Path(__file__).resolve().parents[1] / 'research' / 'cot_provenance' / 'artifacts'
DATES = {'S1': '2018-05-01', 'S2': '2021-06-15', 'S3': '2018-12-24',
         'S4': '2023-01-31', 'S5': '2025-09-30'}

class CotProvenanceTest(unittest.TestCase):
    def test_archived_current_semantic_fields(self):
        for sample, date in DATES.items():
            with self.subTest(sample=sample):
                archived = parse_bitcoin((ROOT / f'{sample}-archive.html').read_bytes(), date)
                current = parse_bitcoin((ROOT / f'{sample}-current.html').read_bytes(), date)
                self.assertEqual(archived, current)
                self.assertEqual(archived['contract_code'], '133741')
                self.assertEqual(archived['contract_unit'], '5 Bitcoins')
                self.assertGreater(archived['open_interest'], 0)
                self.assertEqual(len(semantic_sha256(archived)), 64)

    def test_reject_error_page_missing_code_and_wrong_date(self):
        good = (ROOT / 'S1-archive.html').read_bytes()
        for data in (b'<html><pre>403 Forbidden</pre></html>',
                     good.replace(b'Code-133741', b'Code-133742')):
            with self.assertRaises(ValueError):
                parse_bitcoin(data, DATES['S1'])
        with self.assertRaises(ValueError):
            parse_bitcoin(good, '2018-05-08')

    def test_raw_hashes_match_manifest(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        for sample in manifest['samples']:
            for kind in ('archive', 'current'):
                item = sample[kind]
                data = (ROOT / item['path']).read_bytes()
                self.assertEqual(len(data), item['byte_length'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])

if __name__ == '__main__':
    unittest.main()
