#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Render the full read-only classifier comparison for a GitHub comment."""

import argparse
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
data = json.loads((args.directory / "comparison.json").read_text())
records = data["records"]
config = data["configuration"]


def classification(record):
    return (record.get("answer") or {}).get("classification") or {}


def labels(record):
    result = classification(record)
    return {result["area"], *result["topics"]} if result.get("area") else None


def token_counts(record):
    usage = record.get("metrics", {}).get("usage") or {}
    values = [
        usage.get(key, 0)
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        )
    ]
    return [
        *values,
        sum(values),
        (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0),
    ]


def status(record):
    if record.get("outcome"):
        return record["outcome"]["status"]
    if "answer" not in record:
        return "Invalid JSON / execution error"
    return (record.get("preview") or {}).get("status") or record["answer"].get(
        "outcome", "missing"
    )


with_retries = any(record.get("attempts") for record in records)
lines = [
    "## Sonnet / Haiku label-migration preview comparison",
    "",
    "Relates to #5151. **No GitHub labels, assignments, reviewer requests, or checkpoints were written by this experiment.**",
    "",
    "### Method and limits",
    "",
    (
        "- Same preselected items and frozen evidence per item/model. Schema-constrained output, at most one validation-guided retry, and no automatic response repair. Each attempt uses a fresh CLI session. Per-item metrics sum both attempts; full attempt outputs and validation feedback are retained below."
        if with_retries
        else "- Same ten preselected items, one fresh independent Claude CLI session per item/model, no retries or response repair. Eight items passed the shared acceptance/lifecycle gate; two were gate controls."
    ),
    "- Shared helper preparation used `force=True` only to bypass unchanged-checkpoint detection, never acceptance or lifecycle restrictions. Each model received the same frozen packet, full trusted skill/result contract, canonical scopes, current definitions, and expanded available substantive sources. Input/system hashes were recorded per run.",
    "- This is a **fixed-evidence classifier comparison**, not a benchmark of autonomous evidence gathering or a full `/label-issue` agent session. Models had no tools/MCP access and could not search for additional context. Helper validation and fresh live previews ran outside the model; no apply path was invoked.",
    "- Both CLI invocations requested `--effort medium`. The CLI accepted the flag; the output does not establish equivalent effective effort across model families. Resolved model IDs are reported below. The configured skill requires explicit ambiguity or null; null conventionally means high confidence.",
    "- Wall time measures the Claude subprocess only (startup plus model request). Preparation and helper preview time are separate. Up to three runs were in flight, so these single observations include scheduling/provider variability and cache warming; they are not stable latency estimates.",
    "- Token totals = uncached input + cache-write input + cache-read input + output. Thinking tokens, when reported, are a subset of output and are not added again. Cache read/write are not comparable to freshly billed input; costs below are CLI list-price estimates, not a subscription invoice.",
    "- Confidence is model self-report, not measured accuracy. No human gold classifications were supplied. Validator acceptance proves contract compliance, not correct topic selection. Malformed or held outputs were retained, not silently fixed.",
    "",
    "### Summary",
    "",
]
for model in config["models"]:
    subset = [r for r in records if r["model"] == model]
    metrics = [r["metrics"] for r in subset if "metrics" in r]
    ids = sorted({key for m in metrics for key in (m.get("model_usage") or {})})
    counts = {}
    for record in subset:
        key = status(record)
        counts[key] = counts.get(key, 0) + 1
    total = sum(token_counts(r)[4] for r in subset)
    cost = sum(m.get("reported_cost_usd") or 0 for m in metrics)
    times = [m["wall_seconds"] for m in metrics]
    lines.append(
        f"- **{model}** (`{'`, `'.join(ids)}`): {counts}; {total:,} total reported tokens; ${cost:.4f} list-price estimate; mean wall {statistics.mean(times):.2f}s, median {statistics.median(times):.2f}s. Sum of per-run wall times {sum(times):.2f}s (not elapsed batch time)."
    )
incomplete = [
    f"#{r['number']} {r['model']}"
    for r in records
    if r.get("metrics", {}).get("usage_complete") is False
]
if incomplete:
    lines += [
        "- **Incomplete usage measurements:** "
        + ", ".join(incomplete)
        + ". Their totals include only reported counters and are lower bounds, not complete token/cost measurements."
    ]
comparable = []
for case in config["cases"]:
    pair = [r for r in records if r["number"] == case["number"]]
    if len(pair) == 2 and all(labels(r) is not None for r in pair):
        comparable.append(pair)
if comparable:
    same = sum(labels(pair[0]) == labels(pair[1]) for pair in comparable)
    lines.append(
        f"- Exact proposed area/topic sets agree on **{same}/{len(comparable)} parseable classified pairs**, including outputs that the helper subsequently held. The other pairs are gates or malformed/missing outputs; they are not counted as classification agreement."
    )
lines += [
    "",
    "Review differences in topic breadth, primary-area selection, confidence calibration, and contract compliance separately. Validator acceptance establishes neither correct classification nor calibrated confidence.",
    "",
    "### Per-item choices and confidence",
    "",
    "| Item | Model | Proposed area + topics | Overall confidence | Helper outcome | Attempts |",
    "|---|---|---|---|---|---:|",
]
for record in records:
    label_set = labels(record)
    label_text = ", ".join(f"`{x}`" for x in sorted(label_set)) if label_set else "—"
    confidence = (record.get("answer") or {}).get("confidence", "unparsed")
    lines.append(
        f"| #{record['number']} | {record['model']} | {label_text} | {confidence} | {status(record)} | {record.get('metrics', {}).get('attempt_count', 1)} |"
    )
lines += [
    "",
    "### Per-run time and tokens",
    "",
    "| Item | Model | Wall s | CLI s | API s | Input | Cache write | Cache read | Output | Thinking subset | Total | List USD |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for record in records:
    metrics = record.get("metrics", {})
    counts = token_counts(record)
    lines.append(
        f"| #{record['number']} | {record['model']} | {metrics.get('wall_seconds', 0):.2f} | {(metrics.get('cli_duration_ms') or 0) / 1000:.2f} | {(metrics.get('api_duration_ms') or 0) / 1000:.2f} | {counts[0]:,} | {counts[1]:,} | {counts[2]:,} | {counts[3]:,} | {counts[5]:,} | {counts[4]:,} | {(metrics.get('reported_cost_usd') or 0):.4f} |"
    )
lines += [
    "",
    "Shared preparation and external helper-preview timings (seconds):",
    "",
    "| Item | Shared prepare | Sonnet preview | Haiku preview |",
    "|---|---:|---:|---:|",
]
for case in config["cases"]:
    number = case["number"]
    prep = json.loads(
        (args.directory / str(number) / "preparation-metrics.json").read_text()
    )
    times = []
    for model in config["models"]:
        record = next(
            r for r in records if r["number"] == number and r["model"] == model
        )
        value = record.get("metrics", {}).get("preview_wall_seconds")
        times.append(f"{value:.2f}" if value is not None else "not run")
    lines.append(
        f"| #{number} | {prep['wall_seconds']:.2f} | {times[0]} | {times[1]} |"
    )
lines += [
    "",
    "### Full results",
    "",
    "The model responses below are preserved as returned. Helper differences and diagnostics are authoritative for what a preview would do; any contradictory model summary is an observed defect, not an executed action.",
    "",
]
for case in config["cases"]:
    number = case["number"]
    input_data = json.loads((args.directory / str(number) / "input.json").read_text())
    preparation = input_data["preparation"]
    packet = input_data.get("packet") or {}
    body = (packet.get("evidence_index", {}).get("body") or {}).get("content", {})
    title = body.get("title", case["coverage"])
    kind = "pull" if packet.get("kind") == "pull_request" else "issues"
    lines += [
        f"#### [#{number}](https://github.com/NVIDIA/OpenShell/{kind}/{number}) — {title}",
        "",
        f"Coverage: {case['coverage']}. Preparation: **{preparation['status']}**.",
        "",
    ]
    if preparation.get("diagnostics"):
        lines += ["Gate diagnostics: " + "; ".join(preparation["diagnostics"]), ""]
    if packet:
        lines += [
            "Observed labels: "
            + ", ".join(f"`{x}`" for x in packet.get("existing_labels", [])),
            "",
        ]
    for record in [r for r in records if r["number"] == number]:
        model = record["model"]
        lines += [f"**{model}: {status(record)}**", ""]
        preview = record.get("preview")
        if preview:
            for key in (
                "add",
                "remove",
                "preserve",
                "bookkeeping",
                "diagnostics",
                "missing_prerequisites",
            ):
                if preview.get(key):
                    lines.append(f"- {key}: " + "; ".join(str(x) for x in preview[key]))
            lines.append("")
        if record.get("outcome", {}).get("diagnostics") and not preview:
            lines += [
                "Final diagnostics: " + "; ".join(record["outcome"]["diagnostics"]),
                "",
            ]
        attempts = record.get("attempts") or [record]
        for index, attempt in enumerate(attempts, 1):
            answer = attempt.get("answer")
            envelope = attempt.get("cli") or {}
            raw = (
                json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
                if answer is not None
                else envelope.get(
                    "structured_output",
                    envelope.get(
                        "result",
                        attempt.get("raw_response")
                        or (attempt.get("parse-error") or {}).get(
                            "raw_response", "No response"
                        ),
                    ),
                )
            )
            if not isinstance(raw, str):
                raw = json.dumps(raw, ensure_ascii=False)
            lines += [
                "<details>",
                f"<summary>Complete {model} attempt {index}</summary>",
                "",
                "```json",
                raw,
                "```",
                "",
            ]
            if record.get("attempts"):
                metrics = attempt.get("metrics") or {}
                usage = metrics.get("usage") or {}
                metadata = {
                    "validation": attempt.get("validation"),
                    "wall_seconds": metrics.get("wall_seconds"),
                    "cli_duration_ms": metrics.get("cli_duration_ms"),
                    "api_duration_ms": metrics.get("api_duration_ms"),
                    "usage": {
                        key: usage.get(key)
                        for key in (
                            "input_tokens",
                            "cache_creation_input_tokens",
                            "cache_read_input_tokens",
                            "output_tokens",
                            "output_tokens_details",
                        )
                    },
                    "reported_cost_usd": metrics.get("reported_cost_usd"),
                }
                lines += [
                    "Attempt validation and metrics:",
                    "",
                    "```json",
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                    "```",
                    "",
                ]
            lines += ["</details>", ""]
lines += [
    "### Reproduction",
    "",
    "Tools and the ten-case fixture are on the fork-only `purp/label-migration-tools` branch in `purp/OpenShell`: `compare_label_models.py`, `render_label_model_comparison.py`, and `tasks/labels/model-comparison.json`. Raw CLI envelopes, exact frozen inputs, hashes, metrics, and previews are retained in the local experiment directory; model outputs have not been repaired or applied.",
    "",
]
args.output.write_text("\n".join(lines))
print(json.dumps({"characters": len(args.output.read_text()), "records": len(records)}))
