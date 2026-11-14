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
