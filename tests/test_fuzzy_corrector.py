import tempfile
import unittest
from pathlib import Path

import yaml

from asr_postprocess.fuzzy_corrector import correct_transcript


class FuzzyCorrectorTests(unittest.TestCase):
    def test_corrects_only_high_confidence_glossary_terms(self):
        transcript = "今天志德灣會和會成智醫討論 iMBS，Gamma summary 先不要改我覺得可能有點不舒服。"

        result = correct_transcript(transcript)

        self.assertEqual(
            result.corrected_transcript,
            "今天智德萬會和慧誠智醫討論 iMVS，Gemma summary 先不要改我覺得可能有點不舒服。",
        )
        self.assertFalse(result.llm_verification)
        self.assertEqual(len(result.correction_log), 4)
        self.assertIn("我覺得可能有點不舒服", result.corrected_transcript)
        first = result.correction_log[0]
        self.assertEqual(first["span"], "志德灣")
        self.assertEqual(first["original"], "志德灣")
        self.assertEqual(first["corrected"], "智德萬")
        self.assertEqual(first["score"], 100.0)
        self.assertEqual(first["category"], "organizations")
        self.assertEqual(first["method"], "rapidfuzz")
        self.assertTrue(first["accepted"])

    def test_does_not_rewrite_natural_sentences_without_glossary_match(self):
        transcript = "我覺得可能有點不舒服，今天先不要改一般自然語句。"

        result = correct_transcript(transcript)

        self.assertEqual(result.corrected_transcript, transcript)
        self.assertEqual(result.correction_log, [])

    def test_protects_exact_glossary_terms_from_internal_alias_replacements(self):
        transcript = "Gamma Knife 是 Elekta 的。Gamma summary 才是模型名稱錯字。"

        result = correct_transcript(transcript)

        self.assertEqual(result.corrected_transcript, "Gamma Knife 是 Elekta 的。Gemma summary 才是模型名稱錯字。")
        self.assertEqual(len(result.correction_log), 1)
        self.assertEqual(result.correction_log[0]["original"], "Gamma")
        self.assertEqual(result.correction_log[0]["corrected"], "Gemma")
        self.assertEqual(result.correction_log[0]["start"], 23)

    def test_respects_category_thresholds_for_uncertain_medical_terms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            glossary_path = Path(tmpdir) / "domain_glossary.yaml"
            glossary_path.write_text(
                yaml.safe_dump(
                    {
                        "settings": {
                            "llm_verification": False,
                            "thresholds": {
                                "organizations": 85,
                                "medical_terms": 92,
                                "technical_terms": 90,
                                "people": 90,
                            },
                        },
                        "organizations": [],
                        "medical_terms": ["血氧"],
                        "technical_terms": [],
                        "people": [],
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = correct_transcript("今天血壓看起來正常。", glossary_path=glossary_path)

        self.assertEqual(result.corrected_transcript, "今天血壓看起來正常。")
        self.assertEqual(result.correction_log, [])

    def test_denylisted_review_rejects_are_logged_without_correction(self):
        transcript = "陽明交大和智慧財產今天討論 detector。"

        result = correct_transcript(transcript)

        self.assertEqual(result.corrected_transcript, transcript)
        rejected = [entry for entry in result.correction_log if not entry["accepted"]]
        self.assertEqual(len(rejected), 3)
        self.assertTrue(all(entry["review_status"] == "denylist" for entry in rejected))
        self.assertEqual(
            {(entry["original"], entry["corrected"]) for entry in rejected},
            {
                ("陽明交大", "國立陽明交通大學"),
                ("智慧財產", "智慧財產局"),
                ("detector", "Detector+"),
            },
        )

    def test_unsure_review_cases_are_logged_as_manual_review_required_without_correction(self):
        transcript = "5.0k 和 50L510K 需要 max 確認，陽明院也需要看上下文。"

        result = correct_transcript(transcript)

        self.assertEqual(result.corrected_transcript, transcript)
        manual_review = [entry for entry in result.correction_log if entry["review_status"] == "manual_review_required"]
        self.assertEqual(len(manual_review), 4)
        self.assertTrue(all(not entry["accepted"] for entry in manual_review))
        self.assertEqual(
            {(entry["original"], entry["corrected"]) for entry in manual_review},
            {
                ("5.0k", "510(k)"),
                ("50L510K", "510(k)"),
                ("max", "Max"),
                ("陽明院", "陽明醫院"),
            },
        )


if __name__ == "__main__":
    unittest.main()
