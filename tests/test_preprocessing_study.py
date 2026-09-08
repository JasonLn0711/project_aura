import unittest
from scripts.run_preprocessing_study import select_candidate


class PreprocessingGateTests(unittest.TestCase):
    def test_paired_gate_preserves_terms_and_requires_all_cases(self):
        rows = [dict(case_id=str(i), backend=b, status='ok', mer=m, cer=m, rare_term_hits=['AURA'])
                for i in range(10) for b,m in [('light',.2), ('candidate',.1)]]
        self.assertEqual(select_candidate(rows,'backend','light',['candidate']), 'candidate')
        rows[-1]['rare_term_hits'] = []
        self.assertEqual(select_candidate(rows,'backend','light',['candidate']), 'light')
        rows.pop()
        self.assertEqual(select_candidate(rows,'backend','light',['candidate']), 'light')
