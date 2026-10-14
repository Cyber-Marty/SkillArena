# GPT-6 Sol High: audited agent and skill version experiment

Recorded 2026-10-14. **30 real agent runs**: 10 original synthetic data tasks ×
3 conditions × 1 repetition. Model requested: `gpt-6-sol`, reasoning `high`,
using existing ChatGPT login through the local Codex CLI. No API key or credit
purchase was used. Every saved quota check reports no available paid credits;
this is not an independent invoice audit.

| Condition | Passed | Skill read | Tool calls | Mean input tokens | Mean output tokens | Mean seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 10/10 | 0/10 | 62 | 42778.1 | 446.9 | 41.2116 |
| v1 | 10/10 | 10/10 | 72 | 43231.2 | 482.3 | 40.1735 |
| v2 | 10/10 | 10/10 | 78 | 42438.8 | 503.0 | 43.3902 |

The observed v1 → v2 success-rate difference is **+0.0 percentage points**;
0 tasks improved, 10 tied, and
0 regressed. This describes these synthetic tasks only.
One repetition per task does not estimate within-task variability. Bootstrap intervals are omitted for uniform task deltas; this does not prove equivalence.
There is no independent external replication.

## Inspect the evidence

- [Live report](https://Cyber-Marty.github.io/SkillArena/)
- [Portable report](evidence/report.html), [metrics](evidence/metrics.json), and [version comparison](v1-v2-comparison.json)
- [Frozen plan](evidence/plan.json), [environment](evidence/environment.json), [task/skill/source snapshots](evidence/snapshot)
- [Every run's events, tools, submitted answer and score](evidence/runs)
- [Integrity manifest](evidence/manifest.json), [public-export redactions](evidence/redactions.json)
- [Two disclosed setup sessions](setup/README.md), excluded from the formal comparison

Source commit at experiment start: [`8a1a852f7a2ad7f0ac3ace934702210b0aa264a0`](https://github.com/Cyber-Marty/SkillArena/tree/8a1a852f7a2ad7f0ac3ace934702210b0aa264a0).
The working tree was clean at experiment start. Runtime: codex-cli 0.162.0-alpha.17.2,
Python 3.13.15, Windows 11.
The published application also includes later report escaping and edge-case
hardening; the exact experiment implementation is preserved in the bundle.

The agent explicitly discovers/reads skills through MCP and executes restricted
file tools. It cannot run arbitrary shell commands or access the evaluator through
those tools. This is a tool-using data agent experiment, not a measurement of native
implicit skill routing or skill-script execution. Model aliases are not fixed
provider snapshots. Setup and final results were retained without selecting runs
by their score.

## Check locally without a model call

```bash
skillarena verify research/gpt6-sol-high-agent-2026-10-14/evidence
skillarena compare research/gpt6-sol-high-agent-2026-10-14/evidence --left v1 --right v2
```

Public manifest SHA-256: `1fbbe2fa8d715e35e1ae8c0155ff9d38934841267e683e611009057e1e1d97af`.
Matching hashes show file integrity, not provider authenticity or certification.
Account plan names and reset timestamps were removed from the public copy;
`source-manifest.json` records original hashes. Model/tool traces, all scores,
outputs, task inputs and skill snapshots are unchanged. The unredacted sealed
bundle remains local. Git attributes preserve exact evidence bytes.

To rerun, review and trust the frozen source/tasks first, then use
`evidence/snapshot/experiment.yaml` with `skillarena run ... --execute` and a new
output directory. The included-quota checks remain mandatory. A fresh run is
additional inference; offline verification and comparison are not.
