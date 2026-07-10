#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Orchestrate the PLAN.md component ladder. Prereqs: gateway running,
# `openssl`, `python3` on the host. Idempotent-ish: recreates the bench
# sandbox each run.
#
# Usage: ./run-ladder.sh [reps]
set -euo pipefail
cd "$(dirname "$0")"

REPS=${1:-30}
PORT=8443
SANDBOX=bench
OUT="results-v2/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

[ -f ca/server.pem ] || ./gen-ca.sh

# echo server on the host
python3 echo-server.py "$PORT" ca/server.pem ca/server.key &
ECHO_PID=$!
trap 'kill $ECHO_PID 2>/dev/null || true' EXIT
sleep 1

# dummy provider so rung D exercises placeholder rewrite with a fake secret
openshell provider get bench >/dev/null 2>&1 || \
  openshell provider create --name bench --type generic --credential BENCH_TOKEN=bench-dummy-value

openshell sandbox delete "$SANDBOX" 2>/dev/null || true
openshell sandbox create --name "$SANDBOX" --from . \
  --policy policy-l4.yaml --provider bench --no-tty -- true
openshell sandbox upload "$SANDBOX" bench-client.sh /home/sandbox/

BASE="https://host.docker.internal:${PORT}"
in_sandbox() { # env-string
  openshell sandbox exec -n "$SANDBOX" -- bash -c "$1 bash /home/sandbox/bench-client.sh"
}

echo "== rung A: host -> echo server, direct (floor)"
RUNG=A BASE="$BASE" REPS="$REPS" CELLS="sizes keepalive header" \
  EXTRA="--cacert ca/ca.pem --resolve host.docker.internal:${PORT}:127.0.0.1" \
  ./bench-client.sh > "$OUT/rungA.csv"

echo "== rung B: in-sandbox, L4 passthrough"
in_sandbox "RUNG=B BASE=$BASE REPS=$REPS CELLS='sizes keepalive'" > "$OUT/rungB.csv"

echo "== rung C: in-sandbox, L7 terminate+rest"
openshell policy set "$SANDBOX" --policy policy-l7.yaml --wait
in_sandbox "RUNG=C BASE=$BASE REPS=$REPS CELLS='sizes keepalive header'" > "$OUT/rungC.csv"

echo "== rung D: rung C + placeholder Authorization header"
in_sandbox "RUNG=D BASE=$BASE REPS=$REPS CELLS=sizes SIZES='1 100' AUTH=\"\$BENCH_TOKEN\"" > "$OUT/rungD.csv"

echo "== rung E: request_body_credential_rewrite"
openshell policy set "$SANDBOX" --policy policy-l7-bodyrewrite.yaml --wait
in_sandbox "RUNG=E BASE=$BASE REPS=$REPS CELLS=sizes SIZES='1 100' JSON=1" > "$OUT/rungE.csv"

echo
echo "results in $OUT/ (rungA-E.csv); analyze with ./analyze.py $OUT"
