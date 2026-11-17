# Holdout set 2026-11g (for DT-QA-27)

Collected on 2026-11-16 under the rules in `../README.md`, to give DT-QA-27 (`../../agent-fix/qa27/README.md`) broken
updates that neither DepTime nor its fix command was shaped on. It was collected after 0.2.3 was released. **This
directory was committed before DepTime or an agent ran on any of it.**

## Uses

497 upgrades of real projects (Tier A 280, Tier B 217), each from the version a project pins to the package's newest
release before the cutoff, 7,815 uses asked about:

| Work | Break | Excluded |
|---|---|---|
| 5,868 | 373 | 1,574 |

60 upgrades have at least one use labelled `breaks`: these are DT-QA-27's tasks.

The upgrades come from 463 pinned repositories. All 53 covered packages were searched with `find_pinned.py --per 10`
(`selection.json`: every candidate GitHub's code search returned, and why each skipped one was skipped); a repository
2026-11 to 2026-11f or DT-QA-22's pull requests had asked about didn't qualify. Every package has ten upgrades or more
but typer (4), click (2), marshmallow (1) and urllib3 (none in its first 500 results). The cutoff is 2026-11-16.
Unlike the earlier sets, only upgrades to the newest release are kept: `find_pinned.py` also lists the same code on a
release a year older, which DT-QA-27 doesn't use, so those 314 were dropped before the probe. There is no exercise
stratum and no traceback set.

455 of the 458 environments installed. The three that didn't install from wheels on any of the probe's Pythons, even
with the fallback (`probe-envs.json`): chromadb 0.3.26 and 0.3.29 and crewai 0.63.5; their uses are excluded. Four
needed setuptools added (crewai 0.11.0, gradio 3.24.1, 3.34.0 and 3.35.2).

Labels come from `holdout` run [44003382040](https://github.com/cschmertz/deptime/actions/runs/44003382040) (branch
`spike/holdout`). 78 working uses are deprecated by the probe's rule.

Of the 22 breaks found by binding a call, one was changed by hand (`label-overrides.json`): mcp 2.3.0's
`types.CallToolRequest(params=)`. The class gives `method` a default over its generic base, so the call still works
(mcp's own client makes it). The other 21 were checked against the source at `to`, read from the release's wheel or
sdist, and kept; `label-overrides.json` lists them under `kept`.
