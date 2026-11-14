# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise retry boundaries without model calls or GitHub writes."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from label_model_attempts import run_attempts
from label_model_response import response_schema, validate_answer


def fixtures():
    snapshot = {
        "schema_version": 1,
        "repository": "NVIDIA/OpenShell",
        "number": 1,
        "kind": "issue",
        "snapshot_id": "frozen",
        "taxonomy": {
            "areas": {"area:runtime": "Runtime"},
            "topics": {"topic:networking": "Network"},
            "definitions": {"area:runtime": {}, "topic:networking": {}},
        },
        "evidence_index": {
            "body": {
                "kind": "body",
                "inspected": True,
                "content": "DNS resolver defect",
            }
        },
        "existing_labels": [],
    }
    packet = {
        key: value
        for key, value in snapshot.items()
        if key in ("schema_version", "repository", "number", "kind", "snapshot_id")
    }
    packet["scopes"] = {key: snapshot["taxonomy"][key] for key in ("areas", "topics")}
    bundle = {"preparation": {"status": "ready"}, "packet": packet}
    classification = {
        key: packet[key]
        for key in ("schema_version", "repository", "number", "kind", "snapshot_id")
    }
    classification.update(
        area="area:runtime",
        topics=["topic:networking"],
        reasons=[
            {
                "labels": ["area:runtime", "topic:networking"],
                "evidence": ["body"],
                "reason": "Supervisor DNS resolution.",
            }
        ],
        ambiguity=None,
        removals=[],
    )
    answer = {
        "outcome": "classified",
        "classification": classification,
        "confidence": "high",
        "label_confidence": [
            {
                "label": "area:runtime",
                "confidence": "high",
                "reason": "Runtime resolver",
            }
        ],
        "summary": "Runtime networking.",
        "missing_context": [],
    }
    return bundle, snapshot, answer


def cli(answer=None, *, raw=None, code=0, is_error=False):
    envelope = {
        "result": raw or "",
        "duration_ms": 100,
        "duration_api_ms": 80,
        "is_error": is_error,
        "total_cost_usd": 0.01,
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 30,
            "output_tokens": 40,
            "output_tokens_details": {"thinking_tokens": 5},
        },
        "modelUsage": {
            "model": {
                "inputTokens": 10,
                "outputTokens": 40,
                "costUSD": 0.01,
                "contextWindow": 1000,
            }
        },
    }
    if answer is not None:
        envelope["structured_output"] = answer
    return subprocess.CompletedProcess(["claude"], code, json.dumps(envelope), "")


class AttemptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name)
        self.bundle, self.snapshot, self.answer = fixtures()
        self.preview = Mock(
            return_value={
                "status": "preview",
                "add": ["area:runtime"],
                "diagnostics": [],
            }
        )

    def execute(self, responses):
        self.invoke = Mock(side_effect=responses)
        result = run_attempts(
            self.target,
            ["claude", "--tools", ""],
            "FROZEN INPUT",
            self.bundle,
            self.snapshot,
            invoke=self.invoke,
            preview=self.preview,
            actor="purp",
        )
        self.metrics = json.loads((self.target / "metrics.json").read_text())
        return result

    def test_structured_response_previews_once(self):
        result = self.execute([cli(self.answer)])
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.invoke.call_count, 1)
        self.preview.assert_called_once()
        command = self.invoke.call_args.args[0]
        self.assertEqual(
            json.loads(command[command.index("--json-schema") + 1]),
            response_schema(self.bundle),
        )

    def test_malformed_then_valid_retains_attempts_and_sums_usage(self):
        result = self.execute([cli(raw='{"broken":'), cli(self.answer)])
        self.assertTrue(result["recovered_after_retry"])
        self.assertEqual(self.invoke.call_count, 2)
        self.preview.assert_called_once()
        self.assertIn("validation_errors", self.invoke.call_args.kwargs["input"])
        self.assertTrue(
            self.invoke.call_args.kwargs["input"].startswith("FROZEN INPUT")
        )
        self.assertEqual(
            json.loads((self.target / "attempt-1/cli.json").read_text())["result"],
            '{"broken":',
        )
        self.assertTrue((self.target / "attempt-2/answer.json").exists())
        self.assertEqual(self.metrics["usage"]["output_tokens"], 80)
        self.assertEqual(self.metrics["usage"]["cache_creation_input_tokens"], 40)
        self.assertEqual(
            self.metrics["usage"]["output_tokens_details"]["thinking_tokens"], 10
        )
        self.assertEqual(self.metrics["reported_cost_usd"], 0.02)
        self.assertEqual(self.metrics["model_usage"]["model"]["contextWindow"], 1000)
        attempts = [
            json.loads((self.target / f"attempt-{n}/metrics.json").read_text())
            for n in (1, 2)
        ]
        self.assertEqual(
            self.metrics["wall_seconds"], sum(x["wall_seconds"] for x in attempts)
        )

    def test_schema_failure_is_retried_without_silent_repair(self):
        invalid = copy.deepcopy(self.answer)
        invalid["classification"]["reasons"][0]["label_reasons"] = None
        self.execute([cli(invalid), cli(self.answer)])
        first = json.loads((self.target / "attempt-1/answer.json").read_text())
        self.assertIn("label_reasons", first["classification"]["reasons"][0])
        self.assertIn(
            "unexpected field label_reasons", self.invoke.call_args.kwargs["input"]
        )

    def test_helper_validation_failure_gets_one_retry(self):
        invalid = copy.deepcopy(self.answer)
        invalid["classification"]["reasons"][0]["evidence"] = ["uninspected"]
        result = self.execute([cli(invalid), cli(self.answer)])
        self.assertEqual(result["status"], "preview")
        self.assertIn(
            "inspected substantive evidence", self.invoke.call_args.kwargs["input"]
        )

    def test_two_failures_hold_without_preview_or_third_call(self):
        result = self.execute(
            [cli(raw="broken"), cli(raw="still broken"), cli(self.answer)]
        )
        self.assertEqual(result["status"], "held")
        self.assertEqual(self.invoke.call_count, 2)
        self.preview.assert_not_called()
        self.assertFalse((self.target / "answer.json").exists())

    def test_api_error_is_not_retried(self):
        result = self.execute([cli(raw="Not logged in", code=1, is_error=True)])
        self.assertEqual(result["status"], "held")
        self.assertEqual(self.invoke.call_count, 1)
        self.preview.assert_not_called()

    def test_cli_structured_output_exhaustion_gets_one_retry(self):
        failed = cli(raw="Could not satisfy schema", code=1, is_error=True)
        envelope = json.loads(failed.stdout)
        envelope["subtype"] = "error_max_structured_output_retries"
        failed.stdout = json.dumps(envelope)
        result = self.execute([failed, cli(self.answer)])
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.invoke.call_count, 2)
        self.assertIn(
            "schema-conforming structured output", self.invoke.call_args.kwargs["input"]
        )

    def test_timeout_is_recorded_without_retry(self):
        result = self.execute(
            [subprocess.TimeoutExpired(["claude"], 300, output=b"partial")]
        )
        self.assertEqual(result["status"], "held")
        self.assertEqual((self.target / "attempt-1/stdout.txt").read_text(), "partial")
        self.assertFalse(self.metrics["usage_complete"])
        self.preview.assert_not_called()

    def test_prerequisite_is_not_retried_or_previewed(self):
        self.snapshot["taxonomy"]["definitions"] = {}
        result = self.execute([cli(self.answer)])
        self.assertEqual(result["status"], "prerequisite")
        self.assertEqual(self.invoke.call_count, 1)
        self.preview.assert_not_called()

    def test_stale_live_preview_is_not_retried(self):
        self.preview.return_value = {
            "status": "stale",
            "diagnostics": ["Evidence changed"],
        }
        result = self.execute([cli(self.answer)])
        self.assertEqual(result["status"], "stale")
        self.assertEqual(self.invoke.call_count, 1)

    def test_gate_cannot_be_overridden(self):
        self.bundle = {"preparation": {"status": "skipped"}, "packet": None}
        skipped = {
            **self.answer,
            "outcome": "skipped",
            "classification": None,
            "confidence": "not_applicable",
            "label_confidence": [],
        }
        result = self.execute([cli(self.answer), cli(skipped)])
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(self.invoke.call_count, 2)
        self.preview.assert_not_called()

    def test_syntax_only_fix_still_rejects_extra_reason_field(self):
        self.answer["classification"]["reasons"][0]["label_reasons"] = None
        validation = validate_answer(self.answer, self.bundle, self.snapshot)
        self.assertFalse(validation["valid"])
        self.assertTrue(any("label_reasons" in x for x in validation["errors"]))


if __name__ == "__main__":
    unittest.main()
