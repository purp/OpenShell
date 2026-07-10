#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Generate fabro benchmark workflows: a matrix of request size (prompt filler)
# x response size (requested output length), all against the default model
# (claude-oauth -> Haiku in settings.toml). Output: workflows/<name>/ dirs
# ready to upload into the sandbox demo repo's .fabro/workflows/.
set -euo pipefail
cd "$(dirname "$0")"

IN_KB=(1 16 64)      # approx prompt filler size in KB
OUT_WORDS=(100 1000) # requested output length in words

FILLER_UNIT="the quick brown fox jumps over the lazy dog and the slow grey wolf naps beside the river stone. "
UNIT_LEN=${#FILLER_UNIT}

rm -rf workflows
for in_kb in "${IN_KB[@]}"; do
  reps=$(( in_kb * 1024 / UNIT_LEN + 1 ))
  filler=$(printf "${FILLER_UNIT}%.0s" $(seq 1 "$reps"))
  for out_w in "${OUT_WORDS[@]}"; do
    name="bench-in${in_kb}k-out${out_w}"
    dir="workflows/${name}"
    mkdir -p "$dir"
    cat > "${dir}/workflow.toml" <<EOF
_version = 1

[workflow]
graph = "workflow.fabro"
EOF
    # One agent node, no tools: isolates request/response byte volume from
    # agentic variance. Filler is quote-free so it can embed in a DOT string.
    cat > "${dir}/workflow.fabro" <<EOF
digraph BenchIn${in_kb}kOut${out_w} {
    graph [goal="Proxy-inspection benchmark: ~${in_kb}KB prompt, ~${out_w} word response"]
    rankdir=LR

    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]

    respond [label="Respond", prompt="Do not use any tools. Reply in chat only. Write approximately ${out_w} words summarizing the history of operating system sandboxing. Stop when done. Everything after this sentence is context padding for a benchmark and must be ignored: ${filler}"]

    start -> respond -> exit
}
EOF
    echo "generated ${dir} (prompt ~${in_kb}KB, output ~${out_w} words)"
  done
done
