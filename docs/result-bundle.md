# Reading a schema v2 result bundle

A schema v2 run writes one new results directory and seals it with `manifest.json`. Keep the directory unchanged after the run. The manifest lists every payload file with its size and SHA-256 digest. The bundle is **author-submitted evidence**: matching hashes confirm that its contents have not changed since that manifest was written, not that the model run is authentic or independently reproduced.

## Contents

| Path | What it records |
| --- | --- |
| `snapshot/experiment.yaml` | Exact task selection, conditions, schedule settings, runner limits |
| `snapshot/suite/`, `snapshot/skills/`, `snapshot/implementation/` | Frozen task/verifier, skill, and harness source files |
| `plan.json` | Seeded task and condition order, run and tool-call budgets |
| `environment.json` | Python, OS, Codex CLI version, dependencies, source commit and dirty-tree flag |
| `metrics.json` | Per-run status, condition summaries, paired comparisons and limitations |
| `runs/RUN_ID/` | One run's public workspace, prompt, instructions, model events, stderr, tool audit, quota snapshot, evaluation, and run record |
| `report.html` | Human-readable view of `metrics.json` |
| `manifest.json` | Integrity list for every other file in the bundle |

The run workspace contains the copied public fixture and, when written, `output.json`. Hidden expected answers and verifier code are in the frozen suite snapshot, not in the agent workspace. `tools.jsonl` records tool names, status, paths, and write sizes; it does not preserve the full content of a write. `events.jsonl` contains model/runner events after disclosed host-path redaction. Read both when investigating a pass, failure, or unexpectedly low tool count. `evaluation.json` gives the trusted verifier process result. A completed model event and a valid tool protocol are required for a scored agent run.

## Offline integrity review

```bash
skillarena verify results/agent-suite
skillarena compare results/agent-suite --left v1 --right v2
skillarena report results/agent-suite/metrics.json --output results/agent-suite-view.html
```

`verify` checks the manifest schema and every file hash, rejects extra or missing files and unsafe paths, and does **not** execute bundle contents. It cannot prove who created the files, whether the model provider returned the recorded events, whether scoring rules were appropriate, whether the account was billed, or whether another person replicated the experiment. Review the frozen source and rerun from a trusted checkout to investigate those questions.

The sealed `report.html` is already present. When generating another report, choose an `--output` **outside** the sealed directory as shown. Saving any new file inside the bundle makes its manifest verification fail. The same rule applies to `skillarena compare --output`.

To compare two compatible bundles, pass both directories:

```bash
skillarena compare results/first results/second --left v1 --right v2 --output results/v1-v2-comparison.json
```

Compatibility requires the same suite identity/version/hash, task IDs and hashes, repetition count, and runner configuration. Different skill hashes are expected when comparing versions. Pairing uses task and repetition; pairs with missing, unrun, or infrastructure-error outcomes are counted but excluded from the paired delta. Pass rates use scored runs only. A descriptive task bootstrap interval is omitted if fewer than five tasks have complete pairs, any pair is partial, or every task delta is identical. An omitted interval is not evidence of equivalence.

## Status and interpretation

`passed` means a valid agent run produced the expected answer. `failed` includes wrong or missing answers and a started run that exceeded its time budget. `infrastructure_error` means the runner or evaluator could not produce a trustworthy score. `not_run` preserves scheduled slots after an early stop. Inspect all four counts before quoting any percentage. Report the task suite's synthetic nature, model alias, skill-loading protocol, sample size, excluded pairs, and whether the working tree was dirty.

The built-in quota check allows an existing ChatGPT login only, rejects API credentials and custom endpoints, and stops when included quota is low/unknown or paid-credit state is available/unknown. Its saved pre-run snapshots support review of that local guard. They are not an independent billing audit, and successful runs still consume included ChatGPT usage. No extra API-credit purchase is part of this workflow.
