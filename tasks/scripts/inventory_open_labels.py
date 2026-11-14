#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Export every open item without classifying it or writing to GitHub."""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--items-file",
    required=True,
    type=Path,
    help="Paginated REST issues response, including PRs (gh api --paginate --slurp)",
)
parser.add_argument(
    "--prs-file",
    required=True,
    type=Path,
    help="Paginated REST pulls response, including draft metadata",
)
parser.add_argument("--output-dir", required=True, type=Path)
parser.add_argument(
    "--snapshot-utc", help="Original capture time for replay; otherwise current UTC"
)
args = parser.parse_args()
args.output_dir.mkdir(parents=True, exist_ok=True)
items = [x for page in json.loads(args.items_file.read_text()) for x in page]
pr_items = [x for page in json.loads(args.prs_file.read_text()) for x in page]
prs = {x["number"]: x for x in pr_items}
if len(prs) != len(pr_items):
    raise ValueError("Duplicate PR numbers; capture the pages again")
if any(x["state"] != "open" for x in items + pr_items):
    raise ValueError("Inventory inputs must contain only open items")
assert len({x["number"] for x in items}) == len(items)
assert {x["number"] for x in items if "pull_request" in x} == set(prs)
snapshot = args.snapshot_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
headers = [
    "Number",
    "Kind",
    "Title",
    "URL",
    "Author",
    "Draft",
    "State",
    "Current labels (complete)",
    "Active area labels",
    "Active topic labels",
    "Retired classification labels",
    "Other labels",
    "Classification inventory flags",
    "state:accepted present (not eligibility)",
    "Created UTC",
    "Updated UTC",
    "Snapshot UTC",
    "Eligibility (helper)",
    "Proposed final labels (complete)",
    "Add",
    "Remove",
    "Rationale / ambiguity",
    "Review status",
    "Application outcome",
]
rows = [headers]
for item in sorted(items, key=lambda x: x["number"]):
    is_pr = "pull_request" in item
    labels = sorted(x["name"] for x in item["labels"])
    areas = [x for x in labels if x.startswith("area:")]
    topics = [x for x in labels if x.startswith("topic:")]
    retired = [x for x in labels if x.startswith(("retired:area:", "retired:topic:"))]
    other = [x for x in labels if x not in areas + topics + retired]
    flags = []
    if not areas and not topics:
        flags.append("No active area/topic labels")
    if not areas:
        flags.append("No active area")
    elif len(areas) > 1:
        flags.append("Multiple active areas")
    if retired:
        flags.append("Retired labels present")
    if not areas and not topics and not retired:
        flags.append("No classification labels at all")
    draft = ("Yes" if prs[item["number"]]["draft"] else "No") if is_pr else "N/A"
    rows.append(
        [
            item["number"],
            "PR" if is_pr else "Issue",
            item["title"],
            item["html_url"],
            (item.get("user") or {}).get("login", "[deleted]"),
            draft,
            item["state"],
            "\n".join(labels),
            "\n".join(areas),
            "\n".join(topics),
            "\n".join(retired),
            "\n".join(other),
            "; ".join(flags) or "One active area; no retired labels",
            "Yes" if "state:accepted" in labels else "No",
            item["created_at"],
            item["updated_at"],
            snapshot,
            "Not evaluated",
            "",
            "",
            "",
            "",
            "Pending",
            "Not run",
        ]
    )
assert all(len(row) == len(headers) for row in rows)
(args.output_dir / "rows.json").write_text(json.dumps(rows))
with (args.output_dir / "inventory.csv").open("w", newline="") as f:
    csv.writer(f).writerows(rows)
summary = {
    "snapshot_utc": snapshot,
    "items": len(items),
    "issues": len(items) - len(prs),
    "prs": len(prs),
    "retired_items": sum(bool(row[10]) for row in rows[1:]),
    "no_active_classification": sum(not row[8] and not row[9] for row in rows[1:]),
    "no_classification_at_all": sum(
        not row[8] and not row[9] and not row[10] for row in rows[1:]
    ),
    "columns": len(headers),
}
(args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
