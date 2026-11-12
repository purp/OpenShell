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
2. Review the current repository workflows, scripts, templates, skills, required
   checks, and external webhook/app/project filters for names being retired.
   Repository code alone cannot establish external compatibility. A denied
   webhook lookup is an outstanding check, not evidence that no hooks exist.
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
