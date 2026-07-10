#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Cell runner. Runs on the HOST (rung A, direct) or INSIDE the sandbox
# (rungs B-E, through the proxy). Emits CSV to stdout:
#   rung,cell,rep,namelookup,connect,appconnect,ttfb,total
#
# Env:
#   RUNG   - label (A|B|C|D|E)
#   BASE   - base URL, e.g. https://host.docker.internal:8443
#   REPS   - reps per cell (default 30)
#   CELLS  - which groups to run: "sizes keepalive header" (default sizes)
#   AUTH   - if set, add "Authorization: Bearer $AUTH" (rung D placeholder)
#   JSON   - if set, POST bodies use Content-Type: application/json (rung E)
#   EXTRA  - extra curl args, e.g. --cacert/--resolve on the host
set -euo pipefail

RUNG=${RUNG:?}; BASE=${BASE:?}; REPS=${REPS:-30}; CELLS=${CELLS:-sizes}
SIZES=${SIZES:-"1 100 1024 10240"}   # KB; rung E should use "1 100" (256 KiB rewrite cap)
W='%{time_namelookup},%{time_connect},%{time_appconnect},%{time_starttransfer},%{time_total}\n'
# -H 'Expect:' — curl auto-enables Expect: 100-continue for bodies >1MB and
# that handshake deadlocks in the sandbox tunnel (known proxy Expect bug).
CURL=(curl -sS -o /dev/null -H 'Expect:' -w "$W")
[ -n "${AUTH:-}" ] && CURL+=(-H "Authorization: Bearer ${AUTH}")
CT="application/octet-stream"; [ -n "${JSON:-}" ] && CT="application/json"
# shellcheck disable=SC2206
[ -n "${EXTRA:-}" ] && CURL+=(${EXTRA})

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
for kb in $SIZES; do
  if [ -n "${JSON:-}" ]; then
    # UTF-8 body so the body-rewrite path actually scans it
    head -c $((kb * 512)) /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c $((kb * 1024)) > "$TMP/req_${kb}k"
  else
    head -c $((kb * 1024)) /dev/urandom > "$TMP/req_${kb}k"
  fi
done

emit() { # cell rep csvline
  echo "${RUNG},$1,$2,$3"
}

run_cell() { # cell_name curl-args...
  local cell=$1; shift
  for rep in $(seq 1 "$REPS"); do
    emit "$cell" "$rep" "$("${CURL[@]}" "$@")"
  done
}

if [[ " $CELLS " == *" sizes "* ]]; then
  # response-direction and request-direction sweeps, one request per connection
  for kb in $SIZES; do
    run_cell "resp_${kb}k" "${BASE}/bytes/$((kb * 1024))"
    run_cell "req_${kb}k" -X POST -H "Content-Type: ${CT}" --data-binary "@${TMP}/req_${kb}k" "${BASE}/sink"
  done
fi

if [[ " $CELLS " == *" keepalive "* ]]; then
  # N requests over ONE connection: per-request constant = slope over N.
  # curl reuses the connection across repeated URLs in one invocation;
  # -w emits one line per URL. Tag lines with the request index.
  for n in 1 10 100; do
    urls=(); for _ in $(seq 1 "$n"); do urls+=("${BASE}/ok"); done
    for rep in $(seq 1 "$REPS"); do
      i=0
      "${CURL[@]}" "${urls[@]}" | while read -r line; do
        i=$((i + 1)); emit "ka${n}_req${i}" "$rep" "$line"
      done
    done
  done
fi

if [[ " $CELLS " == *" header "* ]]; then
  # header-size sweep: padding header exercises the byte-at-a-time parser
  for hkb in 1 4 12; do
    pad=$(printf 'h%.0s' $(seq 1 $((hkb * 1024))))
    run_cell "hdr_${hkb}k" -H "X-Bench-Pad: ${pad}" "${BASE}/ok"
  done
fi
