# Definition-edit tools used for #5151

This records the one-off GitHub REST operations used during preparation. The
snippets share the helpers below to avoid repeating subprocess plumbing; the
create, update, and retirement operations were run separately after authorization.
They are a historical record, not a new bulk apply command. Do not replay a
previous plan: first refresh `prepare_label_taxonomy.py` and review its operations.

No snippet changes issue/PR associations. Retirement renames the existing label;
it does not delete/recreate it. Existing associations display the renamed label.

## Shared REST plumbing

All Python snippets were run with `uv run --no-project --offline --python
/usr/bin/python3 python` and authenticated `gh`, against `NVIDIA/OpenShell`.

```python
import json
import subprocess
from pathlib import Path
from urllib.parse import quote


def api(args, data=None):
    result = subprocess.run(
        ['gh', 'api', *args],
        input=None if data is None else json.dumps(data),
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def labels():
    return {
        label['name']: label
        for page in api(['--paginate', '--slurp', 'repos/NVIDIA/OpenShell/labels'])
        for label in page
    }


def label_path(name):
    return 'repos/NVIDIA/OpenShell/labels/' + quote(name, safe='')


catalog = json.loads(Path('tasks/labels/taxonomy.json').read_text())
```

## Create missing active definitions

Saved the original definitions to `/tmp/openshell-labels-before-create.json` and
the 19 missing definitions to `/tmp/openshell-labels-to-create.json`.

```python
before = labels()
missing = [entry for entry in catalog['active'] if entry['name'] not in before]
for definition in missing:
    result = api(
        ['--method', 'POST', 'repos/NVIDIA/OpenShell/labels', '--input', '-'],
        definition,
    )
    assert all(result[key] == definition[key]
               for key in ('name', 'description', 'color'))
```

The initial process timed out after partial progress. Before resuming, fetched
labels again and created only names still missing. Final verification checked all
19 intended definitions and that all 80 pre-existing definitions retained their
IDs, names, descriptions, and colors. Saved the final definitions to
`/tmp/openshell-labels-after-create.json`.

## Update nine existing active definitions

Saved the fresh originals to `/tmp/openshell-nine-definitions-before.json`.

```python
before = labels()
changes = [entry for entry in catalog['active']
           if entry['name'] in before and any(
               before[entry['name']][key] != entry[key]
               for key in ('description', 'color'))]
assert len(changes) == 9
for definition in changes:
    result = api(
        ['--method', 'PATCH', label_path(definition['name']), '--input', '-'],
        {key: definition[key] for key in ('description', 'color')},
    )
    assert result['id'] == before[definition['name']]['id']
```

Re-read all definitions, verified all 28 active definitions against the catalog,
and verified other definitions were unchanged. Saved the final definitions to
`/tmp/openshell-nine-definitions-after.json`.

## Retire 18 obsolete definitions

Saved the fresh preview, including complete original definitions, to
`/tmp/openshell-label-retirement-plan.json` using:

```shell
uv run --no-project python tasks/scripts/prepare_label_taxonomy.py --repo NVIDIA/OpenShell > /tmp/openshell-label-retirement-plan.json
```

```python
plan = json.loads(Path('/tmp/openshell-label-retirement-plan.json').read_text())
operations = plan['operations']
assert len(operations) == 18
assert all(entry['action'] == 'retire' for entry in operations)
results = []
for operation in operations:
    before, after = operation['before'], operation['after']
    current = api([label_path(before['name'])])
    assert all(current[key] == before[key]
               for key in ('id', 'node_id', 'name', 'color', 'description'))
    result = api(
        ['--method', 'PATCH', label_path(before['name']), '--input', '-'],
        {'new_name': after['name'], 'color': after['color'],
         'description': after['description']},
    )
    assert result['id'] == before['id']
    assert result['node_id'] == before['node_id']
    assert all(result[key] == after[key]
               for key in ('name', 'color', 'description'))
    results.append({'before': before, 'after': result})
    Path('/tmp/openshell-label-retirement-results.json').write_text(
        json.dumps(results, indent=2))
```

Re-read all definitions and verified that the 18 original names were absent,
their retired definitions matched the plan with the same IDs, and all other
definitions retained their IDs, names, descriptions, and colors. Saved the final
definitions to `/tmp/openshell-labels-post-retirement.json`. The absent broad
`topic:sdk` label was not created or retired.

## Per-item changes

Manual item tests used the merged `.agents/skills/label-issue/SKILL.md` and
`tasks/scripts/label_issue.py` prepare/preview/apply contract, not custom mutation
code. The verified repeat check of #5451 used:

```shell
uv run --no-project python tasks/scripts/label_issue.py prepare --repo NVIDIA/OpenShell --item 5451 --trusted-actor purp --output /tmp/openshell-5451-verification-complete
```

It returned `unchanged`, `checkpoint_verified: true`, and no ordered writes.
`meta:labeler-checkpoint` was provisioned separately by the maintainer.
