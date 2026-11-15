# Repository label preparation

`taxonomy.json` records the concise definitions and category colors agreed in
[#5151](https://github.com/NVIDIA/OpenShell/issues/5151). `REVIEWERS.md` remains the
source for full scopes and reviewer membership. The active names must match.

These one-time tools live only on `purp/label-migration-tools` in `purp/OpenShell`.
Do not merge this branch or its catalog, planner, tests, or runbook upstream.
[PR #5503](https://github.com/NVIDIA/OpenShell/pull/5503) contains only the permanent
routing, reviewer-roster, guidance, and regression-test changes.

Fetch this branch into a local checkout:

```shell
git fetch https://github.com/purp/OpenShell.git purp/label-migration-tools
git switch -c purp/label-migration-tools FETCH_HEAD
```

Preview all definition changes without modifying GitHub:

```shell
uv run --no-project python tasks/scripts/prepare_label_taxonomy.py --repo NVIDIA/OpenShell > label-definition-plan.json
```

The preview retrieves every page, records original definitions (including label
IDs), and lists creates, updates, and identity-preserving retirements. It rejects
unreviewed active names, conflicting retirement targets, archived definitions,
and drift between the catalog and roster. It also reports missing descriptions
in other label families for separate review; it never guesses workflow states.
`--labels-file` accepts an exported JSON array for an offline preview.

## Rollout

1. Land reviewed routing and roster support first. SDK language topics replace
   `topic:sdk` and route through their own rosters, initially seeded with the
   previous SDK reviewers. Classify cross-SDK work with each supported language
   topic. Individual subscriptions can be refined through reviewed changes.
2. Review the current repository workflows, scripts, templates, skills, and
   required checks for names being retired. External integration verification is
   not a rollout prerequisite: the changes have been announced, and owners of
   outward dependencies are responsible for adjusting their integrations.
3. Refresh the preview immediately before editing definitions and keep its
   original definitions as the recovery record. Create/update active definitions
   first. Rename each obsolete label in place to its complete `retired:` name;
   never delete/recreate it. Verify the same GitHub label ID survives retirement.
4. Use areas `#6699CC`, topics `#B3D1EB`, and retired labels `#EDEDED`. Renaming
   preserves associations but changes displayed names/colors on historical items
   too. Existing saved filters and subscriptions may need updating.
5. Re-read all definitions and compare the result with the plan. Save the verified
   before/after definitions and any exceptions. In-place renames can be reversed
   using the original names, IDs, descriptions, and colors after checking for
   concurrent edits and name collisions.

The preview has no apply mode. Definition edits require the separate authorized
preparation phase after the checks above. Do not change issue/PR assignments,
cycle checkpoint labels, or invoke the item classifier during preparation.
Recoloring/renaming definitions does not backfill reviewer requests. The later
per-item migration uses the shared `/label-issue` path, its current acceptance
and lifecycle checks, and an observed preview/application rollout under #5276.

## Tool record and open-item inventory

[Recorded definition edits](recorded-definition-edits.md) preserves the one-off
REST operations used to create missing labels, update existing definitions, and
retire obsolete names. It also records their verification and backup paths.
These are past operations; do not replay them against a stale plan.

Capture every page of open issues (the endpoint also includes PRs) and open PR
metadata into a local directory outside the checkout:

```shell
mkdir -p /tmp/openshell-open-inventory
gh api --paginate --slurp 'repos/NVIDIA/OpenShell/issues?state=open&sort=created&direction=asc&per_page=100' > /tmp/openshell-open-inventory/items.json
gh api --paginate --slurp 'repos/NVIDIA/OpenShell/pulls?state=open&sort=created&direction=asc&per_page=100' > /tmp/openshell-open-inventory/prs.json
uv run --no-project python tasks/scripts/inventory_open_labels.py --items-file /tmp/openshell-open-inventory/items.json --prs-file /tmp/openshell-open-inventory/prs.json --output-dir /tmp/openshell-open-inventory
```

The builder validates unique numbers and matching PR sets, then emits `rows.json`,
`inventory.csv`, and `summary.json`. It preserves complete label sets and includes
items with no classification labels or acceptance label. Eligibility is **not
evaluated**; `state:accepted` presence is only an observation. Proposals remain
blank until the shared helper examines each item. Pagination is not atomic:
refresh mismatched inputs, and recheck each item before application.

For replay, pass `--snapshot-utc` with the original UTC capture timestamp. The
initial snapshot at `2026-11-14T19:10:37Z` contained 679 items: 449 issues and 230
PRs, including 63 with retired labels and 535 with no classification labels at
all. Its tab is [Open inventory 2026-11-14](https://docs.google.com/spreadsheets/d/10E4rO8_0vgOc85oxHO3uvFvshqwtdYuF_tYvoRGji90/edit#gid=51511114).

Generate the Google Sheets batchUpdate body for a **new**, unused tab ID/title:

```shell
uv run --no-project python tasks/scripts/inventory_sheet_requests.py --rows-file /tmp/openshell-open-inventory/rows.json --sheet-id 51511115 --title 'Open inventory next snapshot' > /tmp/openshell-open-inventory/sheet-requests.json
```

The script performs no remote writes. Submit the structured `requests` array via
the connected Google Drive `batch_update_spreadsheet` tool with spreadsheet ID
`10E4rO8_0vgOc85oxHO3uvFvshqwtdYuF_tYvoRGji90`. The initial publication created
tab ID `51511114`, then submitted cell content and formatting in a second call.
The generator combines those steps; header notes use reusable wording. It writes
numbers and literal strings, never interpreting issue titles or labels as formulas.

After publishing, read back `A1:X<row count>` with `get_spreadsheet_range` and
compare every cell to `rows.json`, normalizing missing trailing cells to empty
strings and numbers to strings. This full readback passed for all 679 rows in
the initial snapshot. No other tabs or sharing permissions were changed.

Keep source tools on this branch. Raw GitHub responses, generated sheet requests,
and before/after snapshots stay outside Git; they may include issue bodies and
are not source code. No inventory tool invokes the classifier or applies labels.

## Sonnet/Haiku preview comparison

`model-comparison.json` records the ten-case selection and requested effort.
`compare_label_models.py` freezes shared helper evidence, invokes each classifier
with tools/MCP disabled, records its unmodified output and usage, then calls the
shared helper's read-only preview. It has no apply mode. This measures classification
against fixed evidence, not autonomous evidence gathering. Run from this checkout
with authenticated `gh` and Claude CLI credentials supplied by the environment.

```shell
uv run --no-project python tasks/scripts/compare_label_models.py prepare --output /tmp/openshell-label-model-comparison --number 5446
uv run --no-project python tasks/scripts/compare_label_models.py run --output /tmp/openshell-label-model-comparison --number 5446 --model sonnet
uv run --no-project python tasks/scripts/compare_label_models.py run --output /tmp/openshell-label-model-comparison --number 5446 --model haiku
```

Repeat for each configured number, preparing once and running each model once.
The recorded experiment used up to three concurrent processes and alternated the
requested model order across cases; #5446 was the initial pair. Preparation uses
`force=True` to bypass checkpoint shortcuts, retaining acceptance/lifecycle gates.
Gated cases are still sent to both classifiers to test respect for the same gate.
The runners refuse to overwrite frozen inputs or existing CLI results. Preserve
failures; use a new experiment directory for deliberate repeat trials.

The initial comparison was a single-attempt baseline. New runs pass a strict
response schema through Claude's `--json-schema` and validate the result locally
against that schema and the shared helper's policy. Every object rejects unknown
fields, including fields inside reasons. A malformed response or failed
schema/policy validation gets one fresh-session retry with the same frozen input,
the rejected response, and validation errors supplied as diagnostic data. The
runner does not repair model output. A second failure records a hold and returns
so the next item can run. Authentication/transport failures, missing definitions,
and stale live previews stop without repeating classification; changed evidence
requires a new preparation and review.

`attempt-1/` and, when needed, `attempt-2/` retain raw stdout/stderr, CLI envelopes,
responses, validation errors, exact prompts, and per-attempt metrics. Root metrics
sum both attempts' wall/API/CLI time, token counters, and reported costs. The CLI's
own structured-output retry exhaustion may trigger the one runner retry; any
internal CLI work remains included in its reported usage. Unavailable usage is
flagged rather than treated as a complete measurement. Reports show attempt
counts, final outcomes, and both responses. The original comparison artifacts
and published results are not overwritten by the new protocol.

```shell
uv run --no-project python tasks/scripts/compare_label_models.py report --output /tmp/openshell-label-model-comparison
uv run --no-project python tasks/scripts/render_label_model_comparison.py --directory /tmp/openshell-label-model-comparison --output /tmp/openshell-label-model-comparison/comment.md
```

Each item/model directory contains input/system hashes, the actual model ID and
raw CLI envelope, per-run monotonic wall time, CLI/API duration, input/output/cache
token counts, reported list-price cost, and the unmodified response. Parseable
classifications also have policy validation and a fresh helper preview. Model
wall time excludes shared preparation and external preview time; the report
lists those separately. Thinking tokens are a subset of output. Startup probes
are not part of the paired experiment totals. Confidence is self-report; neither
agreement nor validator acceptance establishes classification accuracy.

The renderer preserves every response, including malformed JSON, and produces
the comment body for #5276. Posting the comment is a separate authorized
`gh issue comment --body-file` operation. It does not post automatically.

Verify the retry boundaries without model requests or GitHub writes:

```shell
uv run --no-project python -m unittest discover -s tasks/scripts -p label_model_attempts_test.py
```

## Authorized migration execution

`reviewer-rubric.md` records the maintainer's reviewer-relevance rule, also
proposed for the permanent skill in #5581. The comparison runner includes it in
its trusted instructions. `reviewed-first-batch.json` records the eight agreed
classifications and body hashes from human review.

`migrate_open_labels.py` processes one item. The default is preview only;
`--apply` is for a migration phase already authorized by the maintainer. It
prepares fresh evidence, honors acceptance/lifecycle gates, validates output,
binds application to the exact preview, and verifies final labels. A changed
reviewed body is held. Existing item directories are never replayed, including
after partial writes; inspect the audit and explicitly reprepare for recovery.

```shell
uv run --no-project python tasks/scripts/migrate_open_labels.py --config tasks/labels/reviewed-first-batch.json --reviewed --number 5446 --output /tmp/openshell-reviewed-migration --apply
```

For later batches, omit `--reviewed` and use a config with `repository`,
`effort: "medium"`, `models: ["sonnet"]`, and `cases: [{"number": 1234}, ...]`
derived from the fresh open inventory. The runner respects verified unchanged
checkpoints and invokes Sonnet only for ready packets. The schema/retry runner
still has no application path: application occurs here through the shared
helper with the freshly previewed payload. Every attempted item retains
`execution.json`, evidence, preview, model metrics when used, and application
results. No classification comments are posted.

For a partial application, compare `applied.json` with live labels, revisions and
linked inputs before preparing a fresh capture in a different output directory.
Retain the original attempt. A successful reconciliation must verify its checkpoint;
merge its history only when its before-labels match the earlier observed after-labels.
Preserve the coordinator's stopped summary with the resolution audit before marking
that boundary resumable. A label set that looks correct alone is not verified completion.

Update the review inventory with eligibility, desired labels, differences,
rationale, review source, and verified outcome. Preserve the original snapshot
columns and retain fresh before/after labels in the execution audit. Stop
starting new items on uncertain writes or systemic failures; honor API retry
timing. Recheck open-item coverage after the initial inventory is exhausted.

`run_label_migration_batch.py --config CONFIG --output OUTPUT --apply` coordinates
the remaining config with two items at a time and ten-item rate-check batches.
It skips recorded attempts, refuses to replay incomplete item directories, and
stops starting items on uncertain writes or low API headroom. Its summary records
the stop reason and rate-reset information so continuation is explicit.

Create `OUTPUT/coordinator-stop` to stop the coordinator before another pair of
items starts. In-flight items finish and retain their audits. Remove the file
before explicitly resuming the same config and output directory. This permits
coordinator restarts without interrupting a label write.

`migration_sheet_requests.py` generates structured Sheets requests from execution
audits and a fresh read of the inventory's cell values. It updates only inventory
columns R:X, preserving the original snapshot, and maintains a separate
`Migration execution` tab with fresh before/desired/verified-after labels, review
source, model usage, checkpoints, and diagnostics. The audit includes newly opened
items absent from the older inventory. Use `--audit-exists` after creating the tab;
submit and read back through the Google Drive connector as for inventory uploads.
During bulk execution, upload after three completed ten-item batches, or sooner
when a new exception occurs or the coordinator stops. Per-item local audits are
written immediately; batching the full-sheet transfer avoids growing upload
overhead. Verify the sheet readback before marking an upload complete.

```shell
uv run --no-project python -m unittest discover -s tasks/scripts -p migrate_open_labels_test.py
```

## Reviewed testing corrections

`reviewed-testing-corrections.json` records the 13 human-approved removals of
`topic:testing` after reviewing the first migration results. Each decision retains
the other classification labels and pins the reviewed title/body digest.

Prepare a fresh preview with the existing reviewed-item path, then inspect it:

```shell
uv run --no-project python tasks/scripts/migrate_open_labels.py \
  --config tasks/labels/reviewed-testing-corrections.json \
  --output /tmp/openshell-testing-corrections --number "$item" --reviewed
uv run --no-project python tasks/scripts/apply_reviewed_label_correction.py \
  "/tmp/openshell-testing-corrections/$item" --remove topic:testing
```

Add `--apply` to the second command for authorized execution. It accepts only an
unattempted human-reviewed preview whose final state removes exactly that label.
The shared helper still checks freshness and exact requests and performs its
checkpoint bookkeeping. Preserve both the preview audit and application audit;
an `apply-started.json` blocks replay even after a process failure.
`testing-exclusion-audit.json` records subsequent reviewer-relevance checks. Its
case-level `review` records that source rather than direct human case review;
pass the matching `--review-source` when applying its removal previews. The
acceptance, lifecycle and shared-helper checks still apply.

Use `migration_sheet_requests.py --correction-dir
/tmp/openshell-testing-corrections` alongside the original `--execution-dir`
arguments to show the corrected final state and net migration changes. It checks
that each correction starts at the previously recorded final state. Original
execution files and model usage remain intact, and sheet diagnostics identify
the correction audit and superseded rationale.
The same history merge supports a successful fresh classification after a
no-write stale attempt. Keep the original attempt and fresh capture separate;
the sheet retains the actual follow-up review source and totals model time,
tokens and attempts across both runs.

## Keep the tooling out of upstream

After live definitions and item-level migration are verified, retain the final
definitions in GitHub, the routing/parser changes and regression coverage, the
reviewer roster, and the SDK classification guidance. Refine individual language
memberships as follow-on work.

The catalog, preview tool, and this runbook remain on this fork-only branch;
there is no upstream merge-and-removal cycle. They are not a second permanent
source of taxonomy policy. Keep the before/after audit and recovery records with
#5151 and the review inventory.

Run the tool's focused tests locally with:

```shell
uv run --no-project python -m unittest discover -s tasks/scripts -p prepare_label_taxonomy_test.py
```
