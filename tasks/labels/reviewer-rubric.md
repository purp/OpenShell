# Reviewer relevance

Choose the area whose reviewers are the right people to review the work. Add a
topic when the work has a clear, substantive connection to it and its reviewers
would be interested in seeing and potentially reviewing the change. Omit topics
with only incidental or speculative relevance. Supporting documentation or tests
can warrant their topic when that reviewer audience is relevant; their presence
alone does not.

Do not add `topic:testing` merely because a PR adds or extends tests to cover its
own code changes, including routine test-task or CI wiring needed to run those
tests. Judge any substantive changes to testing structure, tooling or strategy
separately under the reviewer-relevance rubric; this exclusion does not rule out
test-only work.

Apply this maintainer rubric when interpreting the canonical scopes and the
skill's shorthand about routine supporting work. Contributor automation belongs
to build/DX; reports about that automation do not by themselves warrant the
observability topic used for OpenShell gateway and sandbox telemetry.

The permanent skill update is proposed in NVIDIA/OpenShell#5581. This fork-only
copy keeps the migration aligned with the reviewed rubric before that PR lands.
