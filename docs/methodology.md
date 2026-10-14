# Benchmark methodology

SkillArena asks a narrow question: for a fixed task, runner, model configuration and evaluator, does adding one skill change the observed result?

## Experimental unit

One repetition contains a baseline run and a skill run. Each gets a fresh copy of `task.source`. Their order alternates across repetitions. The skill file is passed through `SKILLARENA_SKILL_PATH` only for the skill condition. A command adapter may still introduce uncontrolled differences; record its model name, version, temperature, seed when supported, prompt construction, tool access, and cost in its own logs.

## Evaluation

The evaluator is an external command. Exit code `0` means pass; any other code, timeout, or runner failure means fail. Keep evaluator code outside the agent's editable workspace and use hidden cases when appropriate. For real benchmarks, review whether an agent can access expected answers or modify the checker through other routes.

## Reporting

`metrics.json` contains every run, condition, return code, elapsed time, changed paths, and a summary. Logs include runner and evaluator output. `report.html` is a readable view of those data. The absolute success-rate change is descriptive, not a causal or statistical confidence claim. With a single task and a small number of runs, interpret the result as a local observation only.

## Before publishing a result

- Test multiple representative tasks, not just one favorable example.
- Freeze or record model and adapter versions, environment, dependency versions, and evaluation rules.
- Predefine repetitions and metrics. Keep failures in the result set.
- Disclose token use, latency and cost if available; use `unknown` if not measured.
- Publish the task, skill, raw results and a reproducible command where licenses permit.
- Distinguish synthetic demonstrations from experiments on actual AI agents.
