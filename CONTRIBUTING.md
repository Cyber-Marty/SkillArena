# Contributing to SkillArena

Issues, documentation fixes, task fixtures, skills, and adapters are welcome. State which protocol you are changing: schema v2 is the restricted Codex agent suite; the legacy command runner executes trusted local commands.

## Local checks

```bash
python -m venv .venv
# Activate .venv for your shell.
python -m pip install -e ".[dev]"
python -m pytest
skillarena plan examples/agent_suite.yaml
```

Tests and `plan` run offline without model inference. Do not start model runs in CI or a pull request merely to demonstrate a fixture change. If a real run is authorized, use `skillarena doctor` first and keep its result bundle outside the source and skill directories.

## Task contribution protocol

1. Use a small, inspectable input that exercises a meaningful failure mode. State every scoring requirement in public `fixture/TASK.md` and the matching `task.json` prompt, including JSON field types and array order.
2. Record the data source and license. Prefer original synthetic data, label it honestly, and never include personal data, credentials, or copyrighted material without permission.
3. Keep `oracle/output.json` and `verifier.py` outside the agent's `fixture/`. Verifiers must be deterministic and use trusted local code only; exit 0 for correct, 1 for wrong or missing answer, and 2 for evaluator infrastructure errors. Agent submissions need only `output.json`.
4. Add a test that accepts the oracle and rejects at least one plausible incorrect answer, plus checks for missing or invalid output. Review the answer against the stated instructions, not only against the verifier.
5. Freeze the suite ID, semantic version, task IDs, inputs, instructions, and oracles before any comparative run. An answer-changing correction requires a new suite version and a recorded reason. Keep failed and incomplete runs visible in results.

For a skill change, identify which version is under test and leave the runner, model alias, task bytes, and tool boundary fixed. Compare only compatible result bundles. Claims about broad skill effectiveness require a separate, representative task set and independent validation; a synthetic suite result is a local observation.

## Evidence and security

The schema v2 runner exposes only its audited file tools and uses an existing ChatGPT login. It does not run agent-written code. Legacy benchmark definitions can execute arbitrary commands, so run only definitions from a trusted checkout. `skillarena verify` reads and hashes an imported result bundle without executing its files; do not run a verifier or script copied from an untrusted published bundle. Integrity checks cannot establish authenticity or independent replication.

Never commit authentication files or private model logs. Use a new output directory for each experiment and put regenerated reports outside sealed bundles. In a pull request, describe the changed behavior, source/license, checks run, and any material limitation. Discuss large new adapters or benchmark domains in an issue before implementation.
