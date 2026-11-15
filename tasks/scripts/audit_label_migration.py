#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify local migration histories and compare an optional fresh open inventory."""

import argparse
import json
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def audit(execution_dirs, followup_dirs, active, items_file=None):
    records = {}
    histories = {}
    for directory in execution_dirs:
        for path in directory.glob("*/execution.json"):
            record = read(path)
            number = record["number"]
            if number in records:
                raise ValueError(f"Duplicate primary history for #{number}")
            records[number] = record
            histories[number] = [path]
    for directory in followup_dirs:
        for path in directory.glob("*/execution.json"):
            record = read(path)
            number = record["number"]
            previous = records[number]
            if record["status"] != "applied" or not record["checkpoint_verified"]:
                raise ValueError(f"Unverified follow-up: {path}")
            if set(record["before_labels"]) != set(previous["after_labels"]):
                raise ValueError(f"Broken label-state history: {path}")
            records[number] = record
            histories[number].append(path)

    errors = []
    for number, paths in histories.items():
        for path in paths:
            record = read(path)
            if record["status"] not in {"applied", "partial"}:
                continue
            packet = read(path.parent / "evidence/packet.json")
            manifest = read(path.parent / "evidence/manifest.json")
            if not packet["eligibility"]["accepted"]:
                errors.append(f"#{number}: application without accepted-work eligibility")
            if manifest["item_material"]["state"] != "open":
                errors.append(f"#{number}: application outside open-item scope")
        current = records[number]
        if current["status"] == "partial":
            errors.append(f"#{number}: unresolved partial application")
        if current["status"] != "applied":
            continue
        after = set(current["after_labels"])
        classification = {s for s in after if s.startswith(("area:", "topic:"))}
        if not current["checkpoint_verified"]:
            errors.append(f"#{number}: completion without verified checkpoint")
        if len([s for s in after if s.startswith("area:")]) != 1:
            errors.append(f"#{number}: expected exactly one area")
        if classification - active or any(
            s.startswith(("retired:area:", "retired:topic:")) for s in after
        ):
            errors.append(f"#{number}: obsolete or unknown classification remains")
        if after != set(current["proposed_final_labels"]):
            errors.append(f"#{number}: verified state differs from desired state")

    summary = {
        "recorded_items": len(records),
        "current_outcomes": dict(Counter(r["status"] for r in records.values())),
        "followups": sum(len(paths) - 1 for paths in histories.values()),
        "unresolved": {
            str(n): r["status"]
            for n, r in sorted(records.items())
            if r["status"] not in {"applied", "unchanged", "skipped"}
        },
        "errors": errors,
    }
    if items_file:
        items = [item for page in read(items_file) for item in page]
        if len({i["number"] for i in items}) != len(items):
            raise ValueError("Duplicate inventory numbers")
        if any(i["state"] != "open" for i in items):
            raise ValueError("Expected a fresh open-item inventory")
        live = {i["number"]: i for i in items}
        mismatches = {}
        retired = {}
        for number, item in live.items():
            labels = {label["name"] for label in item["labels"]}
            record = records.get(number)
            if record and labels != set(record["after_labels"]):
                mismatches[str(number)] = {
                    "outcome": record["status"],
                    "recorded": record["after_labels"],
                    "live": sorted(labels),
                }
            old = sorted(
                s for s in labels if s.startswith(("retired:area:", "retired:topic:"))
            )
            if old:
                retired[str(number)] = {
                    "outcome": record["status"] if record else "unrecorded",
                    "labels": old,
                }
        summary.update(
            open_items=len(live),
            unrecorded_open=sorted(set(live) - records.keys()),
            no_longer_open=sorted(records.keys() - set(live)),
            label_state_differences=mismatches,
            remaining_retired=retired,
        )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-dir", action="append", type=Path, required=True)
    parser.add_argument("--followup-dir", action="append", type=Path, default=[])
    parser.add_argument("--items-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    catalog = read(Path(__file__).resolve().parents[1] / "labels/taxonomy.json")
    result = audit(
        args.execution_dir,
        args.followup_dir,
        {label["name"] for label in catalog["active"]},
        args.items_file,
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
