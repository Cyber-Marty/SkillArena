# Contributing to SkillArena

Thanks for helping make agent skill claims testable. Issues, documentation fixes, task fixtures, and adapters are welcome.

## Local setup

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest
skillarena run examples/demo.yaml --output results/local-demo
```

## Benchmark contribution checklist

1. State the task, expected behavior, and source or license for any borrowed code/data.
2. Put the evaluator outside the copied task workspace.
3. Use the same runner, model configuration, and task input for both conditions. The skill should be the only intended difference.
4. Make the task small enough to rerun and inspect. Do not commit credentials, private data, generated model logs, or unverifiable success claims.
5. Label deterministic or mock demonstrations as synthetic.

For a code change, include a test that checks behavior and describe how you verified it in the pull request. Please open an issue before building a large new adapter or evaluator so the interface can be agreed on first.
