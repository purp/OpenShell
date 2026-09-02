# Contributing to OpenShell

OpenShell is built agent-first. We use agents to design and implement systems, while humans manage product decisions and the project roadmap.

## The Critical Rule

**You must understand your code.** Using AI agents to write code is not just acceptable, it's how this project works. But you must be able to explain what your changes do and how they interact with the rest of the system. If you can't, don't submit it.

Submitting agent-generated code without understanding it — regardless of how clean it looks — wastes maintainer time and will result in your PR being closed. Repeat offenders will be blocked from the project.

## AI Usage

OpenShell is agent-first, not agent-only. The distinction matters:

- **Do** use agents to explore the codebase, run diagnostics, generate code, and iterate on implementations.
- **Do** use the skills in `.agents/skills/` — they exist to make your agent effective.
- **Do** interrogate your agent until you understand every edge case and interaction in your changes.
- **Don't** submit code you can't explain without your agent open.
- **Don't** use agents as a substitute for understanding the system. Read the architecture docs.

## First-Time Contributors

We use a vouch system. This exists because AI makes it trivial to generate plausible-looking but low-quality contributions, and we can no longer trust by default.

1. Open a [Vouch Request](https://github.com/NVIDIA/OpenShell/discussions/new?category=vouch-request) discussion.
2. Describe what you want to change and why.
3. Write in your own words. AI-generated vouch requests will be denied.
4. A maintainer will comment `/vouch` if approved.
5. Once vouched, you can submit pull requests.

**If you are not vouched, any pull request you open will be automatically closed.** Org members and collaborators with push access bypass this check.

### Finding Work

Issues labeled [`good first issue`](https://github.com/NVIDIA/OpenShell/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are scoped, well-documented, and friendly to new contributors. Start there. If you need guidance, comment on the issue.

An open issue is not necessarily accepted or ready to be worked on. Human contributors should look for `state:accepted`, roadmap placement, `good first issue`, or `help wanted`, or ask a maintainer before starting. Unattended agents require the expected human-applied lifecycle state: `state:accepted` or roadmap placement to plan, and `state:agent-ready` to implement. An agent directly asked to work on a specific issue warns about missing or incomplete expected labels and continues with the requested phase without changing them.

## Before You Open an Issue

Search open and closed issues for the same need. Bug reports and feature requests must include:

1. **User Story:** who needs the change and what they need to do.
2. **Problem Statement:** a concise summary of what is broken or missing in the current behavior.
3. **Impact / Why This Matters:** the consequences of the current behavior, the current workaround, and why that workaround is insufficient.
4. **Acceptance Criteria:** specific, observable outcomes that define success.

Feature requests must also propose a user-facing workflow and describe alternatives considered. Define the externally observable behavior and leave internal implementation choices open. Bug reports instead include minimal reproduction steps, the OpenShell version and relevant environment, and a small, redacted log excerpt when it materially clarifies the behavior.

The project includes optional [agent skills](#agent-skills-for-contributors) for self-service troubleshooting and exploration. Use them when they help you, but summarize any useful result in your own words rather than pasting a diagnostic transcript.

### When to Open an Issue

- A workflow behaves differently from what you need or reasonably expect.
- OpenShell does not support an outcome that matters to your workflow.
- The available documentation or configuration does not explain how to complete a supported workflow.
- Security vulnerabilities must follow [SECURITY.md](SECURITY.md) — **not** GitHub issues.

### When NOT to Open an Issue

- General questions or open-ended discussion — use [GitHub Discussions](https://github.com/NVIDIA/OpenShell/discussions).
- Security vulnerabilities — follow [SECURITY.md](SECURITY.md) instead.

## Before You Submit a Change

Do not start substantial issue-backed work until a maintainer has accepted the issue, unless a maintainer directly asks you to investigate or implement it. Once the work is authorized, use your agent to investigate the current code and behavior. If the issue contains earlier diagnostics, verify them rather than relying on them.

Use agents and the repository skills as needed to understand the affected code, evaluate tradeoffs, implement the smallest coherent change, and verify it. The pull request should explain what changed and how it was tested; it should not substitute an agent transcript for the contributor's understanding.

## Agent Skills for Contributors

Skills live in `.agents/skills/`. Your agent's harness can discover and load them natively. Here is the full inventory:

| Category        | Skill                     | Purpose                                                                                             |
| --------------- | ------------------------- | --------------------------------------------------------------------------------------------------- |
| Getting Started | `openshell-cli`           | CLI usage, sandbox lifecycle, provider management, BYOC workflows                                   |
| Getting Started | `debug-openshell-cluster` | Diagnose gateway deployment and health issues                                                       |
| Getting Started | `debug-inference`         | Diagnose `inference.local`, host-backed local inference, and direct external inference setup issues |
| Contributing    | `create-spike`            | Investigate a problem, produce a structured GitHub issue                                            |
| Contributing    | `create-rfc`              | Create RFC proposals from the repository template                                                   |
| Contributing    | `build-from-issue`        | Plan and implement work from a GitHub issue (maintainer workflow)                                   |
| Contributing    | `create-github-issue`     | Create well-structured GitHub issues                                                                |
| Contributing    | `create-github-pr`        | Create pull requests with proper conventions                                                        |
| Reviewing       | `review-github-pr`        | Summarize PR diffs and key design decisions                                                         |
| Reviewing       | `review-security-issue`   | Assess security issues for severity and remediation                                                 |
| Reviewing       | `fix-security-issue`      | Implement an approved security remediation plan                                                     |
| Reviewing       | `watch-github-actions`    | Monitor CI pipeline status and logs                                                                 |
| Reviewing       | `launch-openshell-gator`  | Launch and supervise OpenShell gator agents for issue and PR monitoring                             |
| Reviewing       | `test-release-canary`     | Dispatch and iterate on the Release Canary workflow that smoke-tests published artifacts            |
| Triage          | `triage-issue`            | Assess, classify, and route community-filed issues                                                  |
| Platform        | `generate-sandbox-policy` | Generate YAML sandbox policies from requirements or API docs                                        |
| Platform        | `helm-dev-environment`    | Start and manage the local Kubernetes development environment                                       |
| Platform        | `tui-development`         | Development guide for the ratatui-based terminal UI                                                 |
| Platform        | `build-openshell-mxc-windows` | Maintain and validate the build-only x64 and ARM64 Windows MSVC lane                             |
| Documentation   | `update-docs`             | Scan recent commits and draft doc updates for user-facing changes                                   |
| Maintenance     | `sync-agent-infra`        | Detect and fix drift across agent-first infrastructure files                                        |
| Reference       | `sbom`                    | Generate SBOMs and resolve dependency licenses                                                      |

### Workflow Chains

Skills connect into pipelines. Individual skill files don't describe these relationships.

- **Community inflow:** `triage-issue` → human disposition and roadmap placement → `create-spike` when needed → `build-from-issue`
- **Internal development:** `create-spike` → human disposition and roadmap placement → `build-from-issue`
- **Security:** `review-security-issue` → `fix-security-issue`
- **Policy iteration:** `openshell-cli` → `generate-sandbox-policy`

### Issue Lifecycle, Roadmap, and Agent Work

OpenShell separates technical assessment, roadmap decisions, sequencing, and agent delegation. Each is a distinct decision recorded by a distinct signal.

The full lifecycle reference lives in the published docs: **[Issue Lifecycle, Roadmap, and Agent Work](https://docs.nvidia.com/openshell/latest/contributing/issue-lifecycle)**. It covers the four decisions and who controls each, the eight `state:*` labels and their transitions, staleness as an orthogonal boundary, triage outcomes, human disposition, the roadmap, delegation to agents, spikes, and security issues.

The canonical machine-readable definition of every lifecycle label is [`.agents/issue-lifecycle.yaml`](.agents/issue-lifecycle.yaml). That file is the source of truth: no document, skill, or workflow may reference a `state:*` label it does not declare, and every label it declares exists on GitHub. The `sync-agent-infra` skill checks both directions.

Two rules cover most day-to-day cases:

- An open issue is not automatically accepted or ready for implementation. Check its `state:*` label before starting work, and ask a maintainer when its status is unclear.
- `state:stale` is an inactivity marker, not a lifecycle decision. A stale item keeps whatever `state:*` label it already had and rejoins the normal process on activity.

## Prerequisites

Install [mise](https://mise.jdx.dev/). This is used to set up the development environment.

```bash
# Install mise (macOS/Linux)
curl https://mise.run | sh
```

After installing `mise`, activate it with `mise activate` or [add it to your shell](https://mise.jdx.dev/getting-started.html).

Shell setup examples:

```bash
# Bash
echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc

# Fish
echo '~/.local/bin/mise activate fish | source' >> ~/.config/fish/config.fish

# Zsh
echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc
```

Project requirements:

- Rust 1.90+
- Python 3.11+
- Docker (running)

### Z3 installation

The `openshell-prover` crate links against Z3. On macOS and Linux, install the
system Z3 development package; `z3-sys` discovers it through `pkg-config`.

```bash
# macOS
brew install z3

# Ubuntu / Debian
sudo apt install libz3-dev

# Fedora
sudo dnf install z3-devel
```

If you prefer not to install Z3 system-wide, use the bundled Z3 feature. This
compiles Z3 from source during the Rust build:

```bash
cargo build -p openshell-prover --features bundled-z3
```

For x86-64 Windows MSVC builds, use one of these Z3 paths:

- System Z3: point `Z3_LIBRARY_PATH_OVERRIDE` at the directory containing the
  64-bit MSVC Z3 library and `Z3_SYS_Z3_HEADER` at the full path to `z3.h`.
  The `windows:*` tasks use this path automatically when `Z3_LIBRARY_PATH_OVERRIDE`
  is set.
- Bundled Z3: pass `--features bundled-z3` so `z3-sys` builds Z3 from source.

Both Windows paths still require `libclang.dll` for `bindgen`. If LLVM is not on
the default search path, set `LIBCLANG_PATH` to the directory containing
`libclang.dll`.

```powershell
$env:LIBCLANG_PATH='C:\Program Files\Microsoft Visual Studio\2022\<Edition>\VC\Tools\Llvm\x64\bin'
cargo build -p openshell-cli --target x86_64-pc-windows-msvc --features bundled-z3
```

To use a local x64 Z3 release with the Windows task wrapper:

```powershell
$env:Z3_LIBRARY_PATH_OVERRIDE='C:\path\to\z3-4.16.0-x64-win\bin'
$env:Z3_SYS_Z3_HEADER='C:\path\to\z3-4.16.0-x64-win\include\z3.h'
mise run --skip-tools windows:build:x64
```

### macOS build tools

Install Apple Command Line Tools before building locally:

```bash
xcode-select --install
```

## Getting Started

```bash
# One-time trust
mise trust

# Run a standalone gateway for local development
mise run gateway
```

## Building the `openshell` CLI

Inside this repository, `openshell` is a local shortcut script at `scripts/bin/openshell`. The script will

1. Build `openshell-cli` if needed.
2. Run the local debug CLI binary under `target/debug/openshell`.

Because `mise` adds `scripts/bin` to `PATH` for this project, you can run `openshell` directly from the repo.

```bash
openshell --help
openshell sandbox create -- codex
```

### Rust build cache

Mise preserves an existing `SCCACHE_DIR` so each environment can choose where
to store compiler cache entries. When `SCCACHE_DIR` is unset, OpenShell uses
the worktree-local `.cache/sccache` directory. To make cache entries available
to multiple worktrees on a workstation, set the variable to a user-level
directory before activating mise. For example:

```shell
export SCCACHE_DIR="$HOME/.cache/openshell/sccache"
```

CI can select a different directory or configure a remote sccache backend
without changing the workstation setting. Cargo output remains in each
worktree's `target/` directory.

OpenShell does not set `SCCACHE_BASEDIRS`. Sccache loads base directories when
its machine-local daemon starts, but the correct workspace root differs for
each worktree. Cache reuse therefore depends on the compiler inputs: outputs
that embed absolute paths, including Rust dependencies in some builds, can
still miss across worktrees.

## Main Tasks

These are the primary `mise` tasks for day-to-day development:

| Task                 | Purpose                                                 |
| -------------------- | ------------------------------------------------------- |
| `mise run gateway`   | Run a standalone gateway for local development          |
| `mise run sandbox`   | Create or reconnect to the dev sandbox                  |
| `mise run test`      | Default test suite                                      |
| `mise run e2e`       | Default end-to-end test lane                            |
| `mise run ci`        | Full local CI checks (lint, compile/type checks, tests) |
| `mise run docs`      | Validate Fern docs locally                              |
| `mise run helm:docs` | Regenerate the Helm chart README                        |
| `mise run clean`     | Clean build artifacts                                   |

## Project Structure

| Path            | Purpose                                       |
| --------------- | --------------------------------------------- |
| `crates/`       | Rust crates                                   |
| `python/`       | Python SDK and bindings                       |
| `sdk/go/`       | Go SDK (types, gRPC clients, converters)      |
| `sdk/typescript/` | TypeScript SDK (Connect client and generated protobuf bindings) |
| `proto/`        | Protocol buffer definitions                   |
| `tasks/`        | `mise` task definitions and build scripts     |
| `deploy/`       | Dockerfiles, Helm chart, Kubernetes manifests |
| `docs/`         | Published Fern docs source, navigation, and content assets |
| `fern/`         | Fern site config, components, and theme assets |
| `architecture/` | Architecture docs and plans                   |
| `rfc/`          | Request for Comments proposals                |
| `.agents/`      | Agent skills and persona definitions          |

## RFCs

New features always start as GitHub issues using the feature request template. For cross-cutting architectural decisions, API contract changes, or process proposals that need broad consensus, maintainers may ask for an RFC from the issue and assign an RFC number there. RFCs live in `rfc/`. See [rfc/README.md](rfc/README.md) for the full lifecycle and guidelines.

## Documentation

If your change affects user-facing behavior (new flags, changed defaults, new features, bug fixes that contradict existing docs), update the relevant pages under `docs/` in the same PR and adjust `docs/index.yml` if navigation changes. For explicit navigation entries, keep `page:` aligned with `sidebar-title` when present and put relative `slug:` values in `docs/index.yml`. Reserve frontmatter `slug` for folder-discovered pages or absolute URL overrides.

To ensure your doc changes follow NVIDIA documentation style, use the `update-docs` skill.
It scans commits, identifies doc pages that need updates, and drafts content that follows the style guide in `docs/CONTRIBUTING.mdx`.

To preview Fern docs locally:

```bash
mise run docs:serve
```

To run non-interactive validation:

```bash
mise run docs
```

PRs that touch `docs/**` or `fern/**` are validated by `.github/workflows/branch-docs.yml`, and they get a preview when `FERN_TOKEN` is available to the workflow.

Fern docs publishing is handled by the `publish-fern-docs` job in `.github/workflows/release-tag.yml` when a release tag is created.

`docs/` is the source-of-truth docs tree. `fern/` contains the site config, components, and theme assets that publish those pages.

See [docs/CONTRIBUTING.mdx](docs/CONTRIBUTING.mdx) for the current docs authoring guide.

## Pull Requests

1. Create a feature branch from `main`.
2. Make your changes with tests.
3. Run `mise run ci` to verify.
4. Open a PR using the `create-github-pr` skill or manually following the [PR template](.github/PULL_REQUEST_TEMPLATE.md).

PRs for new features, user-visible behavior changes, public API changes, architecture changes, or multi-PR efforts must link an accepted issue. Small documentation fixes, mechanical maintenance, and obvious localized bug fixes may omit a separate issue when the PR contains enough context to review the decision and implementation together.

In the PR's **Related Issue** section, use `Fixes #NNN` or `Closes #NNN` when an issue is required. For an exempt change, write `No issue required:` followed by a brief reason. Security fixes follow the private disclosure process in [SECURITY.md](SECURITY.md).

### Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/). All commit messages must follow the format:

```text
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**

- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `chore` - Maintenance tasks (dependencies, build config)
- `refactor` - Code change that neither fixes a bug nor adds a feature
- `test` - Adding or updating tests
- `ci` - CI/CD changes
- `perf` - Performance improvements

**Examples:**

```text
feat(cli): add --verbose flag to openshell run
fix(sandbox): handle timeout errors gracefully
docs: update installation instructions
chore(deps): bump tokio to 1.40
```

### DCO

All human contributions must include a `Signed-off-by` line in each commit message. This certifies you have the right to submit the work under the project license. See the [Developer Certificate of Origin](https://developercertificate.org/). Dependabot-authored dependency update PRs are allowlisted because the bot cannot sign commits.

```bash
git commit -s -m "feat(sandbox): add new capability"
```

DCO sign-off is separate from cryptographic commit signing. CI requires signing for org members so that copy-pr-bot can mirror your PR automatically; see [CI.md](CI.md#commit-signing) for setup.

## CI

How PR CI runs, the `test:e2e`, `test:e2e-gpu`, and `test:e2e-kubernetes` labels, copy-pr-bot, and commit-signing setup are documented in [CI.md](CI.md).
