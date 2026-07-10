# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Bench sandbox image: curl + the throwaway bench CA baked into the system
# bundle, which BOTH in-sandbox curl AND the supervisor's upstream TLS client
# read (SYSTEM_CA_PATHS in openshell-supervisor-network/src/l7/tls.rs).
# Run gen-ca.sh before building so ca/ca.pem exists.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl iproute2 procps \
    && rm -rf /var/lib/apt/lists/*

COPY ca/ca.pem /usr/local/share/ca-certificates/openshell-bench-ca.crt
RUN update-ca-certificates

RUN useradd -m -u 1000 -s /bin/bash sandbox
WORKDIR /sandbox
