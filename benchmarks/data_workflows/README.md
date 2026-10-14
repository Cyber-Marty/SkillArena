# Data workflows v1

This frozen, offline suite has ten small tasks based on original synthetic data. It evaluates whether an agent can read local inputs, apply stated transformation rules, and write `output.json`. No task needs a network request, model call, package install, or executable submission.

Each `fixture/` contains everything shown to the agent: source data and `TASK.md`. `task.json` repeats the public instructions for runners. `oracle/` and `verifier.py` are trusted evaluation material and must not be copied into the agent workspace. The verifier is invoked as `python verifier.py WORKSPACE`, where `WORKSPACE/output.json` is the submission. Exit codes are 0 for correct, 1 for incorrect or absent submission, and 2 for evaluator setup errors.

The data and task text were created for this repository and are released under the repository's MIT license. They do not represent real customers, transactions, or external datasets. Dates with UTC offsets test offset arithmetic rather than timezone database behavior; money rules state their rounding convention explicitly. Exact JSON comparison is deliberate: prompts define field names, types, order, and records. Object key order and whitespace are irrelevant.

Freeze policy: version `1.0.0` fixes task identifiers, public instructions, fixtures, and expected answers. Any change that affects a correct answer requires a new suite version and a recorded rationale. Typo-only documentation fixes may retain the version. Keep all task material in source control so repeated runs use the same inputs and oracle.
