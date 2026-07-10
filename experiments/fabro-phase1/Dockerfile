# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Fabro-on-OpenShell Phase 1: run the whole Fabro stack inside one governed sandbox.
#
# Base requirements from OpenShell BYOC: glibc, a shell, and iproute2 (proxy mode).
# Distroless / FROM scratch is unsupported (supervisor bootstrap needs them).
FROM debian:bookworm-slim

# aarch64 for Apple Silicon Docker Desktop; override for x86_64 hosts.
ARG FABRO_TARGET=aarch64-unknown-linux-gnu

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        iproute2 \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Fabro release binary (build-time fetch; runtime egress is governed by policy).
RUN curl -fsSL "https://github.com/fabro-sh/fabro/releases/latest/download/fabro-${FABRO_TARGET}.tar.gz" \
        | tar -xz -C /tmp \
    && install -m 0755 "/tmp/fabro-${FABRO_TARGET}/fabro" /usr/local/bin/fabro \
    && rm -rf "/tmp/fabro-${FABRO_TARGET}"

# Match the policy's process.run_as_user so the supervisor can drop privileges.
RUN useradd -m -u 1000 -s /bin/bash sandbox

WORKDIR /sandbox
RUN chown sandbox:sandbox /sandbox

CMD ["/bin/bash"]
