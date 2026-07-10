#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Run the benchmark workflow matrix against the running `fabro` sandbox.
# Prereqs: gateway up, sandbox `fabro` created and set up per ../NOTES.md,
# and ./gen-workflows.sh already run.
#
# Usage: ./run-bench.sh [reps]   (default 3)
set -euo pipefail
cd "$(dirname "$0")"

REPS="${1:-3}"
SANDBOX=fabro
WORKDIR=/sandbox/demo
RESULTS="results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS"

# sync workflows into the sandbox demo repo (upload dest is always a directory)
for d in workflows/*/; do
  openshell sandbox upload "$SANDBOX" "${d%/}" "${WORKDIR}/.fabro/workflows/"
done

now_ms() { python3 -c 'import time; print(int(time.time()*1000))'; }

echo "workflow,rep,wall_ms,exit_code" > "${RESULTS}/results.csv"
for d in workflows/*/; do
  wf=$(basename "$d")
  for rep in $(seq 1 "$REPS"); do
    log="${RESULTS}/${wf}-rep${rep}.log"
    t0=$(now_ms)
    rc=0
    openshell sandbox exec -n "$SANDBOX" --workdir "$WORKDIR" -- \
      bash -c "source ~/fabro-env.sh && fabro run ${wf} --environment local" > "$log" 2>&1 || rc=$?
    t1=$(now_ms)
    echo "${wf},${rep},$(( t1 - t0 )),${rc}" >> "${RESULTS}/results.csv"
    echo "${wf} rep${rep}: $(( t1 - t0 ))ms (rc=${rc})"
    # fabro's own timing breakdown (inference vs tool vs wall), if reported
    grep -iE 'inference|elapsed|duration|wall' "$log" | sed "s/^/    /" || true
  done
done

echo
echo "results in ${RESULTS}/results.csv; per-run logs alongside."
echo "note: wall_ms includes a constant 'openshell sandbox exec' round-trip;"
echo "compare deltas across sizes, not absolute values."
