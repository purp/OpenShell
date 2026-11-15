# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify migration authorization, fresh preview binding, and no blind replay."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import migrate_open_labels as migration
from label_model_attempts_test import fixtures


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle, self.snapshot, _ = fixtures()
        body = {"title": "DNS defect", "body": "Supervisor DNS resolution fails."}
        self.snapshot["existing_labels"] = ["state:accepted"]
        self.bundle["packet"].update(
            existing_labels=["state:accepted"],
            evidence_index={"body": {"content": body}},
        )
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        config = {
            "repository": "NVIDIA/OpenShell",
            "cases": [
                {
                    "number": 1,
                    "area": "area:runtime",
                    "topics": ["topic:networking"],
                    "reason": "DNS resolver needs networking reviewers.",
                    "reviewed_body_sha256": digest,
                }
            ],
        }
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(config))
        self.args = SimpleNamespace(
            config=self.config,
            output=self.root / "run",
            number=1,
            actor="purp",
            reviewed=True,
            apply=False,
        )
        self.final = ["area:runtime", "state:accepted", "topic:networking"]
        self.preview = {
            "status": "preview",
            "final_labels": self.final,
            "add": ["area:runtime", "topic:networking"],
            "remove": [],
            "mutation_requests": [{"exact": "payload"}],
        }

    def prepare(self, args, _config):
        directory = args.output / "1"
        migration.write(directory / "input.json", self.bundle)
        migration.write(directory / "evidence/manifest.json", self.snapshot)

    def execute(self, *, after=None, preview=None, applied=None):
        after = ["state:accepted"] if after is None else after
        with (
            patch.object(
                migration.compare_label_models, "prepare", side_effect=self.prepare
            ),
            patch.object(
                migration.label_issue, "preview", return_value=preview or self.preview
            ) as p,
            patch.object(migration.label_issue, "apply", return_value=applied) as a,
            patch.object(
                migration,
                "GitHubClient",
                return_value=lambda *_args, **_kwargs: [{"name": x} for x in after],
            ),
        ):
            migration.migrate(self.args)
        return p, a, json.loads((self.args.output / "1/execution.json").read_text())

    def test_default_is_preview_only(self):
        p, a, record = self.execute()
        p.assert_called_once()
        a.assert_not_called()
        self.assertEqual(record["status"], "preview")
        self.assertEqual(record["before_labels"], ["state:accepted"])

    def test_apply_binds_exact_fresh_preview_and_verifies_final_labels(self):
        self.args.apply = True
        p, a, record = self.execute(
            after=self.final,
            applied={**self.preview, "status": "applied", "checkpoint_verified": True},
        )
        self.assertEqual(a.call_args.kwargs["expected_preview"], p.return_value)
        self.assertEqual(a.call_args.kwargs["trusted_actors"], {"purp"})
        self.assertEqual(record["status"], "applied")
        self.assertTrue(record["checkpoint_verified"])

    def test_stale_preview_never_applies(self):
        self.args.apply = True
        _, a, record = self.execute(
            preview={
                **self.preview,
                "status": "stale",
                "diagnostics": ["Changed evidence"],
            }
        )
        a.assert_not_called()
        self.assertEqual(record["status"], "stale")

    def test_changed_reviewed_body_holds(self):
        self.args.apply = True
        self.bundle["packet"]["evidence_index"]["body"]["content"]["body"] = (
            "Changed request"
        )
        p, a, record = self.execute()
        p.assert_not_called()
        a.assert_not_called()
        self.assertEqual(record["status"], "held")

    def test_partial_write_is_recorded_and_not_replayed(self):
        self.args.apply = True
        _, a, record = self.execute(
            after=["state:accepted", "area:runtime"],
            applied={
                **self.preview,
                "status": "partial",
                "checkpoint_verified": False,
                "diagnostics": ["Uncertain write"],
            },
        )
        a.assert_called_once()
        self.assertEqual(record["status"], "partial")
        with self.assertRaises(ValueError):
            migration.migrate(self.args)

    def test_unaccepted_preparation_skips_without_preview_or_apply(self):
        self.args.apply = True
        self.bundle = {
            "preparation": {
                "status": "skipped",
                "diagnostics": ["Accepted work required"],
            },
            "packet": None,
        }
        p, a, record = self.execute()
        p.assert_not_called()
        a.assert_not_called()
        self.assertEqual(record["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
