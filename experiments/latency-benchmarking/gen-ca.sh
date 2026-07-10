#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Generate a throwaway bench CA + server cert for host.docker.internal.
# Output in ./ca/ (gitignored). The CA cert is baked into the bench image
# so both in-sandbox curl and the proxy's upstream client trust the echo
# server (the supervisor reads /etc/ssl/certs/ca-certificates.crt from the
# sandbox image).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ca

HOST=${1:-host.docker.internal}

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout ca/ca.key -out ca/ca.pem -days 30 -nodes \
  -subj "/CN=openshell-bench-ca" 2>/dev/null

openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout ca/server.key -out ca/server.csr -nodes \
  -subj "/CN=${HOST}" 2>/dev/null

openssl x509 -req -in ca/server.csr -CA ca/ca.pem -CAkey ca/ca.key \
  -CAcreateserial -out ca/server.pem -days 30 \
  -extfile <(printf "subjectAltName=DNS:%s" "$HOST") 2>/dev/null

echo "bench CA + server cert for ${HOST} in ./ca/"
