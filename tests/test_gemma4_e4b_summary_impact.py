from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts.run_gemma4_e4b_summary_impact import (
    DEFAULT_CONFIG,
    FIXED_OLLAMA_MODEL,
    FIXED_MODEL_ID,
    GATE_NAME,
    OllamaGemmaRunner,
    aggregate_report,
    build_summary_prompt,
    check_model_available,
    check_ollama_available,
    classify_decision_change,
    discover_real_transcript_artifact_sets,
    evaluate_pair,
    hallucinated_terms,
    load_config,
    parse_summary_json,
    prompt_uses_correction_log,
    runner_config,
    summary_has_content,
)
from scripts.evaluate_summary_impact import ArtifactSet, load_domain_terms


class Gemma4E4BSummaryImpactTests(unittest.TestCase):
    def test_gemma4_e4b_config_exists(self) -> None:
        self.assertTrue(DEFAULT_CONFIG.exists())
        config = load_config(DEFAULT_CONFIG)
        self.assertEqual(config["gate"], GATE_NAME)
        self.assertEqual(config["model"]["name"], "gemma4_e4b")

    def test_no_fallback_model_allowed(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        self.assertEqual(config.model_id, FIXED_MODEL_ID)
        self.assertEqual(config.runner, "ollama")
        self.assertEqual(config.ollama_model, FIXED_OLLAMA_MODEL)
        self.assertEqual(config.precision_variant, "ollama_qat_q4_0_local_tag")
        self.assertTrue(config.reasoning_enabled)
        self.assertEqual(config.max_output_tokens, 1536)
        self.assertEqual(config.ollama_num_ctx, 32768)
        self.assertFalse(config.allow_fallback_model)
        self.assertFalse(config.allow_download)
        self.assertTrue(config.local_files_only)

    def test_ollama_runner_enables_and_checks_reasoning(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        with patch(
            "scripts.run_gemma4_e4b_summary_impact.ollama_request",
            return_value={
                "message": {"content": "{}", "thinking": ""},
                "done": True,
            },
        ) as request:
            self.assertEqual(OllamaGemmaRunner(config).generate("逐字稿"), "{}")

        payload = request.call_args.kwargs["payload"]
        self.assertEqual(request.call_args.args[1], "/api/chat")
        self.assertTrue(payload["think"])
        self.assertEqual(payload["options"]["num_predict"], 1536)

    def test_external_calls_forbidden(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        self.assertFalse(config["privacy"]["external_calls"])
        self.assertFalse(config["privacy"]["cloud_calls"])
        self.assertTrue(config["model"]["local_only"])

    def test_ollama_runner_requires_localhost_gemma4_e4b(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        self.assertEqual(config.ollama_model, FIXED_OLLAMA_MODEL)
        self.assertTrue(config.ollama_host.startswith("http://127.0.0.1"))
        with patch("scripts.run_gemma4_e4b_summary_impact.ollama_request", side_effect=OSError("not running")):
            available, reason = check_ollama_available(config)
        self.assertFalse(available)
        self.assertIn("Ollama localhost runner not available", reason)

    def test_gate_rejects_runtime_or_reasoning_contract_drift(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        for changed in (
            replace(config, runner="transformers"),
            replace(config, max_output_tokens=7),
            replace(config, ollama_host="http://localhost:11434@external.example"),
        ):
            with self.subTest(changed=changed):
                available, _ = check_model_available(changed)
                self.assertFalse(available)
        with self.assertRaises(RuntimeError):
            OllamaGemmaRunner(replace(config, max_output_tokens=7))

    def test_raw_transcript_context_not_emitted(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        self.assertFalse(config["privacy"]["emit_raw_transcript_context"])
        self.assertFalse(config["privacy"]["commit_raw_model_outputs"])

    def test_model_missing_fails_gracefully(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        with patch("scripts.run_gemma4_e4b_summary_impact.ollama_request", return_value={"models": []}):
            available, reason = check_model_available(config)
        report = aggregate_report([], complete_artifact_sets=0, model_available=available, reason=reason, config=config)
        self.assertFalse(report["model_available"])
        self.assertFalse(report["external_calls"])
        self.assertEqual(report["evaluated_files"], 0)
        self.assertIn("Ollama model not found", reason)

    def test_summary_prompt_does_not_include_correction_log(self) -> None:
        prompt = build_summary_prompt("智德萬 討論 ASR。")
        self.assertFalse(prompt_uses_correction_log(prompt))
        self.assertIn("Preserve domain-specific names exactly as written", prompt)

    def test_report_schema(self) -> None:
        config = runner_config(load_config(DEFAULT_CONFIG))
        report = aggregate_report(
            [],
            complete_artifact_sets=0,
            model_available=False,
            reason="Gemma 4 E4B local model not found",
            config=config,
            generation_failures=[
                {
                    "file_id": "sample",
                    "reason": "empty_structured_summary",
                    "raw_summary_has_content": False,
                    "corrected_summary_has_content": False,
                }
            ],
        )
        expected = {
            "gate",
            "model",
            "fixed_model_id",
            "model_id",
            "runner",
            "endpoint",
            "ollama_model",
            "model_source",
            "precision_variant",
            "fp8_checkpoint",
            "download_during_gate",
            "local_files_only",
            "model_available",
            "external_calls",
            "cloud_calls",
            "raw_transcript_context_emitted",
            "raw_email_pdf_read",
            "complete_artifact_sets",
            "evaluated_files",
            "files_with_both_summaries",
            "domain_terms_raw_summary",
            "domain_terms_corrected_summary",
            "domain_term_delta",
            "raw_asr_error_spans_in_raw_summaries",
            "canonical_terms_in_corrected_summaries",
            "rejected_leakage",
            "manual_review_leakage",
            "decision_changes",
            "hallucinated_entity_watch_count",
            "claim_scope",
        }
        self.assertTrue(expected.issubset(report))
        self.assertEqual(report["fixed_model_id"], "google/gemma-4-E4B-it")
        self.assertEqual(report["runner"], "ollama")
        self.assertEqual(report["endpoint"], "http://127.0.0.1:11434")
        self.assertEqual(report["ollama_model"], FIXED_OLLAMA_MODEL)
        self.assertFalse(report["fp8_checkpoint"])
        self.assertFalse(report["download_during_gate"])
        self.assertEqual(report["summary_generation_failures"], 1)
        self.assertEqual(report["generation_failures"][0]["reason"], "empty_structured_summary")

    def test_empty_structured_summary_has_no_content(self) -> None:
        self.assertFalse(summary_has_content(parse_summary_json("{}")))
        self.assertTrue(summary_has_content(parse_summary_json(json.dumps({"executive_summary": "完成摘要"}))))
        self.assertTrue(summary_has_content(parse_summary_json(json.dumps({"action_items": ["確認模型輸出"]}))))
        self.assertTrue(
            summary_has_content(parse_summary_json(json.dumps({"domain_terms": {"organizations": ["智德萬"]}})))
        )

    def test_rejected_terms_do_not_count_as_improvements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = self._artifact(Path(tmp))
            raw_summary = parse_summary_json(
                json.dumps({"domain_terms": {"organizations": ["志德灣"], "technical_terms": ["iMBS"]}})
            )
            corrected_summary = parse_summary_json(
                json.dumps({"domain_terms": {"organizations": ["智德萬"], "technical_terms": ["Detector+"]}})
            )
            row = evaluate_pair(artifact, raw_summary, corrected_summary, load_domain_terms())
        self.assertIn("Detector+", row["rejected_leakage_terms"])
        self.assertNotIn("Detector+", row["canonical_terms_in_corrected_summary"])

    def test_manual_review_terms_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = self._artifact(Path(tmp))
            corrected_summary = parse_summary_json(
                json.dumps({"domain_terms": {"people": ["Max"], "organizations": ["智德萬"]}})
            )
            row = evaluate_pair(artifact, parse_summary_json("{}"), corrected_summary, load_domain_terms())
        self.assertIn("Max", row["manual_review_leakage_terms"])

    def test_decision_change_categories(self) -> None:
        raw = {"key_decisions": ["use imbs"], "action_items": [], "domain_terms": {}}
        corrected = {"key_decisions": ["use iMVS"], "action_items": [], "domain_terms": {}}
        self.assertEqual(classify_decision_change(raw, corrected, "iMVS", set()), "domain_term_only")

        corrected_manual = {"key_decisions": ["assign Max"], "action_items": [], "domain_terms": {}}
        self.assertEqual(classify_decision_change(raw, corrected_manual, "Max", {"Max"}), "manual_review_needed")

        corrected_semantic = {"key_decisions": ["approve deployment"], "action_items": ["ship tomorrow"], "domain_terms": {}}
        self.assertEqual(classify_decision_change(raw, corrected_semantic, "", set()), "possible_semantic_change")

    def test_hallucinated_entity_watch(self) -> None:
        summary = parse_summary_json(json.dumps({"domain_terms": {"organizations": ["智德萬", "不存在公司"]}}))
        self.assertEqual(hallucinated_terms(summary, "智德萬 討論 ASR"), ["不存在公司"])

    def test_discovers_real_transcript_pairs_with_separate_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript_dir = root / "meeting"
            log_dir = root / "reports" / "asr_fuzzy_correction_logs"
            transcript_dir.mkdir(parents=True)
            log_dir.mkdir(parents=True)
            raw = transcript_dir / "meeting_raw.txt"
            final = transcript_dir / "meeting_final.txt"
            raw.write_text("志德灣\n", encoding="utf-8")
            final.write_text("智德萬\n", encoding="utf-8")
            (log_dir / "001_meeting_raw_correction_log.json").write_text(
                json.dumps(
                    {"correction_log": [{"accepted": True, "original": "志德灣", "corrected": "智德萬"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            artifacts = discover_real_transcript_artifact_sets([root], log_dir=log_dir)

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].raw_transcript.name, "meeting_raw.txt")
        self.assertEqual(artifacts[0].corrected_transcript.name, "meeting_final.txt")

    def _artifact(self, root: Path) -> ArtifactSet:
        raw = root / "sample_raw.txt"
        corrected = root / "sample_corrected.txt"
        log = root / "sample_correction_log.json"
        raw.write_text("志德灣 iMBS detector max\n", encoding="utf-8")
        corrected.write_text("智德萬 iMVS detector max\n", encoding="utf-8")
        log.write_text(
            json.dumps(
                [
                    {"accepted": True, "original": "志德灣", "corrected": "智德萬", "category": "organizations"},
                    {"accepted": True, "original": "iMBS", "corrected": "iMVS", "category": "technical_terms"},
                    {
                        "accepted": False,
                        "original": "detector",
                        "corrected": "Detector+",
                        "category": "technical_terms",
                        "review_status": "rejected",
                    },
                    {
                        "accepted": False,
                        "original": "max",
                        "corrected": "Max",
                        "category": "people",
                        "review_status": "manual_review_required",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return ArtifactSet("sample", raw, corrected, log, None, None)


if __name__ == "__main__":
    unittest.main()
