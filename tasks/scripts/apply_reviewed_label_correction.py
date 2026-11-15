#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Apply an existing reviewed removal preview, preserving its preparation audit."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import label_issue
from label_issue_github import GitHubClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--remove", required=True)
    parser.add_argument("--actor", default="purp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    directory = args.directory

    def read(name):
        return json.loads((directory / name).read_text())

    def write(name, value):
        (directory / name).write_text(json.dumps(value, indent=2) + "\n")

    record, preview = read("execution.json"), read("preview.json")
    if (
        record["review"] != "Human agreed"
        or record["status"] != "preview"
        or preview["status"] != "preview"
        or preview["add"]
        or preview["remove"] != [args.remove]
        or preview.get("missing_prerequisites")
        or preview.get("bookkeeping", []) not in (
            [], ["add meta:labeler-checkpoint", "remove meta:labeler-checkpoint"]
        )
        or set(preview["final_labels"]) != set(record["before_labels"]) - {args.remove}
        or (directory / "apply-started.json").exists()
    ):
        raise ValueError("Expected an unattempted, reviewed, single-label removal")
    if not args.apply:
        print(json.dumps({"number": record["number"], "remove": preview["remove"]}))
        return
    write("preview-execution.json", record)
    write("apply-started.json", {"started_utc": datetime.now(UTC).isoformat()})
    api = GitHubClient()
    applied = label_issue.apply(
        read("evidence/manifest.json"),
        read("reviewed-result.json"),
        api=api,
        trusted_actors={args.actor},
        executor=args.actor,
        expected_preview=preview,
    )
    write("applied.json", applied)
    after = sorted(
        x["name"]
        for x in api(
            f"repos/{record['repository']}/issues/{record['number']}/labels?per_page=100",
            pages=True,
        )
    )
    record.update(
        status=applied["status"],
        applied=applied["status"] == "applied",
        checkpoint_verified=applied.get("checkpoint_verified", False),
        after_labels=after,
        diagnostics=applied.get("diagnostics", []),
        finished_utc=datetime.now(UTC).isoformat(),
    )
    if applied["status"] == "applied" and after != sorted(preview["final_labels"]):
        record["status"] = "partial"
        record["diagnostics"].append("Final labels differ; inspect without replay")
    write("execution.json", record)
    print(json.dumps({k: record[k] for k in ("number", "status", "diagnostics")}))
    if record["status"] != "applied":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
