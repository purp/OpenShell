#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Coordinate migration items, retaining results and stopping on uncertain writes/rate limits."""

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Return at an audit boundary; completed items are skipped on continuation",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("batch size must be positive")
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("max batches must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text())
    pending = []
    for case in config["cases"]:
        directory = args.output / str(case["number"])
        if (directory / "execution.json").exists():
            continue
        if directory.exists():
            raise ValueError(
                f"Incomplete existing item {case['number']}; inspect it, do not replay"
            )
        pending.append(case["number"])

    def item(number):
        command = [
            sys.executable,
            str(ROOT / "tasks/scripts/migrate_open_labels.py"),
            "--config",
            str(args.config.resolve()),
            "--output",
            str(args.output.resolve()),
            "--number",
            str(number),
        ]
        if args.apply:
            command.append("--apply")
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=900
        )
        path = args.output / str(number) / "execution.json"
        if not path.exists():
            return {
                "number": number,
                "status": "execution_error",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        record = json.loads(path.read_text())
        return {
            key: record.get(key)
            for key in ("number", "status", "add", "remove", "diagnostics")
        }

    stop = None
    for offset in range(0, len(pending), args.batch_size):
        rates = json.loads(
            subprocess.run(
                ["gh", "api", "rate_limit"], capture_output=True, text=True, check=True
            ).stdout
        )["resources"]
        if any(rates[name]["remaining"] < 200 for name in ("core", "graphql")):
            stop = {
                "reason": "API rate headroom below 200; wait for reset before starting another batch",
                "rates": {name: rates[name] for name in ("core", "graphql")},
            }
            break
        batch = pending[offset : offset + args.batch_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for pair_offset in range(0, len(batch), 2):
                futures = [
                    pool.submit(item, number)
                    for number in batch[pair_offset : pair_offset + 2]
                ]
                for future in concurrent.futures.as_completed(futures):
                    record = future.result()
                    print(json.dumps(record), flush=True)
                    if record["status"] in ("partial", "execution_error"):
                        stop = {
                            "reason": "Uncertain/systemic execution; inspect before starting another item",
                            "record": record,
                        }
                if stop:
                    break
        if stop:
            break
        if (
            args.max_batches is not None
            and offset // args.batch_size + 1 >= args.max_batches
        ):
            stop = {
                "reason": "Planned batch audit boundary; continue with the same config/output",
                "resumable": True,
            }
            break
    records = [
        json.loads(path.read_text()) for path in args.output.glob("*/execution.json")
    ]
    summary = {
        "configured": len(config["cases"]),
        "attempted": len(records),
        "counts": {},
        "stop": stop,
    }
    for record in records:
        summary["counts"][record["status"]] = (
            summary["counts"].get(record["status"], 0) + 1
        )
    (args.output / "batch-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
