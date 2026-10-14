# SkillArena

**Test whether a skill changes an agent's results on the same frozen tasks, and keep the evidence needed to inspect each run.**

SkillArena is a local benchmark harness. Version 0.2 runs a real Codex agent through a restricted file-tool interface and compares three conditions: no skill (`baseline`), an initial skill (`v1`), and a revised skill (`v2`). The included data workflow suite has ten original synthetic tasks. Its results describe this suite and setup; they do not measure general workplace performance.

[中文说明](README.zh-CN.md) · [Methodology](docs/methodology.md) · [Evidence bundle guide](docs/result-bundle.md)

## Current evidence

**Formal v0.2 experiment pending.** The checked-in [full experiment definition](examples/agent_suite.yaml) schedules 10 tasks × 3 conditions × 1 repetition = 30 agent runs. No 30-run result is claimed here. An earlier, separate [model-only Python bug-fix pilot](research/gpt6-sol-high-2026-10-14/README.md) found 3/3 passes with and without a skill; it used a different task and protocol and must not be treated as a data-suite result.

The [deterministic demo](examples/demo.yaml) is useful for checking the legacy command-runner workflow. Its 0% → 100% change comes from scripted agents, not model inference.

## Install and inspect the plan

Use Python 3.11+ and install from a trusted source checkout. This project is not published on PyPI.

```bash
git clone https://github.com/Cyber-Marty/SkillArena.git
cd SkillArena
python -m venv .venv
# Activate .venv for your shell.
python -m pip install -e .
skillarena plan examples/agent_suite.yaml
```

`plan` reads the frozen tasks and prints the scheduled order and budget **without starting a model**. The [six-run smoke definition](examples/agent_smoke.yaml) uses two tasks across the same three conditions; it is a setup check, not the full experiment.

## Run the agent suite

The agent path needs a current Codex CLI signed in with an existing ChatGPT login. If the command on `PATH` is an older CLI, set `SKILLARENA_CODEX_BIN` to the current executable. The CLI must support the configured `gpt-6-sol` model with high reasoning effort and the required strict configuration options.

```bash
skillarena doctor
skillarena run examples/agent_smoke.yaml --execute --output results/agent-smoke
skillarena run examples/agent_suite.yaml --execute --output results/agent-suite
skillarena verify results/agent-suite
skillarena compare results/agent-suite --left v1 --right v2
skillarena report results/agent-suite/metrics.json --output results/agent-suite-view.html
```

Use a new output directory for every run. `--execute` is required for schema v2 experiments. The full definition caps execution at 30 agent runs, 40 workspace-tool calls and 180 seconds per run. `doctor` and each run check the existing ChatGPT login and included quota. API credentials or custom endpoints are rejected; available or unknown paid-credit state and low or unknown included quota stop model execution. This is a local guard against extra API purchases, **not an independent account-billing audit**. A run consumes included ChatGPT usage when allowed. No command here buys credits.

The tool boundary is deliberately narrow: the agent can list and read task files, write only `output.json`, check that file's JSON syntax, and list or read the supplied skill. Shell, web, arbitrary code execution, and other tools are disabled. Skill access is explicit through `list_skills` and `read_skill`; this experiment does not test Codex's native implicit skill routing. `check_output` reports JSON syntax and types, not correctness. A trusted verifier scores the answer after the agent exits.

## What the suite measures

The [data workflow suite](benchmarks/data_workflows/README.md) covers CSV cleanup, deduplication, grouped aggregation, decimal money, UTC offset conversion, joins, missing versus zero, stable ranking, reconciliation, and JSON schema validation. Public instructions and input data are copied into a fresh workspace for each run. Expected answers and verifiers stay outside that workspace. Each task has an accepted oracle and a plausible wrong-answer test. All data are synthetic and MIT licensed; no independent real-world validity claim follows from these checks.

The default report records per-condition pass rates, paired differences, task-level outcomes, tool calls, skill reads, duration, and model-reported token usage where present. Infrastructure errors and unrun slots remain visible. The task bootstrap interval appears only when enough complete task pairs exist; it is descriptive. See [methodology](docs/methodology.md) before comparing versions.

## Evidence and comparisons

A completed schema v2 run writes a sealed directory with a manifest, source snapshot, plan, environment summary, per-run prompts and events, tool audit, submitted output, evaluator result, metrics, and HTML report. `skillarena verify` checks file integrity offline without executing bundle code. Matching hashes show that files have not changed since sealing; they do not authenticate the model run or establish independent replication. Put any regenerated report or comparison JSON **outside** the sealed bundle. [Bundle fields and review steps](docs/result-bundle.md) explain the limits.

`skillarena compare RESULTS --left v1 --right v2` compares two conditions in one bundle. A second compatible results directory can be supplied as `skillarena compare FIRST SECOND --left v1 --right v2`. Compatibility checks require matching suite identity and hashes, task IDs and hashes, repetition count, and runner configuration. A skill version comparison is meaningful only for the declared tasks and tool boundary.

The earlier command-based format still works with `skillarena run examples/demo.yaml --output results/demo`; it runs local commands from a trusted benchmark definition. Do not execute a benchmark definition from an untrusted source. See [CONTRIBUTING.md](CONTRIBUTING.md) for task requirements.

## Related projects and name

Other projects also evaluate agent skills, including [SkillsBench](https://github.com/benchflow-ai/skillsbench). [Jiaqi Liu's SkillArena dataset and framework](https://huggingface.co/datasets/JiaaqiLiu/SkillArena-datasets) also uses the SkillArena name. This repository is a separate project and claims no affiliation with either. MIT licensed.
