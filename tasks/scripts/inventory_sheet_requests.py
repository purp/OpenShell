#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build Google Sheets requests for a new inventory tab; perform no writes."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--rows-file", required=True, type=Path)
parser.add_argument(
    "--sheet-id", required=True, type=int, help="Unused tab ID, not the spreadsheet ID"
)
parser.add_argument("--title", required=True)
args = parser.parse_args()
rows = json.loads(args.rows_file.read_text())
if not rows or len(rows[0]) != 24 or any(len(row) != 24 for row in rows):
    raise ValueError("Expected the 24-column open inventory")
sheet_id = args.sheet_id
requests = [
    {
        "addSheet": {
            "properties": {
                "sheetId": sheet_id,
                "title": args.title,
                "gridProperties": {
                    "rowCount": len(rows) + 20,
                    "columnCount": 24,
                    "frozenRowCount": 1,
                    "frozenColumnCount": 2,
                },
            }
        }
    },
    {
        "updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
            "rows": [
                {
                    "values": [
                        {
                            "userEnteredValue": {"numberValue": value}
                            if isinstance(value, (int, float))
                            else {"stringValue": value}
                        }
                        for value in row
                    ]
                }
                for row in rows
            ],
            "fields": "userEnteredValue",
        }
    },
    {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": len(rows),
            },
            "cell": {
                "userEnteredFormat": {
                    "verticalAlignment": "TOP",
                    "wrapStrategy": "CLIP",
                    "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                }
            },
            "fields": "userEnteredFormat",
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
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1,
            },
            "properties": {"pixelSize": 58},
            "fields": "pixelSize",
        }
    },
    {
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": len(rows),
                    "startColumnIndex": 0,
                    "endColumnIndex": 24,
                }
            }
        }
    },
    {
        "addConditionalFormatRule": {
            "index": 0,
            "rule": {
                "ranges": [
                    {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": len(rows),
                        "startColumnIndex": 10,
                        "endColumnIndex": 11,
                    }
                ],
                "booleanRule": {
                    "condition": {"type": "NOT_BLANK"},
                    "format": {
                        "backgroundColor": {"red": 1, "green": 0.91, "blue": 0.78}
                    },
                },
            },
        }
    },
]
for start, end, width in [
    (0, 24, 150),
    (0, 2, 78),
    (2, 4, 380),
    (7, 13, 260),
    (18, 22, 280),
]:
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start,
                    "endIndex": end,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        }
    )
notes = {
    0: f"Open-item snapshot: {len(rows) - 1} items. API pagination is not atomic; re-read lifecycle, content, and labels before preview/application. Inventory only: no classifications or GitHub item changes. Capture time is in column Q.",
    13: "Observed presence of state:accepted only, not helper eligibility. Maintainer PRs and linked accepted work may qualify through other paths. Do not grant acceptance as a migration side effect.",
    18: "Intentionally blank until fresh content-derived classification and helper preview. Column H preserves the complete observed label state. No historical proposals are copied into the snapshot.",
}
for column, note in notes.items():
    requests.append(
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": column},
                "rows": [{"values": [{"note": note}]}],
                "fields": "note",
            }
        }
    )
print(json.dumps({"requests": requests}))
