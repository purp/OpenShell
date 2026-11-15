#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reconcile one authorized migration item using the shared helper and audit its result."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import compare_label_models
import label_issue
from label_issue_github import GitHubClient
from label_issue_policy import IDENTITY, validate_result


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def migrate(args):
    config = json.loads(args.config.read_text())
    decision = next(x for x in config["cases"] if x["number"] == args.number)
    directory = args.output.resolve() / str(args.number)
    if directory.exists():
        raise ValueError(
            "Item already attempted; inspect its audit before any explicit recovery"
        )
    directory.mkdir(parents=True)
    call = SimpleNamespace(
        output=args.output.resolve(),
        number=args.number,
        model="sonnet",
        actor=args.actor,
        respect_checkpoints=not args.reviewed,
    )
    compare_label_models.prepare(call, config)
    bundle = json.loads((directory / "input.json").read_text())
    preparation = bundle["preparation"]
    packet = bundle.get("packet")
    repo = config["repository"]

    def live_labels():
        return sorted(
            x["name"]
            for x in GitHubClient()(
                f"repos/{repo}/issues/{args.number}/labels?per_page=100", pages=True
            )
        )

    before = packet["existing_labels"] if packet else live_labels()
    record = {
        "number": args.number,
        "repository": repo,
        "started_utc": datetime.now(UTC).isoformat(),
        "before_labels": before,
        "preparation_status": preparation["status"],
        "review": "Human agreed"
        if args.reviewed
        else "Sonnet; reviewer-relevance rubric",
        "applied": False,
    }

    def finish(report):
        record.update(
            status=report["status"],
            diagnostics=report.get("diagnostics", []),
            finished_utc=datetime.now(UTC).isoformat(),
        )
        record["after_labels"] = live_labels()
        if record["status"] in ("applied", "no-op") and set(
            record["after_labels"]
        ) != set(report["final_labels"]):
            record["status"] = "partial"
            record["diagnostics"].append(
                "Post-application labels changed; inspect concurrent edits, no automatic replay"
            )
        write(directory / "execution.json", record)
        print(
            json.dumps(
                {
                    "number": args.number,
                    "status": record["status"],
                    "add": record.get("add", []),
                    "remove": record.get("remove", []),
                    "diagnostics": record["diagnostics"],
                }
            ),
            flush=True,
        )

    if preparation["status"] != "ready":
        finish(preparation)
        return
    snapshot = json.loads((directory / "evidence/manifest.json").read_text())
    if args.reviewed:
        body = packet["evidence_index"]["body"]["content"]
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if digest != decision["reviewed_body_sha256"]:
            finish(
                {
                    "status": "held",
                    "diagnostics": [
                        "Body changed since human review; inspect before applying the agreed classification"
                    ],
                }
            )
            return
        result = {key: snapshot[key] for key in IDENTITY}
        result.update(
            area=decision["area"],
            topics=decision["topics"],
            reasons=[
                {
                    "labels": [decision["area"], *decision["topics"]],
                    "evidence": ["body"],
                    "reason": decision["reason"],
                }
            ],
            ambiguity=None,
            removals=[],
        )
        write(directory / "reviewed-result.json", result)
        validation = validate_result(snapshot, result)
        write(directory / "validation.json", validation)
        if not validation["valid"] or validation["missing_prerequisites"]:
            finish(
                {
                    "status": "held",
                    "diagnostics": validation["errors"]
                    + validation["missing_prerequisites"],
                }
            )
            return
        preview = label_issue.preview(
            snapshot, result, api=GitHubClient(), executor=args.actor
        )
    else:
        compare_label_models.run(call, config)
        target = directory / "sonnet"
        record["model_metrics"] = json.loads((target / "metrics.json").read_text())
        outcome = json.loads((target / "outcome.json").read_text())
        if outcome["status"] != "preview":
            finish(outcome)
            return
        answer = json.loads((target / "answer.json").read_text())
        record["confidence"] = answer["confidence"]
        result = answer["classification"]
        preview = json.loads((target / "preview.json").read_text())
    write(directory / "preview.json", preview)
    record.update(
        proposed_final_labels=preview["final_labels"],
        add=preview["add"],
        remove=preview["remove"],
        rationale=result["reasons"],
        ambiguity=result["ambiguity"],
        bookkeeping=preview.get("bookkeeping", []),
    )
    if preview["status"] != "preview" or not args.apply:
        finish(preview)
        return
    # Do not bypass helper eligibility, freshness, prefix verification, locks,
    # expected-payload matching, checkpoint verification, or partial-write handling.
    write(
        directory / "apply-started.json", {"started_utc": datetime.now(UTC).isoformat()}
    )
    applied = label_issue.apply(
        snapshot,
        result,
        api=GitHubClient(),
        trusted_actors={args.actor},
        executor=args.actor,
        expected_preview=preview,
    )
    write(directory / "applied.json", applied)
    record.update(
        applied=applied["status"] == "applied",
        checkpoint_verified=applied.get("checkpoint_verified", False),
    )
    finish(applied)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--number", type=int, required=True)
    parser.add_argument("--actor", default="purp")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly authorize the previewed label changes",
    )
    args = parser.parse_args()
    migrate(args)


if __name__ == "__main__":
    main()
