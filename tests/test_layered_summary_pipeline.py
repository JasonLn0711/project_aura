from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from summary.field_schemas import (
    BASE_MODEL_ID,
    EXTRACTOR_FIELDS,
    EXTRACTOR_NAMES,
    OLLAMA_MODEL_TAG,
    OLLAMA_NUM_CTX,
    validate_extractor_value,
    validate_field_value,
    validate_final_summary,
)
from summary.layered_summary_pipeline import (
    DEFAULT_LAYER_PROMPT_DIR,
    build_extractor_prompt,
    extract_with_repair,
    generate_layered_summary,
    run_extractors_parallel,
    save_layered_outputs,
)
from summary.ollama_gemma4_client import OllamaGemma4Client, OllamaGemmaConfig, OllamaGemmaError


VALID_OUTPUTS = {
    "meeting_topic": {"meeting_topic": "Topic"},
    "participants": {"participants": ["Jason"]},
    "executive_summary": {"executive_summary": "A concise summary."},
    "key_points": {"key_points": ["Point"]},
    "decisions": {"decisions": [{"decision": "Use corrected transcript.", "evidence_style": "explicit"}]},
    "action_items": {
        "action_items": [{"task": "Render Markdown.", "owner": "", "deadline": "", "status": "open"}],
    },
    "open_questions": {"open_questions": ["Question?"]},
    "risks": {"risks": ["Risk"]},
    "next_steps": {
        "next_steps": ["Next"],
    },
}


class FakeClient:
    def __init__(self, outputs: dict[str, dict] | list[str] | None = None, delay_sec: float = 0.0):
        self.outputs = outputs if outputs is not None else VALID_OUTPUTS
        self.delay_sec = delay_sec
        self.prompts: list[str] = []
        self.started_at: list[float] = []
        self.lock = threading.Lock()

    def generate_json(self, prompt: str) -> str:
        with self.lock:
            self.prompts.append(prompt)
            self.started_at.append(time.monotonic())
            if isinstance(self.outputs, list):
                output = self.outputs.pop(0) if self.outputs else "{}"
            else:
                output = "{}"
                for extractor, payload in self.outputs.items():
                    if f"Extractor name: {extractor}" in prompt or f"extractor {extractor}" in prompt:
                        output = json.dumps(payload)
                        break
        if self.delay_sec:
            time.sleep(self.delay_sec)
        return output


class LayeredSummaryPipelineTests(unittest.TestCase):
    def test_all_nine_extractors_run_in_one_parallel_batch(self) -> None:
        client = FakeClient(delay_sec=0.08)
        started = time.monotonic()

        run_extractors_parallel(EXTRACTOR_NAMES, "corrected transcript", client)
        elapsed = time.monotonic() - started

        self.assertEqual(len(client.prompts), 9)
        self.assertLess(elapsed, 0.18)

    def test_uses_corrected_transcript_only(self) -> None:
        prompt = build_extractor_prompt("meeting_topic", "CORRECTED_TRANSCRIPT_SENTINEL")

        self.assertIn("CORRECTED_TRANSCRIPT_SENTINEL", prompt)
        self.assertNotIn("RAW_TRANSCRIPT_SENTINEL", prompt)
        self.assertNotIn("CORRECTION_LOG_SENTINEL", prompt)

    def test_raw_transcript_not_sent_to_model(self) -> None:
        client = FakeClient({"meeting_topic": VALID_OUTPUTS["meeting_topic"]})
        extract_with_repair("meeting_topic", "CORRECTED_ONLY_SENTINEL", client)

        self.assertIn("CORRECTED_ONLY_SENTINEL", client.prompts[0])
        self.assertNotIn("RAW_TRANSCRIPT_SENTINEL", client.prompts[0])

    def test_correction_log_not_sent_to_model(self) -> None:
        client = FakeClient({"risks": VALID_OUTPUTS["risks"]})
        extract_with_repair("risks", "CORRECTED_TRANSCRIPT_SENTINEL", client)

        self.assertNotIn("CORRECTION_LOG_JSON_SENTINEL", client.prompts[0])
        self.assertNotIn("PRIVATE_AUDIT_LOG_SENTINEL", client.prompts[0])

    def test_exact_ollama_model_tag_required(self) -> None:
        client = OllamaGemma4Client()

        self.assertEqual(client.config.model, OLLAMA_MODEL_TAG)
        self.assertEqual(client.config.base_model_id, BASE_MODEL_ID)
        self.assertEqual(client.config.num_ctx, OLLAMA_NUM_CTX)
        self.assertEqual(client.config.temperature, 0.0)

    def test_ollama_generation_options_are_fixed(self) -> None:
        client = OllamaGemma4Client()
        requests: list[tuple[str, dict | None]] = []

        def fake_request(endpoint: str, payload: dict | None = None, timeout: int | None = None) -> dict:
            requests.append((endpoint, payload))
            if endpoint == "/api/tags":
                return {"models": [{"name": OLLAMA_MODEL_TAG}]}
            return {"response": "{}"}

        with patch.object(client, "_request", side_effect=fake_request):
            client.generate_json("prompt")

        generate_payload = requests[1][1]
        self.assertIsNotNone(generate_payload)
        self.assertEqual(generate_payload["model"], OLLAMA_MODEL_TAG)
        self.assertFalse(generate_payload["stream"])
        self.assertEqual(generate_payload["options"]["temperature"], 0.0)
        self.assertEqual(generate_payload["options"]["num_ctx"], OLLAMA_NUM_CTX)

    def test_no_fallback_model_allowed(self) -> None:
        with self.assertRaises(OllamaGemmaError):
            OllamaGemma4Client(OllamaGemmaConfig(model="other:model"))

    def test_each_field_prompt_exists(self) -> None:
        for extractor in EXTRACTOR_NAMES:
            self.assertTrue((DEFAULT_LAYER_PROMPT_DIR / f"{extractor}.system.txt").exists())
        self.assertTrue((DEFAULT_LAYER_PROMPT_DIR / "format_repair.system.txt").exists())

    def test_each_field_prompt_has_minimal_example(self) -> None:
        for path in DEFAULT_LAYER_PROMPT_DIR.glob("*.system.txt"):
            self.assertIn("Minimal valid output example", path.read_text(encoding="utf-8"))

    def test_each_field_prompt_is_distinct(self) -> None:
        prompts = {
            path.name: path.read_text(encoding="utf-8")
            for path in DEFAULT_LAYER_PROMPT_DIR.glob("*.system.txt")
            if path.name != "format_repair.system.txt"
        }

        self.assertEqual(len(set(prompts.values())), len(prompts))

    def test_field_output_validation(self) -> None:
        value, result = validate_extractor_value("action_items", VALID_OUTPUTS["action_items"])

        self.assertTrue(result.valid)
        self.assertEqual(value["action_items"][0]["status"], "open")

    def test_all_extractors_cover_final_fields_once(self) -> None:
        covered = [field for fields in EXTRACTOR_FIELDS.values() for field in fields]

        self.assertEqual(covered, list(EXTRACTOR_NAMES))

    def test_meeting_topic_must_be_string(self) -> None:
        _, result = validate_field_value("meeting_topic", {"meeting_topic": ["bad"]})

        self.assertFalse(result.valid)

    def test_participants_must_be_list(self) -> None:
        _, result = validate_field_value("participants", {"participants": "Jason"})

        self.assertFalse(result.valid)

    def test_key_points_must_be_list(self) -> None:
        _, result = validate_field_value("key_points", {"key_points": "point"})

        self.assertFalse(result.valid)

    def test_decisions_must_be_list_of_objects(self) -> None:
        _, result = validate_field_value("decisions", {"decisions": ["decision"]})

        self.assertFalse(result.valid)

    def test_action_items_must_be_list_of_objects(self) -> None:
        _, result = validate_field_value("action_items", {"action_items": ["task"]})

        self.assertFalse(result.valid)

    def test_format_repair_runs_once(self) -> None:
        client = FakeClient(["not json", json.dumps(VALID_OUTPUTS["participants"])])
        value, log, _ = extract_with_repair("participants", "Jason joined.", client)

        self.assertEqual(value["participants"], ["Jason"])
        self.assertTrue(log.repaired)
        self.assertEqual(len(client.prompts), 2)

    def test_failed_repair_uses_default_values(self) -> None:
        client = FakeClient(["not json", "still not json"])
        value, log, _ = extract_with_repair("participants", "Jason joined.", client)

        self.assertEqual(value["participants"], [])
        self.assertFalse(log.valid)
        self.assertEqual(len(client.prompts), 2)

    def test_final_json_schema_valid(self) -> None:
        client = FakeClient()
        result = generate_layered_summary("corrected transcript", client=client)

        self.assertTrue(validate_final_summary(result.summary))
        self.assertTrue(result.summary["metadata"]["parallel_field_generation"])
        self.assertFalse(result.summary["metadata"]["parallel_layered_generation"])
        self.assertEqual(len(client.prompts), 9)
        self.assertEqual(set(result.field_outputs), set(EXTRACTOR_NAMES))

    def test_markdown_rendered_from_json(self) -> None:
        result = generate_layered_summary("corrected transcript", client=FakeClient())

        self.assertIn("# Meeting Summary", result.markdown)
        self.assertIn("## Decisions", result.markdown)
        self.assertIn("Use corrected transcript.", result.markdown)

    def test_ollama_unavailable_fails_gracefully(self) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(OllamaGemmaError, "Ollama local runner unavailable"):
                OllamaGemma4Client().check_model_available()

    def test_missing_model_tag_fails_gracefully(self) -> None:
        client = OllamaGemma4Client()
        with patch.object(client, "_request", return_value={"models": [{"name": "other:model"}]}):
            with self.assertRaisesRegex(OllamaGemmaError, f"Gemma 4 E4B local Ollama model tag not found: {OLLAMA_MODEL_TAG}"):
                client.check_model_available()

    def test_external_cloud_calls_forbidden(self) -> None:
        client = OllamaGemma4Client()

        self.assertEqual(client.config.host, "http://localhost:11434")
        with self.assertRaises(OllamaGemmaError):
            OllamaGemma4Client(OllamaGemmaConfig(host="https://api.example.com"))

    def test_private_outputs_not_staged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = generate_layered_summary("corrected transcript", client=FakeClient())
            paths = save_layered_outputs(result, Path(temp_dir) / "local_outputs" / "meeting_summary")

        self.assertIn("local_outputs/meeting_summary", str(paths["final_summary"]))


if __name__ == "__main__":
    unittest.main()
