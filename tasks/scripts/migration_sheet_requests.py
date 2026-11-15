#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build inventory/result audit updates from migration records; no remote calls."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inventory-rows", type=Path, required=True)
parser.add_argument("--execution-dir", type=Path, action="append", required=True)
parser.add_argument("--correction-dir", type=Path, action="append", default=[])
parser.add_argument("--audit-exists", action="store_true")
args = parser.parse_args()
rows = json.loads(args.inventory_rows.read_text())
row_numbers = {int(row[0]): i for i, row in enumerate(rows[1:], 1)}
records = sorted(
    [
        json.loads(path.read_text())
        for directory in args.execution_dir
        for path in directory.glob("*/execution.json")
    ],
    key=lambda r: r["number"],
)
if len({r["number"] for r in records}) != len(records):
    raise ValueError("Duplicate audit items require explicit recovery-history handling")
by_number = {r["number"]: r for r in records}
for directory in args.correction_dir:
    for path in sorted(directory.glob("*/execution.json")):
        correction = json.loads(path.read_text())
        original = by_number[correction["number"]]
        if correction["status"] != "applied" or set(
            correction["before_labels"]
        ) != set(original["after_labels"]):
            raise ValueError(f"Unverified correction history: {path}")
        after = correction["after_labels"]
        before = original["before_labels"]
        by_number[correction["number"]] = {
            **original,
            "review": original["review"] + "; human-reviewed correction",
            "after_labels": after,
            "proposed_final_labels": correction["proposed_final_labels"],
            "add": sorted(set(after) - set(before)),
            "remove": sorted(set(before) - set(after)),
            "rationale": original.get("rationale", []) + correction["rationale"],
            "checkpoint_verified": correction["checkpoint_verified"],
            "finished_utc": correction["finished_utc"],
            "diagnostics": original.get("diagnostics", [])
            + [f"Earlier rationale superseded where corrected; correction audit: {path}"],
        }
records = sorted(by_number.values(), key=lambda r: r["number"])
sheet_id = 51511501
requests = []
if not args.audit_exists:
    requests.append(
        {
            "addSheet": {
                "properties": {
                    "sheetId": sheet_id,
                    "title": "Migration execution",
                    "gridProperties": {
                        "rowCount": max(1000, len(records) + 21),
                        "columnCount": 19,
                        "frozenRowCount": 1,
                        "frozenColumnCount": 2,
                    },
                }
            }
        }
    )
audit = [
    [
        "Number",
        "URL",
        "Review source",
        "Preparation",
        "Outcome",
        "Fresh before labels",
        "Desired final labels",
        "Verified after labels",
        "Add",
        "Remove",
        "Rationale",
        "Ambiguity",
        "Checkpoint verified",
        "Started UTC",
        "Finished UTC",
        "Model wall seconds",
        "Model token usage",
        "Model attempts",
        "Diagnostics",
    ]
]


def cell(value):
    return {
        "userEnteredValue": {"numberValue": value}
        if isinstance(value, (int, float))
        else {"stringValue": str(value)}
    }


for record in records:
    reason = "\n".join(x["reason"] for x in record.get("rationale", []))
    metrics = record.get("model_metrics") or {}
    diagnostic = "; ".join(record.get("diagnostics", []))
    before, after = (
        "\n".join(record["before_labels"]),
        "\n".join(record["after_labels"]),
    )
    desired = "\n".join(record.get("proposed_final_labels", []))
    additions, removals = (
        "\n".join(record.get("add", [])),
        "\n".join(record.get("remove", [])),
    )
    ambiguity = (
        json.dumps(record["ambiguity"], ensure_ascii=False)
        if record.get("ambiguity")
        else ""
    )
    audit.append(
        [
            record["number"],
            f"https://github.com/NVIDIA/OpenShell/issues/{record['number']}",
            record["review"],
            record["preparation_status"],
            record["status"],
            before,
            desired,
            after,
            additions,
            removals,
            reason,
            ambiguity,
            str(record.get("checkpoint_verified", "")),
            record["started_utc"],
            record["finished_utc"],
            metrics.get("wall_seconds", ""),
            json.dumps(metrics.get("usage", {}), ensure_ascii=False),
            metrics.get("attempt_count", ""),
            diagnostic,
        ]
    )
    if record["number"] in row_numbers:
        values = [
            record["preparation_status"],
            desired,
            additions,
            removals,
            reason + ("\nAmbiguity: " + ambiguity if ambiguity else ""),
            record["review"],
            record["status"] + (" — " + diagnostic if diagnostic else ""),
        ]
        requests.append(
            {
                "updateCells": {
                    "start": {
                        "sheetId": 51511114,
                        "rowIndex": row_numbers[record["number"]],
                        "columnIndex": 17,
                    },
                    "rows": [{"values": [cell(v) for v in values]}],
                    "fields": "userEnteredValue",
                }
            }
        )
requests += [
    {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
            "rows": [{"values": [cell(v) for v in row]} for row in audit],
            "fields": "userEnteredValue",
        }
    },
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.18, "green": 0.33, "blue": 0.5},
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    },
                    "wrapStrategy": "WRAP",
                }
            },
            "fields": "userEnteredFormat",
        }
    },
    {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 19,
            },
            "properties": {"pixelSize": 190},
            "fields": "pixelSize",
        }
    },
    {
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": len(audit),
                    "startColumnIndex": 0,
                    "endColumnIndex": 19,
                }
            }
        }
    },
]
print(json.dumps({"requests": requests}))
