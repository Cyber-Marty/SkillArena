# Benchmark methodology

SkillArena v0.2 asks a local question: under one declared model, tool boundary, task suite, and scoring rule, how do outcomes differ among `baseline`, `v1`, and `v2`? The declared [full experiment](../examples/agent_suite.yaml) contains ten original synthetic data tasks and one repetition per condition, for 30 planned runs. The [six-run smoke configuration](../examples/agent_smoke.yaml) is a setup check. **The formal v0.2 experiment is pending; no full-suite outcome is reported here.**

## Experimental unit and controls

Each task and repetition forms a block containing all three conditions. A seed shuffles the initial condition order; subsequent blocks rotate positions to balance order. Each run receives a fresh copy of the same public fixture. The baseline has no skill package. `v1` and `v2` receive read-only packages with their respective `SKILL.md` files. The experiment fixes the Codex model alias (`gpt-6-sol`), high reasoning effort, timeout, tool-call budget, task bytes, and runner configuration across arms. The alias does not pin a provider snapshot, so behavior may change over time.

The run begins in an empty CLI context. The only task access is through a restricted workspace MCP server. Available operations are `list_files`, `read_file`, `write_file` for `output.json` only, `check_output` for JSON syntax/types, and `list_skills`/`read_skill` for a supplied package. Shell, web, arbitrary code execution, and other tools are disabled. Skill loading is an explicit agent tool choice; this design does not measure native implicit skill routing. The agent can read task instructions and input data and must produce JSON, not code.

## Tasks and scoring

The [suite](../benchmarks/data_workflows/README.md) covers CSV cleanup, contact deduplication, grouped aggregation, decimal money rounding, timestamp offsets, joins, missing versus zero, stable ranking, payment reconciliation, and schema validation. Inputs and expected answers are original synthetic material under MIT. Each task exposes complete public requirements in `TASK.md`; its oracle and verifier stay outside the agent workspace. Unit checks accept every oracle, reject a plausible wrong answer for every task, and classify missing or invalid submissions. This vets the fixtures and verifier behavior, but it is not independent real-world task validation.

After the agent exits, the trusted local verifier compares `output.json` with the expected typed JSON and returns 0 for pass, 1 for wrong or missing output, and 2 for setup error. `check_output` cannot reveal the oracle or grade correctness. A runner or verifier infrastructure failure is recorded separately from a scored failure; a started agent that exceeds its declared time budget is a scored failure. There are no automatic model retries. Unrun slots remain in the metrics when execution stops early.

## Analysis

Pass rate uses only scored passes and failures; infrastructure errors and unrun slots have separate counts. Pairwise comparisons align outcomes by task and repetition. A task contributes to the reported pass-rate delta only when every declared repetition has scored outcomes on both sides. Missing, infrastructure-error, and unrun pairs are counted and excluded from that paired delta. The report also shows improvements, ties, and regressions by complete task.

The fixed-seed bootstrap resamples tasks, not individual runs. A 95% task bootstrap interval appears only when at least five tasks have complete paired outcomes, there are no partial pairs, and task deltas are not all identical. An omitted interval does not prove equivalence. A displayed interval is descriptive for this small, selected suite, not a causal confidence claim or a measure of generalization. With one repetition, model variability within a task is poorly measured. Model-reported input/output tokens and elapsed time are recorded when available; monetary cost is not independently measured.

`skillarena compare` requires the same suite identity, version and hash, identical task IDs and hashes, repetition count, and runner configuration. It can compare two conditions in one evidence bundle or conditions in two compatible bundles. Skill hashes may differ because comparing revisions is the point. A comparison across different settings should be described as separate observations rather than a paired skill effect.

## Evidence and limits

Runs snapshot task, skill, and implementation files; record the plan and environment; retain model events, tool audit, submitted workspace, evaluator result, and per-run metadata; then seal the bundle with SHA-256 hashes. See [result bundle guide](result-bundle.md). `skillarena verify` checks that the current files match the bundle's own manifest offline and never executes bundle content. The manifest is author-submitted: it does not authenticate the model provider, certify correct scoring, verify account billing, or establish independent replication. Reproduction requires a trusted source checkout, the declared environment, and a fresh run.

The quota guard requires an existing ChatGPT login, rejects API credentials and custom endpoints, and stops when included quota is low or unknown or paid-credit state is available or unknown. It is a conservative local preflight, not a provider-side billing guarantee. A permitted run can consume included usage; it does not purchase credits.

The earlier [Python bug-fix pilot](../research/gpt6-sol-high-2026-10-14/README.md) and [scripted demo](../examples/demo.yaml) use the legacy command-runner protocol. Keep their results separate from v0.2. Legacy definitions can execute arbitrary local commands and should be run only from trusted sources.
