# GPT-6 Sol High: Python inclusive-index repair

**Date:** 2026-10-14 (Asia/Shanghai)

**Question:** Does a short boundary-checking skill improve GPT-6 Sol High on this fixed Python repair task?

## Result

| Condition | Success | Mean input tokens | Mean output tokens | Mean runner duration |
| --- | ---: | ---: | ---: | ---: |
| Without skill | 3/3 | 14,457 | 104 | 34.9 s |
| With skill | 3/3 | 14,507 | 112 | 46.7 s |

The observed success-rate difference is **0 percentage points**. Both conditions produced the same passing one-line fix. We did not observe an improvement on this task. Duration varied substantially between runs, so the time difference is not evidence that the skill slows the model.

## Setup

- Model request: `gpt-6-sol`, reasoning effort `high`.
- Client: Codex CLI `0.162.0-alpha.17.2`, signed in with ChatGPT. The adapter refuses `OPENAI_API_KEY` and non-ChatGPT authentication. No API-key calls were used.
- Task: [`calculate.py`](../../examples/python_bug_fix/fixture/calculate.py) returns a sum through an inclusive index but uses an exclusive slice bound.
- Skill: [`skill.md`](../../examples/python_bug_fix/skill.md) asks the model to check slice boundary semantics and keep the fix small.
- Interaction: the full source and task are supplied to the model. It returns a schema-constrained complete replacement file. The model session is read-only and uses no tools. The harness writes the returned file to an isolated task copy.
- Evaluator: [`evaluate.py`](../../examples/python_bug_fix/evaluate.py) is outside the task copy and checks four cases.
- Order: baseline → skill, skill → baseline, baseline → skill. Each of the six runs starts from the same source. No failed model results were dropped.

The benchmark definition is [`examples/real_codex.yaml`](../../examples/real_codex.yaml). SHA-256 prefixes: definition `c5b713334141`, task files `f1a68a38ffd7`, skill `278d6ebeae01`. Python 3.13.15 was used on Windows.

## Evidence

- [Raw run metrics](metrics.json) and [HTML report](report.html)
- [Model event records](events/) containing each returned replacement and token usage
- [Evaluator results](evaluations/) and [resulting files](outputs/)

The `events/` files retain the model's completion and usage events. Client startup warnings, local paths and session IDs were omitted from this public bundle. The original unredacted logs remain local to the experimenter.

## Reproduce

Install from this checkout, sign the current Codex CLI in with ChatGPT, and run:

```bash
skillarena run examples/real_codex.yaml --output results/real-reproduction
```

If your shell finds an older CLI, set `SKILLARENA_CODEX_BIN` to the newer CLI executable first. The exact results may differ because model behavior and service conditions can change. The task, skill, runner and evaluator are all included in this repository.

## Limits

This is one easy synthetic task and three paired repetitions. It is a real-model pilot, not an estimate of performance across tasks or models. The skill contains general advice already familiar to a strong coding model. Token counts include Codex client context as reported by the CLI. We did not compute a confidence interval or attach a causal claim to the duration difference.

Early setup attempts with an older CLI and a workspace sandbox failed before a valid model edit; they were excluded from this model-only protocol. The six reported runs were completed with the same final adapter and include every resulting pass and failure.
